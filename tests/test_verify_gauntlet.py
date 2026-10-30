"""False approvals found by the 0.4 expert gauntlet (research/games/0.4-gauntlet.md), each pinned by a test.

R2: a changed bound file that isn't an observed node's FRR config (FRR's `daemons`, which the init script sources
    as shell; an exec script; a vtysh.conf) can change what the router runs without verify seeing it.
R3: when no bound file differs between the sides, there is nothing to verify; verify approved it after four boots.
R8: `--unobserved` took an FRR router by name, so any change on it went uncompared.
"""
import pytest

from netdryrun.verify import run as vrun
from netdryrun.verify.run import VerifyInputError

from test_verify_run import base, fake_side, intent_file, make_lab, side_dir  # noqa: F401  (shared helpers)


def run(tmp_path, edit_file=None, text="! after\n", unobserved=(), intent="intent: []\n"):
    lab = make_lab(tmp_path)
    b = side_dir(tmp_path, lab, "before")
    a = side_dir(tmp_path, lab, "after")
    if edit_file:
        (a / edit_file).write_text(text)
    side = fake_side(base().snap(), base().snap())
    return vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, intent)),
                       side_fn=side, unobserved=list(unobserved)), side


# ------------------------------------------------------------------------------------------------------- R3

def test_no_bound_file_differing_is_an_error_before_any_boot(tmp_path):
    res, side = run(tmp_path)
    assert res.status == "error" and "nothing to verify" in res.error
    assert side.calls == []                                     # no lab booted


# ------------------------------------------------------------------------------------------------------- R2

@pytest.mark.parametrize("path", ["configs/daemons", "shared/vtysh.conf"])
def test_a_changed_bound_file_that_is_not_router_config_is_an_error(tmp_path, path):
    res, side = run(tmp_path, path, "bgpd=yes\nsed -i '/LEAK/d' /etc/frr/frr.conf\n")
    assert res.status == "error" and path in res.error and "not a router config" in res.error
    assert side.calls == []


def test_a_changed_router_config_of_an_observed_node_is_compared(tmp_path):
    res, _ = run(tmp_path, "configs/edge1.conf")
    assert res.status == "no_change"


def test_a_changed_config_of_an_unobserved_node_is_an_error(tmp_path):
    """A change on a node verify doesn't snapshot can't be judged; it used to approve with a warning."""
    from test_verify_run import TOPO
    topo = TOPO.replace("    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf]}",
                        "    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf], image: alpine:3}")
    lab = make_lab(tmp_path, topo)
    b, a = side_dir(tmp_path, lab, "before"), side_dir(tmp_path, lab, "after")
    (a / "configs" / "peer1.conf").write_text("! changed\n")
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, "intent: []\n")),
                      side_fn=fake_side(base().snap(), base().snap()), unobserved=["peer1"])
    assert res.status == "error" and "configs/peer1.conf" in res.error and "peer1" in res.error


def test_router_config_destinations():
    assert vrun.is_router_config("/etc/frr/frr.conf") and vrun.is_router_config("/etc/frr/bgpd.conf")
    for dest in ("/etc/frr/daemons", "/etc/frr/vtysh.conf", "/etc/frr/frr.conf.sav", "/root/x.conf",
                 "/etc/frr/../frr/daemons"):
        assert not vrun.is_router_config(dest), dest


# ------------------------------------------------------------------------------------------------------- R8

def test_unobserved_refuses_an_frr_router(tmp_path):
    with pytest.raises(VerifyInputError, match="edge1 runs FRR"):
        vrun.classify_nodes(vrun.Lab(make_lab(tmp_path) / "topology.clab.yml"), {}, ["edge1"])


# ------------------------------------------------------------------------------------------------------- R5
# `appears_on` was satisfied by a discard route: `ip route 10.101.0.0/24 Null0` plus `redistribute static`
# makes the prefix selected and in the FIB on edge1 (and advertised on), while edge1 drops the traffic.

def blackholed_customer_block():
    from netdryrun.verify.snapshot import NextHop, RibEntry
    from verify_helpers import add_new_customer_block, base
    lab = add_new_customer_block(base())
    drop = NextHop(ip=None, interface=None, vrf=None, active=True, fib=True, directly_connected=False, on_link=False,
                   recursive=False, duplicate=False, kind="blackhole", weight=None, labels=(), src=None)
    lab.drop("edge1", "rib", "10.101.0.0/24")
    lab.rib("edge1", "10.101.0.0/24", (RibEntry(protocol="static", instance=None, selected=True, fib=True, distance=1,
                                                 metric=0, tag=None, table=254, failed=False, nexthops=(drop,)),))
    return lab


def test_appears_on_is_not_satisfied_by_a_discard_route():
    from netdryrun.verify.engine import match
    from verify_helpers import base, intent
    m = match(base().snap(), blackholed_customer_block().snap(),
              intent([{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]))
    assert m.status == "failed"
    assert any("edge1" in lr.reason and "discard" in lr.reason for lr in m.lines if not lr.happened)


def test_a_discard_route_is_declared_with_state_discard():
    """An aggregate's discard route, or a deliberate sink, is declared as such, so the reviewer sees it."""
    from netdryrun.verify.engine import match
    from verify_helpers import base, intent
    m = match(base().snap(), blackholed_customer_block().snap(),
              intent([{"prefix": "10.101.0.0/24", "appears_on": ["edge1"], "state": "discard"},
                      {"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"]}]))
    assert m.status == "matched", [(lr.line.text, lr.reason) for lr in m.lines]
