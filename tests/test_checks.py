"""Check runner logic with a fake driver and a fake clock (no lab needed)."""
from netdryrun.checks import converge_then_hold, hold_check, is_post_convergence, run_check
from netdryrun.config import Check
from netdryrun.drivers.base import BgpNeighbor, Observation, Route


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeDriver:
    """Returns a scripted sequence of states, one per call."""

    def __init__(self, states=(), routes=()):
        self.states = list(states)
        self.route_seq = list(routes)

    def bgp_neighbors(self, vrf="default"):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return Observation({"10.0.0.2": BgpNeighbor("10.0.0.2", state, {"ipv4-unicast": 5})}, [])

    def routes(self, prefix, vrf="default"):
        rs = self.route_seq.pop(0) if len(self.route_seq) > 1 else self.route_seq[0]
        return Observation(rs, [])


def check(ctype, timeout=30, **params):
    return Check(type=ctype, params=params, name=ctype, timeout=timeout)


def test_positive_check_waits_for_convergence():
    clock = FakeClock()
    d = FakeDriver(states=["active", "connect", "established"])
    r = run_check(check("bgp_session", node="r1", neighbor="10.0.0.2", state="established"), d,
                  interval=3, clock=clock, sleep=clock.sleep)
    assert r.passed and r.attempts == 4  # 2 converging samples + 2 confirming passes


def test_positive_check_times_out():
    clock = FakeClock()
    d = FakeDriver(states=["active"])
    r = run_check(check("bgp_session", timeout=10, node="r1", neighbor="10.0.0.2", state="established"), d,
                  interval=3, clock=clock, sleep=clock.sleep)
    assert not r.passed and "active" in r.detail and clock.t >= 10


def test_unknown_neighbor_fails_with_reason():
    clock = FakeClock()
    r = run_check(check("bgp_session", timeout=0, node="r1", neighbor="10.9.9.9", state="established"),
                  FakeDriver(states=["established"]), clock=clock, sleep=clock.sleep)
    assert not r.passed and "not configured" in r.detail


def test_prefix_range_catches_route_leak():
    clock = FakeClock()
    r = run_check(check("bgp_prefixes", timeout=0, node="r1", neighbor="10.0.0.2", min=1, max=3),
                  FakeDriver(states=["established"]), clock=clock, sleep=clock.sleep)
    assert not r.passed and "5" in r.detail


def test_negative_check_fails_on_late_violation():
    clock = FakeClock()
    leak = [Route("0.0.0.0/0", "bgp", True)]
    d = FakeDriver(routes=[[], [], leak])
    c = check("route", node="r1", prefix="0.0.0.0/0", protocol="bgp", present=False)
    assert is_post_convergence(c)
    r = hold_check(c, d, hold=10, interval=3, clock=clock, sleep=clock.sleep)
    assert not r.passed and "unexpectedly present" in r.detail


def test_negative_check_passes_after_hold():
    clock = FakeClock()
    r = hold_check(check("route", node="r1", prefix="0.0.0.0/0", present=False), FakeDriver(routes=[[]]),
                   hold=10, interval=3, clock=clock, sleep=clock.sleep)
    assert r.passed and "held" in r.detail


def test_inactive_route_is_not_present():
    clock = FakeClock()
    d = FakeDriver(routes=[[Route("10.0.0.0/8", "bgp", False)]])
    r = run_check(check("route", timeout=0, node="r1", prefix="10.0.0.0/8"), d, clock=clock, sleep=clock.sleep)
    assert not r.passed and "inactive" in r.detail


def test_absent_fails_on_received_but_not_selected_route():
    """Regression: a leaked BGP default losing to the kernel default is still a leak."""
    clock = FakeClock()
    d = FakeDriver(routes=[[Route("0.0.0.0/0", "kernel", True), Route("0.0.0.0/0", "bgp", False)]])
    c = check("route", node="r1", prefix="0.0.0.0/0", protocol="bgp", present=False)
    r = hold_check(c, d, hold=10, interval=3, clock=clock, sleep=clock.sleep)
    assert not r.passed and "not selected" in r.detail


def test_flapping_session_does_not_pass():
    clock = FakeClock()
    d = FakeDriver(states=["established", "idle"] * 10)
    r = run_check(check("bgp_session", timeout=15, node="r1", neighbor="10.0.0.2", state="established"), d,
                  interval=3, clock=clock, sleep=clock.sleep)
    assert not r.passed and "flapping" in r.detail


def test_exact_prefix_count():
    clock = FakeClock()
    r = run_check(check("bgp_prefixes", timeout=0, node="r1", neighbor="10.0.0.2", exact=5),
                  FakeDriver(states=["established"]), confirm=1, clock=clock, sleep=clock.sleep)
    assert r.passed


def test_upper_bounds_and_down_states_are_post_convergence():
    assert is_post_convergence(check("bgp_prefixes", node="r1", neighbor="10.0.0.2", max=10))
    assert is_post_convergence(check("bgp_prefixes", node="r1", neighbor="10.0.0.2", exact=0))
    assert not is_post_convergence(check("bgp_prefixes", node="r1", neighbor="10.0.0.2", min=1))
    assert is_post_convergence(check("bgp_session", node="r1", neighbor="10.0.0.2", state="idle"))
    assert not is_post_convergence(check("bgp_session", node="r1", neighbor="10.0.0.2", state="established"))


def test_converge_then_hold_catches_a_late_leak():
    """Count reaches the allowed range, then a leak pushes it over max during the hold."""
    clock = FakeClock()

    class Ramp(FakeDriver):
        counts = [2, 2, 50]

        def bgp_neighbors(self, vrf="default"):
            n = self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]
            return Observation({"10.0.0.2": BgpNeighbor("10.0.0.2", "established", {"ipv4-unicast": n})}, [])

    r = converge_then_hold(check("bgp_prefixes", node="r1", neighbor="10.0.0.2", min=1, max=10), Ramp(),
                           hold=10, interval=3, clock=clock, sleep=clock.sleep)
    assert not r.passed and "50" in r.detail


def test_route_present_not_selected_with_active_false():
    clock = FakeClock()
    d = FakeDriver(routes=[[Route("0.0.0.0/0", "kernel", True), Route("0.0.0.0/0", "bgp", False)]])
    ok = run_check(check("route", timeout=0, node="r1", prefix="0.0.0.0/0", protocol="bgp", active=False), d,
                   confirm=1, clock=clock, sleep=clock.sleep)
    assert ok.passed and "not selected" in ok.detail
    strict = run_check(check("route", timeout=0, node="r1", prefix="0.0.0.0/0", protocol="bgp"), d,
                       confirm=1, clock=clock, sleep=clock.sleep)
    assert not strict.passed


def test_round_robin_shares_one_timeout():
    """Three permanently failing checks cost about one timeout, not three."""
    from netdryrun.checks import run_round_robin
    clock = FakeClock()
    d = FakeDriver(states=["active"])
    checks = [check("bgp_session", timeout=30, node="r1", neighbor="10.0.0.2", state="established") for _ in range(3)]
    results = run_round_robin(checks, {"r1": d}, interval=3, clock=clock, sleep=clock.sleep)
    assert all(not r.passed for r in results)
    assert clock.t <= 33


def test_round_robin_passes_converging_checks():
    from netdryrun.checks import run_round_robin
    clock = FakeClock()
    d = FakeDriver(states=["active", "established"])
    results = run_round_robin([check("bgp_session", node="r1", neighbor="10.0.0.2", state="established")],
                              {"r1": d}, interval=3, clock=clock, sleep=clock.sleep)
    assert results[0].passed


def test_hold_together_catches_late_violation_and_passes_others():
    from netdryrun.checks import hold_together
    clock = FakeClock()
    leak = [Route("0.0.0.0/0", "bgp", True)]
    bad = check("route", node="r1", prefix="0.0.0.0/0", present=False)
    good = check("route", node="r2", prefix="0.0.0.0/0", present=False)
    results = hold_together([bad, good], {"r1": FakeDriver(routes=[[], leak]), "r2": FakeDriver(routes=[[]])},
                            hold=10, interval=3, clock=clock, sleep=clock.sleep)
    assert not results[0].passed and results[1].passed


def test_evidence_excerpt_finds_the_prefix():
    from netdryrun.report import _evidence_excerpt
    out = "\n".join([f"line {i}" for i in range(40)] + ['"0.0.0.0/0": [{"protocol": "bgp", "selected": false}]'] + ["tail"] * 20)
    ex = _evidence_excerpt(out, {"prefix": "0.0.0.0/0"})
    assert '"0.0.0.0/0"' in ex and len(ex.splitlines()) <= 16


class SlowDriver(FakeDriver):
    """Every sample costs 2 seconds of (fake) time, like a slow SR Linux show command."""

    def __init__(self, clock, **kw):
        super().__init__(**kw)
        self.clock = clock

    def bgp_neighbors(self, vrf="default"):
        self.clock.t += 2
        return super().bgp_neighbors(vrf)


def test_big_slow_list_does_not_false_fail_healthy_checks():
    """Regression (Grok review): 80 healthy checks, slow samples, short timeout: all must pass."""
    from netdryrun.checks import run_round_robin
    clock = FakeClock()
    d = SlowDriver(clock, states=["established"])
    checks = [check("bgp_session", timeout=30, node="r1", neighbor="10.0.0.2", state="established") for _ in range(80)]
    results = run_round_robin(checks, {"r1": d}, interval=3, clock=clock, sleep=clock.sleep)
    assert all(r.passed for r in results), [r.detail for r in results if not r.passed][:3]


def test_max_only_prefix_check_fails_when_count_climbs_after_zero():
    """Regression (Grok review): 0 prefixes at first must not let a max check pass a later leak."""
    from netdryrun.checks import hold_together
    clock = FakeClock()

    class Climb(FakeDriver):
        counts = [0, 0, 50]

        def bgp_neighbors(self, vrf="default"):
            n = self.counts.pop(0) if len(self.counts) > 1 else self.counts[0]
            return Observation({"10.0.0.2": BgpNeighbor("10.0.0.2", "established", {"ipv4-unicast": n})}, [])

    r = hold_together([check("bgp_prefixes", node="r1", neighbor="10.0.0.2", max=10)], {"r1": Climb()},
                      hold=10, interval=3, clock=clock, sleep=clock.sleep)[0]
    assert not r.passed and "50" in r.detail


def test_per_check_hold_is_honored():
    """Regression (Grok review): hold: 30 on one check must catch a violation at t=20."""
    from netdryrun.checks import hold_together
    clock = FakeClock()
    leak_late = FakeDriver(routes=[[]] * 7 + [[Route("0.0.0.0/0", "bgp", True)]])
    c = check("route", node="r1", prefix="0.0.0.0/0", present=False)
    c.hold = 30
    r = hold_together([c], {"r1": leak_late}, hold=10, interval=3, clock=clock, sleep=clock.sleep)[0]
    assert not r.passed and "unexpectedly present" in r.detail
