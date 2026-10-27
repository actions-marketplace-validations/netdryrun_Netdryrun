"""Runner verdict logic: run(), run_scenario(), the post-convergence BGP gate and the fault-visibility wait.

A whole run is driven on a fake clock, against a fake lab and VRF-aware fake drivers whose state is a
function of time. The checks module is NOT wrapped, so the clock and sleep the runner passes down are the
ones that are used. Each test asserts a status, a verdict, which checks ran, what the lab was asked to do
or how long the run waited, never a message text.
"""
from __future__ import annotations

import ipaddress
import signal
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.checks import Result
from netdryrun.config import Check, Config, Fault, Scenario
from netdryrun.drivers.base import BgpNeighbor, DriverError, Observation, Route
from netdryrun.lab import ExecResult, Lab, LabError, Node


# ----------------------------------------------------------------------------------------------- fakes

class Clock:
    def __init__(self, start=1000.0):
        self.start = self.t = start
        self.sleeps: list[float] = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        assert s >= 0
        self.sleeps.append(s)
        self.t += s
        assert len(self.sleeps) < 5000, "a wait that never ends"

    @property
    def now(self):
        return self.t - self.start


class FakeLab:
    def __init__(self, clock, nodes=("r1", "r2", "r3"), kinds=None, existing=(), running=None, destroy_rc=0,
                 destroy_error=None, deploy_error=None, addresses=None, links=None, set_link_error=None):
        self.clock, self.name, self.topology = clock, "t", Path("t.clab.yml")
        kinds = kinds or {}
        self.nodes = {n: Node(n, f"clab-t-{n}", *kinds.get(n, ("linux", "quay.io/frrouting/frr:10.4.1")))
                      for n in nodes}
        self.links = links if links is not None else [(("r1", "eth1"), ("r2", "eth1")), (("r2", "eth2"), ("r3", "eth1"))]
        self.existing, self.running = set(existing), running
        self.destroy_rc, self.destroy_error, self.deploy_error = destroy_rc, destroy_error, deploy_error
        self.addresses = addresses if addresses is not None else {("r1", "eth1"): ["10.0.12.1/30"],
                                                                  ("r2", "eth1"): ["10.0.12.2/30"]}
        self.set_link_error = set_link_error or {}
        self.events: list[tuple] = []
        self.deployed = self.destroyed = 0
        self.locked = False
        self.active_during_checks = None

    def check_tools(self):
        pass

    def version(self):
        return "test"

    def acquire_lock(self):
        self.locked = True
        self.events.append(("lock",))

    def release_lock(self):
        self.locked = False
        self.events.append(("unlock",))

    def existing_containers(self):
        return self.existing

    def deploy(self):
        self.deployed += 1
        self.events.append(("deploy",))
        if self.deploy_error:
            raise self.deploy_error
        return ExecResult([], 0, "", "")

    def destroy(self):
        self.destroyed += 1
        self.events.append(("destroy",))
        if self.destroy_error:
            raise self.destroy_error
        return ExecResult([], self.destroy_rc, "", "boom" if self.destroy_rc else "")

    def running_containers(self):
        if self.running is not None:
            return set(self.running)
        return {n.container for n in self.nodes.values()}

    def run_setup(self, node, cmds, log=None):
        self.events.append(("setup", node, tuple(cmds), log is not None))

    def _require_linux_links(self, node):
        self.events.append(("require", node))

    def data_interfaces(self, node):
        return {"r1": ["eth1", "eth2"]}.get(node, ["eth1"])

    def set_link(self, node, iface, up):
        self.events.append(("link", node, iface, up, self.clock.now))
        err = self.set_link_error.get((node, iface, up))
        if err:
            raise err
        return ExecResult([], 0, "", "")

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(a) for a in self.addresses.get((node, iface), [])]

    def peers_of(self, node, iface):
        return Lab.peers_of(self, node, iface)

    def link_events(self):
        return [e[1:4] for e in self.events if e[0] == "link"]


def _at(v, t):
    return v(t) if callable(v) else v


class Drv:
    """neighbors: {vrf: value or fn(t)} where value is {addr: state or (state, {afi: n})};
    routes: {vrf: fn(t, prefix) -> bool (present and active)}. A VRF not listed is an error."""

    def __init__(self, clock, neighbors=None, routes=None, ping=None, neighbors_error=None, on_call=None):
        self.clock, self.neighbors, self.routes_ = clock, neighbors or {}, routes or {}
        self.ping_, self.neighbors_error, self.on_call = ping, neighbors_error, on_call
        self.calls: list[tuple] = []

    def bgp_neighbors(self, vrf="default"):
        self.calls.append(("bgp_neighbors", vrf, self.clock.now))
        if self.on_call:
            self.on_call()
        err = _at(self.neighbors_error, self.clock.now)
        if err:
            raise err
        if vrf not in self.neighbors:
            raise DriverError(f"no VRF {vrf}")
        out = {}
        for a, s in _at(self.neighbors[vrf], self.clock.now).items():
            state, pfx = (s, {"ipv4-unicast": 3}) if isinstance(s, str) else s
            out[a] = BgpNeighbor(a, state, dict(pfx))
        return Observation(out, [{"cmd": "nbr"}])

    def routes(self, prefix, vrf="default"):
        self.calls.append(("routes", prefix, vrf, self.clock.now))
        if self.on_call:
            self.on_call()
        if vrf not in self.routes_:
            raise DriverError(f"no VRF {vrf}")
        present = self.routes_[vrf](self.clock.now, prefix)
        return Observation([Route(prefix, "bgp", True)] if present else [], [{"cmd": "rt"}])

    def ping(self, target, source, count, vrf="default"):
        self.calls.append(("ping", target, vrf, self.clock.now))
        return self.ping_(self.clock.now)


def always(t, p):
    return True


def never(t, p):
    return False


def up(*addrs):
    return {"default": {a: "established" for a in addrs}}


class Env:
    def __init__(self, monkeypatch, clock, lab, drivers):
        self.clock, self.lab, self.drivers = clock, lab, drivers
        self.for_node_calls: list[tuple] = []
        self.supported_calls: list[tuple] = []
        self.injections: list = []
        self.logs: list[str] = []
        self.results: list[Result] = []
        monkeypatch.setattr(runner, "_clock", clock)
        monkeypatch.setattr(runner, "_sleep", clock.sleep)
        monkeypatch.setattr(runner, "Lab", lambda path: lab)

        def for_node(lab_, node, override=None):
            assert lab_ is lab
            self.for_node_calls.append((node, override))
            return drivers[node]

        monkeypatch.setattr(runner, "for_node", for_node)

        def check_supported(lab_, c, override=None):
            assert lab_ is lab
            self.supported_calls.append((c.name, override))

        monkeypatch.setattr(runner, "check_supported", check_supported)
        env = self

        class Injection:
            def __init__(self, lab_, node, prefixes, as_path):
                assert lab_ is lab
                self.node, self.prefixes, self.as_path, self.applied, self.restored = node, prefixes, as_path, False, 0
                env.injections.append(self)

            def describe(self):
                return f"{self.node}"

            def apply(self):
                self.applied = True
                env.lab.events.append(("inject", self.node, self.clock_now()))

            def restore(self):
                self.restored += 1
                env.lab.events.append(("uninject", self.node))

            def clock_now(self):
                return env.clock.now

        monkeypatch.setattr(runner, "RouteInjection", Injection)

    def run(self, checks, scenarios=(), drivers_cfg=None, setup=None, **kw):
        cfg = Config(path=Path("netdryrun.yml"), lab=Path("t.clab.yml"), timeout=120, checks=list(checks),
                     drivers=drivers_cfg or {}, scenarios=list(scenarios), setup=setup or {})
        kw.setdefault("deploy", False)
        return runner.run(cfg, on_result=self.results.append, log=self.logs.append, **kw)


def chk(ctype, name, node="r1", timeout=30, hold=None, **params):
    return Check(type=ctype, params={"node": node, **params}, name=name, timeout=timeout, hold=hold)


def route(name, node="r1", prefix="10.9.9.0/24", **kw):
    return chk("route", name, node=node, prefix=prefix, **kw)


def leak(name, node="r1", prefix="10.66.0.0/16", **kw):
    return chk("route", name, node=node, prefix=prefix, present=False, **kw)


def by_name(rep):
    return {r.check.name: r for r in rep.results}


def iso(s):
    return isinstance(s, str) and datetime.fromisoformat(s).utcoffset().total_seconds() == 0


def make(monkeypatch, nodes=("r1", "r2", "r3"), **drivers_kw):
    clock = Clock()
    lab = FakeLab(clock, nodes=nodes)
    drivers = {n: Drv(clock, **drivers_kw.get(n, {"neighbors": up(), "routes": {"default": always}})) for n in nodes}
    return Env(monkeypatch, clock, lab, drivers)


# ----------------------------------------------------------------------------------------------- run(): phases

def test_negative_checks_run_after_convergence_and_hold(monkeypatch):
    """A leak arriving during the hold window fails; a positive check is never held."""
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"),
                              "routes": {"default": lambda t, p: p == "10.9.9.0/24" or t >= 20}})
    pos, neg = route("pos"), leak("neg")
    rep = e.run([neg, pos], settle=10, hold=10)
    assert rep.status == "failed"
    assert by_name(rep)["pos"].passed and not by_name(rep)["neg"].passed
    assert [r.check.name for r in rep.results] == ["neg", "pos"]          # the user's order
    assert sorted(r.check.name for r in e.results) == ["neg", "pos"]      # each reported once
    assert e.results[0].check is pos                                      # positives finish first
    assert iso(rep.started) and iso(rep.finished)


def test_post_convergence_check_is_not_judged_on_two_early_samples(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": lambda t, p: t >= 8}})
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "failed"


def test_positive_check_passes_on_two_samples_and_is_not_held(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: t < 5}})
    rep = e.run([route("pos")], settle=10, hold=10)
    assert rep.status == "passed" and e.clock.now == 3.0


def test_settle_waits_at_least_30s_when_nothing_proved_convergence(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    rep = e.run([leak("neg")], settle=10, hold=10)
    assert rep.status == "passed" and 30.0 in e.clock.sleeps and 10.0 not in e.clock.sleeps[:3]
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}})
    rep = e.run([leak("neg"), route("pos")], settle=10, hold=10)
    assert rep.status == "passed" and 10.0 in e.clock.sleeps and 30.0 not in e.clock.sleeps
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": never}})
    e.run([leak("neg")], settle=45, hold=10)
    assert 45.0 in e.clock.sleeps


def test_run_defaults_settle_and_hold_10s(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}})
    cfg = Config(path=Path("x"), lab=Path("t"), timeout=120, checks=[route("pos"), leak("neg")])
    rep = runner.run(cfg, deploy=False)
    assert rep.status == "passed"
    assert e.clock.sleeps.count(10.0) == 1
    assert by_name(rep)["neg"].duration == 10.0


def test_hold_is_passed_to_the_post_convergence_checks(monkeypatch):
    # the leak arrives 15 s into the hold: caught with hold=20, not with the default 10
    def routes(start):
        return {"default": lambda t, p: p == "10.9.9.0/24" or t >= start}

    e = make(monkeypatch, r1={"neighbors": up(), "routes": routes(3 + 10 + 15)})
    assert e.run([route("pos"), leak("neg")], settle=10, hold=20).status == "failed"
    e = make(monkeypatch, r1={"neighbors": up(), "routes": routes(3 + 10 + 15)})
    assert e.run([route("pos"), leak("neg")], settle=10, hold=10).status == "passed"


def test_checks_wait_on_the_runner_clock(monkeypatch):
    """Durations come from the runner's clock (the one tests and the CLI share), for every phase."""
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24" and t >= 6}})
    rep = e.run([route("pos"), leak("neg")], settle=10, hold=10)
    assert by_name(rep)["pos"].duration == 9.0 and by_name(rep)["neg"].duration == 10.0
    assert e.clock.now == 9 + 3 + 10 + 10   # positives, the gate's second sample, settle, hold


def test_not_converged_checks_are_reported_once_and_not_held(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up("10.0.12.2"), "routes": {"default": always}},
             r3={"neighbors": {"default": {"10.0.23.2": "active"}}, "routes": {"default": never}})
    checks = [chk("bgp_session", "s", neighbor="10.0.12.2", state="established"),
              leak("neg", node="r3", timeout=12), leak("neg2", node="r1", prefix="10.77.0.0/16")]
    e.drivers["r1"].routes_ = {"default": lambda t, p: p != "10.77.0.0/16"}
    rep = e.run(checks, settle=10, hold=10)
    names = [r.check.name for r in rep.results]
    assert names == ["s", "neg", "neg2"] and len(e.results) == 3
    r = by_name(rep)["neg"]
    assert r.passed is False and not any(c[0] == "routes" for c in e.drivers["r3"].calls)
    assert by_name(rep)["neg2"].passed and rep.status == "failed"
    assert all(isinstance(x, Result) for x in e.results)
    assert sorted(x.check.name for x in e.results) == ["neg", "neg2", "s"]


def test_gate_uses_positive_results_to_skip_dead_nodes(monkeypatch):
    """A node whose positive checks never got usable state already waited out their timeout: no second wait."""
    e = make(monkeypatch, r1={"neighbors_error": DriverError("bgpd down"), "routes": {"default": never}})
    checks = [chk("bgp_session", "s", neighbor="10.0.12.2", timeout=9), leak("neg", timeout=60)]
    rep = e.run(checks, settle=10, hold=10)
    assert rep.status == "inconclusive"
    assert e.clock.now == 9 + 10 + 10   # session timeout, settle, hold: the gate did not wait 60 s


def test_gate_warning_when_a_node_never_answers(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}},
             r3={"neighbors_error": DriverError("no bgpd"), "routes": {"default": never}})
    rep = e.run([route("pos"), leak("neg", node="r3", timeout=9)], settle=10, hold=10)
    assert rep.status == "passed" and len(e.logs) == 2


def test_results_of_every_phase_are_kept(monkeypatch):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": lambda t, p: p == "10.9.9.0/24"}})
    rep = e.run([route("a"), leak("b"), route("c", prefix="10.8.0.0/16")], settle=10, hold=10)
    assert [r.check.name for r in rep.results] == ["a", "b", "c"]
    assert [r.passed for r in rep.results] == [True, True, False]


def test_report_started(monkeypatch):
    e = make(monkeypatch)
    rep = e.run([route("a")])
    assert iso(rep.started) and rep.lab_name == "t"
    assert rep.environment["nodes"]["r1"] == {"kind": "linux", "image": "quay.io/frrouting/frr:10.4.1"}
    assert set(rep.environment) == {"netdryrun", "containerlab", "python", "host", "nodes"}


# ----------------------------------------------------------------------------------------------- run(): setup

def test_drivers_get_the_configured_override(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth9")], [route("[s] x", node="r3")])
    e.run([route("a"), route("b", node="r2")], [sc], drivers_cfg={"r2": "srlinux"})
    assert ("r2", "srlinux") in e.for_node_calls and ("r1", None) in e.for_node_calls
    assert ("r3", None) in e.for_node_calls
    assert all(o == "srlinux" for n, o in e.for_node_calls if n == "r2")
    assert e.supported_calls == [("a", None), ("b", "srlinux"), ("[s] x", None)]


@pytest.mark.parametrize("what", ["check", "scenario_check", "fault", "setup"])
def test_unknown_nodes_are_an_error_before_deploying(monkeypatch, what):
    e = make(monkeypatch)
    checks, scenarios, setup = [route("a")], [], {}
    if what == "check":
        checks = [route("a", node="r9")]
    elif what == "scenario_check":
        scenarios = [Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r9")])]
    elif what == "fault":
        scenarios = [Scenario("s", [Fault("link_down", "r9", "eth1")], [route("x")])]
    else:
        setup = {"r9": ["true"]}
    rep = e.run(checks, scenarios, setup=setup, deploy=True)
    assert rep.status == "error" and e.lab.deployed == 0 and e.lab.destroyed == 0


def test_inject_routes_needs_an_frr_node(monkeypatch):
    clock = Clock()
    lab = FakeLab(clock, kinds={"r2": ("nokia_srlinux", "srl")})
    e = Env(monkeypatch, clock, lab, {n: Drv(clock, neighbors=up(), routes={"default": always}) for n in lab.nodes})
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x")])
    assert e.run([route("a")], [sc]).status == "error" and not e.injections
    # an frr override on that node makes it acceptable
    e = Env(monkeypatch, clock, lab, e.drivers)
    assert e.run([route("a")], [sc], drivers_cfg={"r2": "frr"}).status == "passed" and e.injections
    # and an override to another driver refuses an FRR image
    lab2 = FakeLab(clock)
    e = Env(monkeypatch, clock, lab2, {n: Drv(clock, neighbors=up(), routes={"default": always}) for n in lab2.nodes})
    sc = Scenario("s", [Fault("inject_routes", "r1", prefixes=["10.66.0.0/16"])], [route("x")])
    assert e.run([route("a")], [sc], drivers_cfg={"r1": "eos"}).status == "error"


def test_deploy_setup_and_destroy(monkeypatch):
    e = make(monkeypatch)
    seen = {}
    e.drivers["r1"].on_call = lambda: seen.setdefault("active", e.lab in runner._ACTIVE)
    rep = e.run([route("a")], setup={"r2": ["echo 1", "echo 2"]}, deploy=True)
    assert rep.status == "passed" and e.lab.deployed == 1 and e.lab.destroyed == 1
    assert ("setup", "r2", ("echo 1", "echo 2"), True) in e.lab.events
    assert seen["active"] is True and e.lab not in runner._ACTIVE
    assert e.lab.events[0] == ("lock",) and e.lab.events[-1] == ("unlock",)


def test_no_deploy_means_no_setup_and_no_destroy(monkeypatch):
    e = make(monkeypatch)
    rep = e.run([route("a")], setup={"r2": ["echo 1"]}, deploy=False)
    assert rep.status == "passed" and e.lab.deployed == 0 and e.lab.destroyed == 0
    assert not any(ev[0] == "setup" for ev in e.lab.events) and not any(ev[0] == "lock" for ev in e.lab.events)


def test_keep_leaves_the_lab_and_never_registers_it(monkeypatch):
    e = make(monkeypatch)
    seen = {}
    e.drivers["r1"].on_call = lambda: seen.setdefault("active", e.lab in runner._ACTIVE)
    rep = e.run([route("a")], deploy=True, keep=True)
    assert rep.status == "passed" and e.lab.destroyed == 0 and seen["active"] is False and not e.lab.locked


@pytest.mark.parametrize("ok,destroyed", [(True, 1), (False, 0)])
def test_keep_on_failure(monkeypatch, ok, destroyed):
    e = make(monkeypatch, r1={"neighbors": up(), "routes": {"default": always if ok else never}})
    rep = e.run([route("a", timeout=6)], deploy=True, keep_on_failure=True)
    assert rep.status == ("passed" if ok else "failed") and e.lab.destroyed == destroyed
    assert e.lab not in runner._ACTIVE


def test_keep_on_failure_does_not_apply_to_an_interrupted_run(monkeypatch):
    e = make(monkeypatch)

    def interrupt():
        raise KeyboardInterrupt

    e.drivers["r1"].on_call = interrupt
    with pytest.raises(KeyboardInterrupt) as exc:
        e.run([route("a")], deploy=True, keep_on_failure=True)
    rep = exc.value.report
    assert rep.status == "error" and rep.error and e.lab.destroyed == 1 and rep.finished


def test_interrupted_by_sigterm(monkeypatch):
    e = make(monkeypatch)

    def interrupt():
        raise runner.Interrupted(signal.SIGTERM)

    e.drivers["r1"].on_call = interrupt
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.report.status == "error" and exc.value.signum == signal.SIGTERM and e.lab.destroyed == 1


def test_signal_during_cleanup_is_raised_after_it(monkeypatch):
    e = make(monkeypatch)

    @contextmanager
    def deferred():
        yield [signal.SIGTERM, signal.SIGINT]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.signum == signal.SIGTERM and e.lab.destroyed == 1
    rep = exc.value.report
    assert rep.status == "error" and rep.error and rep.results[0].passed


def test_signal_during_cleanup_keeps_an_earlier_error(monkeypatch):
    e = make(monkeypatch)
    e.lab.existing = {"clab-t-r1"}

    @contextmanager
    def deferred():
        yield [signal.SIGHUP]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.report.error and exc.value.signum == signal.SIGHUP


def test_no_signal_during_cleanup_after_an_interrupt(monkeypatch):
    """The run was already interrupted: a signal recorded during cleanup doesn't replace it."""
    e = make(monkeypatch)

    def interrupt():
        raise runner.Interrupted(signal.SIGINT)

    e.drivers["r1"].on_call = interrupt

    @contextmanager
    def deferred():
        yield [signal.SIGTERM]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.signum == signal.SIGINT


def test_a_running_lab_is_refused(monkeypatch):
    e = make(monkeypatch)
    e.lab.existing = {"clab-t-r1"}
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and e.lab.deployed == 0 and e.lab.destroyed == 0 and not e.lab.locked


def test_missing_containers_are_an_error(monkeypatch):
    e = make(monkeypatch)
    e.lab.running = {"clab-t-r1", "clab-t-r2"}
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and e.lab.destroyed == 1
    e = make(monkeypatch)
    e.lab.running = {"clab-t-r1", "clab-t-r2"}
    assert e.run([route("a")], deploy=False).status == "error"


def test_cleanup_trouble_never_hides_the_results(monkeypatch):
    for kw in ({"destroy_rc": 1}, {"destroy_error": RuntimeError("docker gone")}):
        e = make(monkeypatch)
        for k, v in kw.items():
            setattr(e.lab, k, v)
        rep = e.run([route("a")], deploy=True)
        assert rep.status == "passed" and e.lab.destroyed == 1 and e.lab not in runner._ACTIVE and not e.lab.locked


def test_deploy_failure_is_an_error_and_the_lab_is_destroyed(monkeypatch):
    e = make(monkeypatch)
    e.lab.deploy_error = LabError("no image")
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and e.lab.destroyed == 1


def test_internal_error_is_an_error(monkeypatch, capsys):
    e = make(monkeypatch)
    e.lab.deploy_error = RuntimeError("boom")
    monkeypatch.setenv("NETDRYRUN_DEBUG", "1")
    rep = e.run([route("a")], deploy=True)
    assert rep.status == "error" and rep.exit_code == 2 and "Traceback" in capsys.readouterr().err


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, "10", None])
def test_bad_settle_or_hold_is_an_error(monkeypatch, value):
    for key in ("settle", "hold"):
        e = make(monkeypatch)
        rep = e.run([route("a")], deploy=True, **{key: value})
        assert rep.status == "error" and e.lab.deployed == 0


@pytest.mark.parametrize("value", [0, 0.0, 1e9])
def test_good_settle_and_hold(monkeypatch, value):
    e = make(monkeypatch)
    assert e.run([route("a")], settle=value, hold=value).status == "passed"


@pytest.mark.parametrize("value,env", [("1", True), ("yes", True), ("true", True), ("", False), ("0", False),
                                       ("false", False), ("no", False), (None, False)])
def test_debug_flag(monkeypatch, value, env):
    if value is None:
        monkeypatch.delenv("NETDRYRUN_DEBUG", raising=False)
    else:
        monkeypatch.setenv("NETDRYRUN_DEBUG", value)
    assert runner._debug() is env


# ----------------------------------------------------------------------------------------------- run(): scenarios

def _recovering(e, fault_node="r1", gone_until=None):
    """r3's route 10.1.0.0/24 is lost while a link is down (and until `gone_until` after restore)."""
    lab = e.lab

    def routes(t, p):
        if p != "10.1.0.0/24":
            return True
        down = [ev for ev in lab.events if ev[0] == "link"]
        if down and down[-1][3] is False:
            return False
        if gone_until is not None and down and t < gone_until:
            return False
        return True

    e.drivers["r3"].routes_ = {"default": routes}


def test_scenario_recovery_is_checked(monkeypatch):
    e = make(monkeypatch)
    _recovering(e, gone_until=10 ** 6)
    base = route("base", node="r3", prefix="10.1.0.0/24")
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] other", node="r2")])
    rep = e.run([base], [sc], settle=10, hold=10)
    assert rep is not None and rep.status == "failed"
    names = [r.check.name for r in rep.results]
    assert names == ["base", "[s] other", "[after s] recovers: base"]
    stuck = rep.results[-1]
    assert not stuck.passed and stuck.check.type == "route" and stuck.check.params["node"] == "r3"
    assert e.results[-1] is stuck and len(e.results) == 3


def test_recovered_network_adds_nothing(monkeypatch):
    e = make(monkeypatch)
    _recovering(e)
    base = route("base", node="r3", prefix="10.1.0.0/24")
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] other", node="r2")])
    rep = e.run([base], [sc], settle=10, hold=10)
    assert rep.status == "passed" and [r.check.name for r in rep.results] == ["base", "[s] other"]


def test_only_passing_positive_checks_must_recover(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24"}
    broken = route("broken", prefix="10.5.0.0/16", timeout=6)       # failed before the scenario
    guard = leak("guard")                                           # passed, but post-convergence
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r2")])
    rep = e.run([broken, guard], [sc], settle=10, hold=10)
    assert [r.check.name for r in rep.results] == ["broken", "guard", "[s] x"]
    # the leak guard is not re-run as a "recovery" check: it only matters after convergence
    e = make(monkeypatch)
    e.drivers["r1"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24" or e.lab.link_events()}
    rep = e.run([guard], [sc], settle=10, hold=10)
    assert rep.status == "passed" and [r.check.name for r in rep.results] == ["guard", "[s] x"]


def test_later_scenarios_are_skipped_when_the_network_does_not_recover(monkeypatch):
    e = make(monkeypatch)
    _recovering(e, gone_until=10 ** 6)
    base = route("base", node="r3", prefix="10.1.0.0/24")
    s1 = Scenario("s1", [Fault("link_down", "r1", "eth1")], [route("[s1] x", node="r2")])
    s2 = Scenario("s2", [Fault("link_down", "r2", "eth2")], [route("[s2] y", node="r2")])
    rep = e.run([base], [s1, s2], settle=10, hold=10)
    assert [r.check.name for r in rep.results] == ["base", "[s1] x", "[after s1] recovers: base"]
    assert ("r2", "eth2", False) not in e.lab.link_events()


def test_scenario_results_are_reported(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] pos", node="r2"), leak("[s] neg", node="r2")])
    e.drivers["r2"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24"}
    rep = e.run([route("base")], [sc], settle=10, hold=10)
    assert rep.status == "passed" and [r.check.name for r in rep.results] == ["base", "[s] pos", "[s] neg"]
    assert [r.check.name for r in e.results] == ["base", "[s] pos", "[s] neg"]


# ----------------------------------------------------------------------------------------------- run_scenario

def direct(e, sc, settle=10, hold=10, driver_for=None):
    return runner.run_scenario(e.lab, sc, e.drivers, settle=settle, hold=hold, on_result=e.results.append,
                               log=e.logs.append, driver_for=driver_for)


def test_link_down_is_applied_and_restored(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")])
    results = direct(e, sc)
    assert e.lab.link_events() == [("r1", "eth1", False), ("r1", "eth1", True)]
    assert ("require", "r1") in e.lab.events
    assert [r.passed for r in results] == [True] and len(e.results) == 1
    assert e.clock.sleeps[0] == 10 and e.clock.sleeps[-1] == 10   # settle before the checks and after restoring


def test_node_isolated_downs_every_data_interface(monkeypatch):
    e = make(monkeypatch)
    direct(e, Scenario("s", [Fault("node_isolated", "r1")], [route("x", node="r3")]))
    assert e.lab.link_events() == [("r1", "eth1", False), ("r1", "eth2", False), ("r1", "eth1", True),
                                   ("r1", "eth2", True)]


def test_inject_routes_is_applied_and_restored(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"], as_path=[65009]),
                        Fault("link_down", "r1", "eth1")], [route("x", node="r3")])
    direct(e, sc)
    [inj] = e.injections
    assert (inj.node, inj.prefixes, inj.as_path, inj.applied, inj.restored) == ("r2", ["10.66.0.0/16"], [65009], True, 1)
    assert ("r1", "eth1", False) in e.lab.link_events()        # a later fault still applies
    assert e.clock.sleeps.count(10) == 2


def test_inject_only_scenario_settles_after_restoring(monkeypatch):
    e = make(monkeypatch)
    direct(e, Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x", node="r3")]))
    assert e.clock.sleeps[0] == 10 and e.clock.sleeps[-1] == 10 and e.clock.sleeps.count(10) == 2
    assert not e.lab.link_events()


def test_scenario_restores_even_when_a_check_crashes(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].on_call = lambda: (_ for _ in ()).throw(KeyboardInterrupt())
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"]), Fault("link_down", "r1", "eth1")],
                  [route("x", node="r3")])
    with pytest.raises(KeyboardInterrupt):
        direct(e, sc)
    assert ("r1", "eth1", True) in e.lab.link_events() and e.injections[0].restored == 1


def test_a_link_that_cannot_be_restored_stops_the_run(monkeypatch):
    e = make(monkeypatch)
    e.lab.set_link_error = {("r1", "eth1", True): LabError("stuck")}
    with pytest.raises(LabError):
        direct(e, Scenario("s", [Fault("link_down", "r1", "eth1"), Fault("link_down", "r2", "eth2")],
                           [route("x", node="r3")]))
    assert ("r2", "eth2", True) in e.lab.link_events()        # the other link is still restored


def test_an_injection_that_cannot_be_restored_stops_the_run(monkeypatch):
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x", node="r3")])
    orig = runner.RouteInjection

    class Failing(orig):
        def restore(self):
            raise LabError("stuck")

    monkeypatch.setattr(runner, "RouteInjection", Failing)
    with pytest.raises(LabError):
        direct(e, sc)


def test_scenario_waits_for_bgp_over_the_downed_link_and_settles(monkeypatch):
    e = make(monkeypatch)
    lab = e.lab

    def down_after(delay):
        def f(t):
            ev = [x for x in lab.events if x[0] == "link" and not x[3]]
            return "idle" if ev and t >= ev[0][4] + delay else "established"
        return f

    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": down_after(20)(t)}}
    e.drivers["r2"].neighbors = {"default": lambda t: {"10.0.12.1": down_after(20)(t)}}
    direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3", timeout=60)]))
    assert e.clock.sleeps[:8] == [3, 3, 3, 3, 3, 3, 3, 10]   # seen down at t=21, then the settle


def test_scenario_checks_in_another_vrf_watch_that_vrf(monkeypatch):
    e = make(monkeypatch)
    for n in ("r1", "r2"):
        e.drivers[n].neighbors = {"default": {}, "blue": {}}
    direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3", vrf="blue")]))
    e.drivers["r3"].routes_["blue"] = always
    assert ("bgp_neighbors", "blue", 0.0) in e.drivers["r1"].calls
    assert ("bgp_neighbors", "default", 0.0) in e.drivers["r1"].calls


def test_scenario_negative_checks_are_held(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24" or t >= 10 + 3 + 3 + 8}
    results = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")],
                                 [route("pos", node="r3"), leak("neg", node="r3")]), hold=10)
    assert [r.check.name for r in results] == ["pos", "neg"] and [r.passed for r in results] == [True, False]
    assert [r.check.name for r in e.results] == ["pos", "neg"]
    e = make(monkeypatch)
    # positives: settle 10, reach 3, hold 20 (to t=33); then the leak guard holds 20 s and the leak comes at 48
    e.drivers["r3"].routes_ = {"default": lambda t, p: p == "10.9.9.0/24" or t >= 10 + 3 + 20 + 15}
    results = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")],
                                 [route("pos", node="r3"), leak("neg", node="r3")]), hold=20)
    assert [r.passed for r in results] == [True, False]


def test_scenario_positive_that_fails_in_the_hold(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: t < 10 + 3 + 6}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=10)
    assert not r.passed and isinstance(r.detail, str) and r.detail != r.history[-1]["detail"]
    assert r.attempts == 2 + 3 and r.samples_passed == 2 + 2 and r.samples_unready == 0
    assert [h["t"] for h in r.history] == [0.0, 3.0, 3.0, 6.0, 9.0] and r.duration == 9.0 and iso(r.started)


def test_scenario_positive_merged_fields(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: t >= 10 + 3}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=10)
    assert r.passed and r.attempts == 3 + 5 and r.samples_passed == 2 + 5
    assert [h["t"] for h in r.history] == [0.0, 3.0, 6.0, 6.0, 9.0, 12.0, 15.0, 16.0]
    assert r.duration == 16.0 and [x.check.name for x in e.results] == ["pos"]


def test_scenario_positive_unready_samples_are_added(monkeypatch):
    e = make(monkeypatch)
    calls = {"n": 0}

    def flaky(t, p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DriverError("not yet")
        return t < 10 + 6 + 3 or True

    e.drivers["r3"].routes_ = {"default": flaky}
    e.drivers["r3"].routes_ = {"default": lambda t, p: (_ for _ in ()).throw(DriverError("x")) if t < 10 + 1 else True}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=3)
    assert r.passed and r.samples_unready == 1 and r.attempts == 3 + 2


def test_scenario_positive_long_history(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": lambda t, p: t >= 10 + 90}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1", )], [route("pos", node="r3", timeout=200)]),
                 hold=90)
    assert r.passed and len(r.history) == 50 and r.attempts == 32 + 31


def test_scenario_with_fractional_timing(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r3"].routes_ = {"default": always}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=1.25,
                 settle=0.25)
    assert r.passed and r.duration == 4.2 and r.history[-1]["t"] == 4.2


def test_run_scenario_without_driver_for_builds_missing_drivers(monkeypatch):
    e = make(monkeypatch)
    drivers = dict(e.drivers)
    e.drivers = {"r3": drivers["r3"]}
    results = runner.run_scenario(e.lab, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]),
                                  e.drivers, settle=10, hold=10)
    assert [r.passed for r in results] == [True]
    assert sorted(e.for_node_calls) == [("r1", None), ("r2", None)] and set(e.drivers) == {"r1", "r2", "r3"}
    # a driver already there is not rebuilt
    e.for_node_calls.clear()
    runner.run_scenario(e.lab, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]),
                        e.drivers, settle=10, hold=10)
    assert e.for_node_calls == []


# ----------------------------------------------------------------------------------------------- sessions over links

def sessions(e, links, vrfs=("default",)):
    return runner._sessions_over_links(e.lab, links, list(vrfs), lambda n: e.drivers[n])


def test_sessions_over_links_on_the_faulted_node(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established", "10.0.12.1": "established",
                                             "10.9.9.9": "established", "eth1": "established",
                                             "10.0.12.3": "idle", "eth2": "established"}}
    e.drivers["r2"].neighbors = {"default": {}}
    assert sessions(e, [("r1", "eth1")]) == [("r1", "default", "10.0.12.2"), ("r1", "default", "eth1")]


def test_sessions_over_links_on_the_far_end(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {}}
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established", "eth1": "established",
                                             "10.0.12.2": "established", "10.0.12.5": "established",
                                             "eth2": "established"},
                                 "blue": {"10.0.12.1": "established", "eth1": "active"}}
    assert sessions(e, [("r1", "eth1")], ("default", "blue")) == [
        ("r2", "blue", "10.0.12.1"), ("r2", "default", "10.0.12.1"), ("r2", "default", "eth1")]
    assert ("bgp_neighbors", "blue", 0.0) in e.drivers["r2"].calls


def test_sessions_over_links_per_vrf_and_unreadable(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"blue": {"10.0.12.2": "established"}}   # no default VRF answer: nothing there
    e.drivers["r2"].neighbors_error = DriverError("no bgpd")
    assert sessions(e, [("r1", "eth1")], ("default", "blue")) == [("r1", "blue", "10.0.12.2")]
    calls = [c for c in e.drivers["r1"].calls if c[0] == "bgp_neighbors"]
    assert [c[1] for c in calls] == ["default", "blue"]                  # each (node, vrf) read once


def test_sessions_over_links_ipv6_and_scoped_keys(monkeypatch):
    e = make(monkeypatch)
    e.lab.addresses = {("r1", "eth1"): ["2001:db8:12::1/64"]}
    e.drivers["r1"].neighbors = {"default": {"2001:db8:12::2": "established", "fe80::2%eth1": "established"}}
    e.drivers["r2"].neighbors = {"default": {"2001:db8:12::1%eth1": "established"}}
    assert sessions(e, [("r1", "eth1")]) == [("r1", "default", "2001:db8:12::2"),
                                             ("r2", "default", "2001:db8:12::1%eth1")]


# ----------------------------------------------------------------------------------------------- fault visible

SC = Scenario("s", [Fault("link_down", "r1", "eth1")], [])


def wait(e, watch, timeout):
    return runner._wait_fault_visible(watch, lambda n: e.drivers[n], timeout, SC, log=e.logs.append)


def test_wait_fault_visible_returns_when_every_session_is_down(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "idle" if t >= 4 else "established"}}
    e.drivers["r2"].neighbors = {"blue": lambda t: {"10.0.12.1": "idle" if t >= 7 else "established"}}
    wait(e, [("r1", "default", "10.0.12.2"), ("r2", "blue", "10.0.12.1")], 30)
    assert e.clock.now == 9 and e.clock.sleeps == [3, 3, 3]


def test_wait_fault_visible_session_gone_counts_as_down(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {} if t >= 3 else {"10.0.12.2": "established"}}
    wait(e, [("r1", "default", "10.0.12.2")], 30)
    assert e.clock.now == 3


def test_wait_fault_visible_times_out(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}}
    with pytest.raises(LabError):
        wait(e, [("r1", "default", "10.0.12.2")], 10)
    assert e.clock.sleeps == [3, 3, 3, 1] and e.clock.now == 10


def test_wait_fault_visible_unreadable_state_is_not_proof(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("cli down")
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "idle"}}
    with pytest.raises(LabError):
        wait(e, [("r1", "default", "10.0.12.2"), ("r2", "default", "10.0.12.1")], 6)


def test_wait_fault_visible_with_nothing_to_watch(monkeypatch):
    e = make(monkeypatch)
    wait(e, [], 30)
    assert e.clock.sleeps == [] and e.logs


def test_wait_fault_visible_fractional_deadline(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}}
    with pytest.raises(LabError):
        wait(e, [("r1", "default", "10.0.12.2")], 3.5)
    assert e.clock.sleeps == [3, 0.5]


# ----------------------------------------------------------------------------------------------- the BGP gate

def gate(e, negatives, all_checks=None, positive_results=()):
    return runner._bgp_convergence_gate(negatives, all_checks if all_checks is not None else negatives, e.drivers,
                                        log=e.logs.append, positive_results=list(positive_results))


def test_gate_needs_two_identical_established_samples(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established", "10.0.13.3": "established"}}
    assert gate(e, [leak("n")]) == {} and e.clock.sleeps == [3]


def test_gate_waits_for_prefix_counts_to_settle(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": ("established", {"ipv4-unicast": min(int(t), 6)})}}
    assert gate(e, [leak("n")]) == {}
    assert e.clock.now == 9   # counts 0, 3, 6, 6


def test_gate_counts_that_never_settle_dont_block(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": ("established", {"ipv4-unicast": int(t)})}}
    assert gate(e, [leak("n", timeout=9)]) == {} and e.clock.now == 9


def test_gate_down_sample_resets_the_streak(monkeypatch):
    e = make(monkeypatch)
    states = {0: "established", 3: "idle", 6: "established", 9: "established"}
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": states.get(round(t), "established")}}
    assert gate(e, [leak("n")]) == {} and e.clock.now == 9


def test_gate_unreadable_sample_resets_the_streak(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": up("10.0.12.2")["default"]}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("x") if round(t) == 3 else None
    assert gate(e, [leak("n")]) == {} and e.clock.now == 9


def test_gate_blocks_a_node_whose_session_never_comes_up(monkeypatch):
    e = make(monkeypatch)
    e.clock.t += 0.25
    e.drivers["r1"].neighbors = {"default": lambda t: {"10.0.12.2": "established" if t < 3 else "active"}}
    a, b = leak("a", timeout=7.5), leak("b", timeout=9.75)
    blocked = gate(e, [a, b])
    assert set(blocked) == {id(a), id(b)}
    r = blocked[id(a)]
    assert r.check is a and r.passed is False and r.attempts == 5 and r.duration == 9.8 and iso(r.started)
    assert r.evidence == [] and r.samples_passed == 0 and r.samples_unready == 0
    assert [h["passed"] for h in r.history] == [True, False, False, False, False]
    assert [h["t"] for h in r.history] == [0.0, 3.0, 6.0, 9.0, 9.8]
    assert e.clock.sleeps == [3, 3, 3, 0.75]


def test_gate_blocked_result_counts_unready_samples(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("x") if t >= 3 else None
    [r] = gate(e, [leak("a", timeout=9)]).values()
    assert r.samples_unready == 3 and r.attempts == 4
    assert [bool(h.get("unready")) for h in r.history] == [False, True, True, True]
    assert all(h["passed"] is False for h in r.history)


def test_gate_keeps_the_last_50_samples(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    [r] = gate(e, [leak("a", timeout=300)]).values()
    assert r.attempts == 101 and len(r.history) == 50 and r.history[0]["t"] == 153.0


def test_gate_reads_each_checks_vrf(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}, "blue": {"10.0.12.2": "established"}}
    assert gate(e, [leak("n", vrf="blue", timeout=9)]) == {}
    assert {c[1] for c in e.drivers["r1"].calls} == {"blue"}
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "established"}, "blue": {"10.0.12.2": "active"}}
    assert len(gate(e, [leak("n", vrf="blue", timeout=9)])) == 1


def test_gate_ignores_sessions_expected_down_in_their_vrf(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"blue": {"10.0.12.2": "established", "10.0.99.9": "idle"}}
    down = chk("bgp_session", "gone", neighbor="10.0.99.9", state="down", vrf="blue")
    neg = leak("n", vrf="blue", timeout=9)
    assert gate(e, [neg], [down, neg]) == {}
    # the same neighbor expected down in another VRF doesn't excuse it here
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"blue": {"10.0.12.2": "established", "10.0.99.9": "idle"}}
    other = chk("bgp_session", "gone", neighbor="10.0.99.9", state="down")
    assert len(gate(e, [neg], [other, neg])) == 1


def test_gate_a_session_expected_established_still_blocks(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    want_up = chk("bgp_session", "up", neighbor="10.0.12.2", state="established")
    plain = chk("bgp_session", "up2", neighbor="10.0.12.2")
    prefix_check = chk("bgp_prefixes", "p", neighbor="10.0.12.2", min=1)
    neg = leak("n", timeout=9)
    assert len(gate(e, [neg], [want_up, plain, prefix_check, neg])) == 1


def test_gate_skips_nodes_whose_positive_checks_never_got_state(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    dead = Result(route("p"), False, "x", 3, 9.0, "t", samples_unready=3)
    neg = leak("n", timeout=9)
    assert gate(e, [neg], positive_results=[dead]) == {} and e.drivers["r1"].calls == []
    for alive in (Result(route("p"), False, "x", 3, 9.0, "t", samples_unready=2),
                  Result(route("p"), False, "x", 0, 9.0, "t", samples_unready=0)):
        e = make(monkeypatch)
        e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
        assert len(gate(e, [neg], positive_results=[alive])) == 1
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    other_node = Result(route("p", node="r2"), False, "x", 3, 9.0, "t", samples_unready=3)
    assert len(gate(e, [neg], positive_results=[other_node])) == 1


def test_gate_ping_only_node_without_bgp_is_not_waited_for(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=60)
    assert gate(e, [p]) == {} and e.clock.now == 0 and not e.logs


def test_gate_node_that_errors_first_but_has_other_checks_is_waited_for(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("starting") if t < 1 else None
    assert len(gate(e, [leak("n", timeout=9)])) == 1 and e.clock.now == 9
    # a ping-only node that answers first and errors later is still waited for
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}
    e.drivers["r1"].neighbors_error = lambda t: DriverError("crash") if t >= 3 else None
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=9)
    assert len(gate(e, [p])) == 1 and e.clock.now == 9


def test_gate_node_that_never_answers_goes_ahead_with_a_warning(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")
    assert gate(e, [leak("n", timeout=9)]) == {} and e.clock.now == 9 and len(e.logs) == 1


def test_gate_groups_are_independent(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")         # sorted first, errors every round
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    e.drivers["r3"].neighbors = {"default": {"10.0.23.2": "active"}}
    a, b, c = leak("a", timeout=9), leak("b", node="r2", timeout=30), leak("c", node="r3", timeout=6)
    blocked = gate(e, [a, b, c])
    assert set(blocked) == {id(c)}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0]
    assert e.clock.sleeps == [3, 3, 3]


def test_gate_with_no_negatives(monkeypatch):
    e = make(monkeypatch)
    assert gate(e, []) == {} and e.clock.sleeps == []


# ----------------------------------------------------------------------------------------------- small helpers

def test_check_duration():
    for ok in (0, 0.0, 5, 1e12):
        runner._check_duration("x", ok)
    for bad in (-0.1, float("inf"), float("nan"), True, False, "1", None, [1]):
        with pytest.raises(runner.RunError):
            runner._check_duration("x", bad)


def test_ip():
    assert runner._ip("10.0.0.1") == ipaddress.ip_address("10.0.0.1")
    assert runner._ip("fe80::1%eth1") == ipaddress.ip_address("fe80::1")
    assert runner._ip("eth1") is None


def test_now_is_utc():
    assert iso(runner._now())


def test_error_report(tmp_path):
    rep = runner.error_report(tmp_path, "bad")
    assert rep.status == "error" and rep.exit_code == 2 and rep.error == "bad"
    assert rep.config.path == tmp_path / "netdryrun.yml" and rep.config.checks == [] and rep.config.timeout == 0.0
    assert rep.config.lab == Path() and iso(rep.started) and rep.started == rep.finished
    f = tmp_path / "x.yml"
    assert runner.error_report(f, "e").config.path == f


def test_signals():
    assert runner.signal_name(signal.SIGTERM) == "SIGTERM" and runner.signal_name(999) == "signal 999"
    assert runner.signal_exit_code(signal.SIGINT) == 130
    e = runner.Interrupted(signal.SIGHUP)
    assert e.signum == signal.SIGHUP and isinstance(e, KeyboardInterrupt) and str(e) == "SIGHUP"
    with pytest.raises(runner.Interrupted) as exc:
        runner._raise_interrupted(signal.SIGTERM, None)
    assert exc.value.signum == signal.SIGTERM
    assert runner._catchable_signals("SIGTERM", "NOPE") == [signal.SIGTERM]


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX signals")
def test_install_signal_handlers(monkeypatch):
    seen = {}
    monkeypatch.setattr(runner.signal, "signal", lambda s, h: seen.__setitem__(s, h))
    runner.install_signal_handlers()
    assert seen == {signal.SIGTERM: runner._raise_interrupted, signal.SIGHUP: runner._raise_interrupted}
    seen.clear()
    import threading
    t = threading.Thread(target=runner.install_signal_handlers)
    t.start()
    t.join()
    assert seen == {}


# ----------------------------------------------------------------------------------------------- loading a config

@pytest.mark.parametrize("text", [
    "lab: t.clab.yml\ntimeout: soon\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\n",
    "lab: t.clab.yml\nchecks: {a: 1}\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\nscenarios: {a: 1}\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\nnodes: [r1]\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\nnodes: {r1: frr}\n",
    "lab: t.clab.yml\nchecks: [{type: route, node: r1, prefix: 10.0.0.0/8}]\n  bad: [\n",
    "[1, 2]\n",
])
def test_load_config_errors_are_config_errors(tmp_path, text):
    (tmp_path / "t.clab.yml").write_text("name: t\n")
    (tmp_path / "netdryrun.yml").write_text(text)
    with pytest.raises(runner.ConfigError):
        runner.load_config(tmp_path)


def test_shape_problem(tmp_path):
    p = tmp_path / "netdryrun.yml"
    cases = {
        "timeout: soon\n": True, "timeout: '30'\n": False, "timeout: 30\n": False, "timeout: [1]\n": True,
        "timeout: null\n": False, "checks: {}\n": True, "checks: []\n": False, "scenarios: 1\n": True,
        "scenarios: []\n": False, "nodes: []\n": True, "nodes: {}\n": False, "nodes: {r1: x}\n": True,
        "nodes: {r1: null}\n": False, "nodes: {r1: {driver: frr}}\n": False, "[1]\n": False, "a: [\n": False,
        "nodes: null\n": False,
    }
    for text, problem in cases.items():
        p.write_text(text)
        assert (runner._shape_problem(p) is not None) is problem, text


def test_yaml_problem():
    import yaml
    try:
        yaml.safe_load("a: [\n")
    except yaml.YAMLError as e:
        assert runner._yaml_problem(e)
    assert runner._yaml_problem(yaml.YAMLError("plain"))


def test_config_path(tmp_path):
    assert runner._config_path(tmp_path) == tmp_path / "netdryrun.yml"
    assert runner._config_path(tmp_path / "x.yml") == tmp_path / "x.yml"


# ----------------------------------------------------------------------------------------------- more edges

def test_scenario_drivers_built_mid_scenario_get_their_override(monkeypatch):
    """r2 has no check of its own: its driver is first needed to watch the BGP session over the downed link."""
    e = make(monkeypatch)
    sc = Scenario("s", [Fault("link_down", "r1", "eth1")], [route("[s] x", node="r3")])
    rep = e.run([route("a")], [sc], drivers_cfg={"r2": "srlinux"})
    assert rep.status == "passed"
    assert ("r2", "srlinux") in e.for_node_calls and ("r2", None) not in e.for_node_calls


def test_one_signal_during_cleanup(monkeypatch):
    e = make(monkeypatch)

    @contextmanager
    def deferred():
        yield [signal.SIGTERM]

    monkeypatch.setattr(runner, "_signals_deferred", deferred)
    with pytest.raises(runner.Interrupted) as exc:
        e.run([route("a")], deploy=True)
    assert exc.value.signum == signal.SIGTERM and exc.value.report.status == "error"


def test_gate_down_group_does_not_stop_the_round(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors = {"default": {"10.0.12.2": "active"}}       # sorted first, down every round
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    a, b = leak("a", timeout=6), leak("b", node="r2", timeout=30)
    assert set(gate(e, [a, b])) == {id(a)}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0]


def test_gate_discarded_ping_node_does_not_stop_the_round(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r1"].neighbors_error = DriverError("no bgpd")              # sorted first, ping-only: discarded
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    p = chk("ping", "p", target="10.9.9.9", expect="failure", timeout=60)
    assert gate(e, [p, leak("b", node="r2", timeout=30)]) == {}
    assert [x[2] for x in e.drivers["r2"].calls] == [0.0, 3.0] and e.clock.now == 3


def test_inject_only_scenario_downs_no_link(monkeypatch):
    e = make(monkeypatch)
    e.drivers["r2"].neighbors = {"default": {"10.0.12.1": "established"}}
    direct(e, Scenario("s", [Fault("inject_routes", "r2", prefixes=["10.66.0.0/16"])], [route("x", node="r3")]))
    assert ("require", "r2") not in e.lab.events and not e.lab.link_events()
    assert not any(c[0] == "bgp_neighbors" for c in e.drivers["r2"].calls)


def test_scenario_watches_only_the_vrfs_its_checks_use(monkeypatch):
    e = make(monkeypatch)
    direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("x", node="r3")]))
    assert {c[1] for c in e.drivers["r1"].calls if c[0] == "bgp_neighbors"} == {"default"}


def test_scenario_positive_unready_in_the_hold_is_counted(monkeypatch):
    e = make(monkeypatch)

    def routes(t, p):
        if t >= 10 + 3 + 3:
            raise DriverError("cli gone")
        return True

    e.drivers["r3"].routes_ = {"default": routes}
    [r] = direct(e, Scenario("s", [Fault("link_down", "r1", "eth1")], [route("pos", node="r3")]), hold=10)
    assert not r.passed and r.samples_unready == 1 and r.attempts == 2 + 2


def test_load_config_turns_any_crash_into_a_config_error(monkeypatch, tmp_path):
    (tmp_path / "netdryrun.yml").write_text("checks: []\n")

    def boom(path):
        raise RuntimeError("bug")

    monkeypatch.setattr(runner, "load", boom)
    with pytest.raises(runner.ConfigError):
        runner.load_config(tmp_path)
    with pytest.raises(runner.ConfigError):
        runner.load_config(tmp_path / "netdryrun.yml")


def test_config_files_are_read_as_utf8(monkeypatch, tmp_path):
    import codecs
    seen = []
    orig = Path.read_text

    def read_text(self, encoding=None, errors=None):
        seen.append(encoding)
        return orig(self, encoding="utf-8", errors=errors)

    monkeypatch.setattr(Path, "read_text", read_text)
    (tmp_path / "netdryrun.yml").write_text("timeout: soon\n", encoding="utf-8")
    runner._shape_problem(tmp_path / "netdryrun.yml")
    assert seen and all(enc is not None and codecs.lookup(enc).name == "utf-8" for enc in seen)
