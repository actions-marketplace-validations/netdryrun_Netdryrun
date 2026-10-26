"""Run behavioral checks.

Positive checks poll until they pass (networks need time to converge), then must pass again on
consecutive samples so a flapping session can't pass on one lucky sample. Negative checks run
after convergence and must hold for a whole window.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import Check
from .drivers import Driver


@dataclass
class Result:
    check: Check
    passed: bool
    detail: str
    attempts: int
    duration: float
    started: str
    evidence: list[dict] = field(default_factory=list)  # raw outputs from the final attempt
    history: list[dict] = field(default_factory=list)   # every sample: time offset, pass/fail, detail


def _bgp_session(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.bgp_neighbors(p.get("vrf", "default"))
    n = obs.value.get(p["neighbor"])
    if n is None:
        return False, f"neighbor {p['neighbor']} not configured (seen: {', '.join(obs.value) or 'none'})", obs.evidence
    return n.state == p["state"], f"state is {n.state}", obs.evidence


def _bgp_prefixes(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.bgp_neighbors(p.get("vrf", "default"))
    n = obs.value.get(p["neighbor"])
    if n is None:
        return False, f"neighbor {p['neighbor']} not configured", obs.evidence
    if n.state != "established":
        # counters reset to 0 when a session drops (e.g. a max-prefix trip), so a count
        # from a down session would satisfy "max" by accident
        return False, f"session is {n.state}; prefix counts are only meaningful when established", obs.evidence
    afi = p.get("afi", "ipv4-unicast")
    count = n.prefixes.get(afi, 0)  # established but the family reports nothing: zero prefixes
    if "exact" in p:
        ok = count == p["exact"]
    else:
        ok = count >= p.get("min", 0) and ("max" not in p or count <= p["max"])
    return ok, f"{count} {afi} prefixes accepted", obs.evidence


def _route(d: Driver, p: dict) -> tuple[bool, str, list]:
    obs = d.routes(p["prefix"], p.get("vrf", "default"))
    want_proto = str(p.get("protocol", "")).lower()
    matching = [r for r in obs.value if not want_proto or r.protocol == want_proto]
    active = [r for r in matching if r.active]
    if p.get("present", True):
        if active:
            return True, f"active via {active[0].protocol}", obs.evidence
        if p.get("active", True) is False and matching:
            # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
            return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
    # Absent means not in the routing table at all: a received-but-not-selected route
    # (e.g. a leaked default losing to a local one) is still a leak.
    if matching:
        r = matching[0]
        return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
    return True, "absent", obs.evidence


def _ping(d: Driver, p: dict) -> tuple[bool, str, list]:
    count = int(p.get("count", 3))
    obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
    sent, received = obs.value
    if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
    if p.get("expect", "success") == "success":
        need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
        return received >= need, f"{received}/{sent} replies (need {need})", obs.evidence
    return received == 0, f"{received}/{sent} replies", obs.evidence


EVALUATORS = {"bgp_session": _bgp_session, "bgp_prefixes": _bgp_prefixes, "route": _route, "ping": _ping}


def is_post_convergence(check: Check) -> bool:
    """Checks that are trivially true before the network converges, so they must run afterwards
    and hold: "must be absent", "must fail", a session expected NOT established, and upper bounds
    on prefix counts (0 prefixes satisfies "max: 10" while BGP is still coming up)."""
    p = check.params
    return (
        (check.type == "route" and p.get("present", True) is False)
        or (check.type == "ping" and p.get("expect", "success") == "failure")
        or (check.type == "bgp_session" and p.get("state", "established") != "established")
        or (check.type == "bgp_prefixes" and ("max" in p or "exact" in p))
    )


def _evaluate(check: Check, driver: Driver) -> tuple[bool, str, list]:
    try:
        return EVALUATORS[check.type](driver, check.params)
    except Exception as e:  # a crashed check is a failed check, with the reason kept
        return False, f"error: {e}", []


def run_check(check: Check, driver: Driver, interval: float = 3.0, confirm: int = 2,
              clock=time.monotonic, sleep=time.sleep) -> Result:
    """Positive check: poll until it passes `confirm` samples in a row, or the timeout expires."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    history: list[dict] = []
    streak = 0
    while True:
        ok, detail, evidence = _evaluate(check, driver)
        elapsed = clock() - t0
        history.append({"t": round(elapsed, 1), "passed": ok, "detail": detail})
        streak = streak + 1 if ok else 0
        if streak >= confirm or elapsed >= check.timeout:
            passed = streak >= confirm
            if not passed and ok:
                detail = f"{detail}, but not stable ({streak}/{confirm} consecutive passes before timeout)"
            elif not passed and any(h["passed"] for h in history):
                detail = f"{detail} (flapping: passed {sum(h['passed'] for h in history)} of {len(history)} samples)"
            return Result(check, passed, detail, len(history), round(elapsed, 1), started, evidence, history[-50:])
        sleep(min(interval, max(0.0, check.timeout - elapsed)))


def hold_check(check: Check, driver: Driver, hold: float = 10.0, interval: float = 3.0,
               clock=time.monotonic, sleep=time.sleep) -> Result:
    """Negative check: must stay true for the whole hold window; fails at the first violation."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = clock()
    history: list[dict] = []
    while True:
        ok, detail, evidence = _evaluate(check, driver)
        elapsed = clock() - t0
        history.append({"t": round(elapsed, 1), "passed": ok, "detail": detail})
        if not ok or elapsed >= hold:
            if ok:
                detail = f"{detail} (held {round(elapsed)}s, {len(history)} samples)"
            return Result(check, ok, detail, len(history), round(elapsed, 1), started, evidence, history[-50:])
        sleep(min(interval, max(0.0, hold - elapsed)))


def converge_then_hold(check: Check, driver: Driver, hold: float = 10.0, interval: float = 3.0,
                       clock=time.monotonic, sleep=time.sleep) -> Result:
    """Post-convergence check: reach the expected state (e.g. prefix count up to min), then hold it.

    Only prefix counts need the "reach" phase (counters ramp up). For absent routes, failing pings
    and down sessions, a violation seen after convergence is a real failure: fail fast."""
    if check.type != "bgp_prefixes":
        return hold_check(check, driver, hold=check.hold or hold, interval=interval, clock=clock, sleep=sleep)
    first = run_check(check, driver, interval=interval, confirm=1, clock=clock, sleep=sleep)
    if not first.passed:
        return first
    held = hold_check(check, driver, hold=check.hold or hold, interval=interval, clock=clock, sleep=sleep)
    held.started = first.started
    held.duration = round(first.duration + held.duration, 1)
    held.attempts += first.attempts
    held.history = (first.history + held.history)[-50:]
    return held
