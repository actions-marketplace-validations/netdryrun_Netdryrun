"""The convergence-stable snapshot loop, on a fake clock."""
from dataclasses import replace

import pytest

from netdryrun.verify.converge import Inconclusive, SnapshotUnreadable, stable_snapshot
from netdryrun.verify.frr import CommandFailed
from netdryrun.verify.snapshot import SnapshotError
from verify_helpers import base, path, session


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def seq(*snaps):
    """A collect() that returns the given snapshots (or raises the given exceptions) in turn, then repeats
    the last one."""
    items = list(snaps)

    def collect():
        x = items.pop(0) if len(items) > 1 else items[0]
        if isinstance(x, Exception):
            raise x
        return x
    return collect


def moved(n):
    lab = base()
    lab.path("edge1", "203.0.113.0/24", "10.0.2.2", path(as_path="65002", next_hop="10.0.2.2", med=n))
    return lab.snap()


def run(collect, settle=10, timeout=120):
    clock = Clock()
    return stable_snapshot(collect, settle=settle, timeout=timeout, clock=clock, sleep=clock.sleep), clock


def test_two_identical_snapshots_settle_apart_are_stable():
    a, b = moved(1), moved(2)
    got, clock = run(seq(a, b, b))
    assert got is not None and not isinstance(got, Inconclusive) and got.items() == b.items()
    assert clock.t == 20          # three samples, settle apart


def test_moving_state_is_inconclusive_and_names_what_moved():
    n = iter(range(1000))
    got, clock = run(lambda: moved(next(n)), timeout=60)
    assert isinstance(got, Inconclusive) and got.moving and any("203.0.113.0/24" in m for m in got.moving)
    assert clock.t <= 60


def test_prefix_counts_must_be_stable_too():
    a, b = base(), base()
    s = b.get("edge1", "session", neighbor="10.0.2.2")
    b.session("edge1", "10.0.2.2", replace(s, prefix_counts=(("ipv4-unicast", 9),)))
    assert a.snap().items() == b.snap().items()                    # the diff ignores counts...
    got, _ = run(seq(a.snap(), b.snap(), a.snap(), b.snap()), timeout=35)
    assert isinstance(got, Inconclusive)                           # ...stability doesn't


def test_sessions_stably_down_are_stable():
    lab = base()
    lab.session("edge1", "10.0.9.2", session(None, state="active"))
    got, _ = run(seq(lab.snap()))
    assert not isinstance(got, Inconclusive)


def test_failed_commands_are_retried_then_unreadable():
    good = base().snap()
    got, _ = run(seq(CommandFailed("vtysh: bgpd not up"), CommandFailed("again"), good, good))
    assert not isinstance(got, Inconclusive)
    with pytest.raises(SnapshotUnreadable):
        run(seq(CommandFailed("vtysh: bgpd not up")), timeout=30)


def test_schema_errors_stop_at_once():
    calls = []

    def collect():
        calls.append(1)
        raise SnapshotError("unknown field")
    with pytest.raises(SnapshotError):
        run(collect)
    assert len(calls) == 1


def test_a_node_with_an_empty_rib_is_not_ready():
    lab = base()
    for k in [k for k in lab.items["up1"] if k.kind == "rib"]:
        del lab.items["up1"][k]
    got, _ = run(seq(lab.snap()), timeout=40)
    assert isinstance(got, Inconclusive) and any("up1" in m for m in got.moving)
