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


# ------------------------------------------------------------------------------------------------------- R1
# Every IPv6 link-local next hop was compared as `fe80::` (containerlab's random MACs change it per boot), so a
# link-local next hop set in config (a route-map `set ipv6 next-hop local`, a static route) with a typo was
# invisible. Now verify reads every lab node's link-local addresses: one a lab node owns is named by its owner
# (stable across boots); any other keeps its address, so a typo is a difference.

IP_ADDR = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN qlen 1000
2: eth0@if71: <BROADCAST,MULTICAST,UP,LOWER_UP,M-DOWN> mtu 1500 qdisc noqueue state UP
    inet6 fe80::42:acff:fe14:1403/64 scope link
       valid_lft forever preferred_lft forever
3: eth1@if70: <BROADCAST,MULTICAST,UP,LOWER_UP,M-DOWN> mtu 9500 qdisc noqueue state UP
    inet6 fe80::a8c1:abff:feb5:4b08/64 scope link
       valid_lft forever preferred_lft forever
    inet6 fe80::1/64 scope link
       valid_lft forever preferred_lft forever
"""


def test_link_local_addresses_are_read_per_interface():
    from netdryrun.verify import frr
    assert frr.parse_link_local(IP_ADDR, "peer1") == {"fe80::42:acff:fe14:1403": "peer1:eth0",
                                                      "fe80::a8c1:abff:feb5:4b08": "peer1:eth1",
                                                      "fe80::1": "peer1:eth1"}


def test_a_link_local_next_hop_is_named_by_its_owner_and_anything_else_kept():
    from netdryrun.verify import frr
    owners = frr.link_local_names({"peer1": frr.parse_link_local(IP_ADDR, "peer1")})
    with frr.link_local_owners(owners):
        assert frr._boot_free("fe80::a8c1:abff:feb5:4b08") == "fe80::%peer1:eth1"
        assert frr._boot_free("fe80::dead") == "fe80::dead"              # no lab node owns it: a typo shows
        assert frr._boot_free("10.0.0.1") == "10.0.0.1"
    assert frr._boot_free("fe80::a8c1:abff:feb5:4b08") == "fe80::"        # without the lab's addresses (fixtures)


def test_a_link_local_address_two_nodes_share_is_kept_as_written():
    """fe80::1 configured on two nodes: which one is meant depends on the link, so the address stays (it is
    configured, so it is the same on every boot)."""
    from netdryrun.verify import frr
    owners = frr.link_local_names({"r1": {"fe80::1": "r1:eth1"}, "r3": {"fe80::1": "r3:eth2"}})
    with frr.link_local_owners(owners):
        assert frr._boot_free("fe80::1") == "fe80::1"


def test_collect_reads_the_link_local_addresses_of_every_node(monkeypatch):
    from netdryrun.verify import frr

    class Lab:
        nodes = {"edge1": type("N", (), {"kind": "linux"})(), "br": type("N", (), {"kind": "bridge"})(),
                 "h1": type("N", (), {"kind": "linux"})()}

        def exec(self, node, argv, timeout=60):
            from netdryrun.lab import ExecResult
            assert node != "br" and argv == ["ip", "-6", "addr", "show", "scope", "link"]
            return ExecResult(argv, 0 if node == "edge1" else 1, IP_ADDR if node == "edge1" else "", "no ip")

    seen = {}

    class Collector:
        def __init__(self, node, exec_fn, ll_owners=None):
            seen[node] = ll_owners

        def collect(self):
            return frr.NodeSnapshot("edge1", "frr", ("default",), {}, [])
    monkeypatch.setattr(vrun, "FrrCollector", Collector)
    monkeypatch.setattr(vrun, "unobserved_reasons", lambda lab, nodes: {})
    vrun.collect(Lab(), {"edge1": "frr", "h1": "", "br": ""})
    assert seen["edge1"]["fe80::a8c1:abff:feb5:4b08"] == "fe80::%edge1:eth1"


# ------------------------------------------------------------------------------------------- R4 (Option 1)
# Config that acts only on routes or events the lab never produces (a prefix-list widened for prefixes the lab
# doesn't carry, maximum-prefix, dampening, timers, BFD, a password) changed nothing observable, so it shipped under
# NO BEHAVIOR CHANGE, or next to a declared change. Each FRR node's normalised running config is now in the
# snapshot: a config change with no observable effect fails, and an approval lists the changed lines.

def _m(before, after, lines=()):
    from netdryrun.verify.engine import match
    from verify_helpers import intent
    return match(before.snap(), after.snap(), intent(lines))


def test_a_config_change_with_no_observable_effect_fails():
    from verify_helpers import base
    after = base()
    after.configure("edge1", " neighbor 10.0.2.2 maximum-prefix 5")
    m = _m(base(), after)
    assert m.status == "failed"
    (d,) = m.undeclared
    assert d.key.kind == "config" and d.key.node == "edge1"


def test_identical_running_configs_are_no_change():
    from verify_helpers import base
    assert _m(base(), base()).status == "no_change"


def test_a_cosmetic_change_can_be_declared_and_is_listed():
    from verify_helpers import base
    after = base()
    after.configure("edge1", " neighbor 10.0.2.2 description upstream-1")
    m = _m(base(), after, [{"config_change_on": ["edge1"]}])
    assert m.status == "matched"
    assert m.untested == {"edge1": {"added": ["router bgp 65000 > neighbor 10.0.2.2 description upstream-1"],
                                    "removed": []}}


def test_config_change_on_a_node_whose_config_did_not_change_did_not_happen():
    from verify_helpers import base
    m = _m(base(), base(), [{"config_change_on": ["edge1"]}])
    assert m.status == "failed" and m.not_happened


def test_a_latent_line_next_to_a_declared_change_is_listed_as_untested():
    """The declared change on edge1 matches; the max-prefix line next to it changes nothing the lab sees, so it is
    listed under 'not tested if the lab doesn't exercise them' (in the result, the PR header and MCP)."""
    from verify_helpers import add_new_customer_block, base
    after = add_new_customer_block(base())
    after.configure("edge1", " neighbor 10.0.1.2 maximum-prefix 5", " network 10.101.0.0/24")
    m = _m(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "matched", [d.key.where() for d in m.undeclared]
    assert "router bgp 65000 > neighbor 10.0.1.2 maximum-prefix 5" in m.untested["edge1"]["added"]


def test_a_config_change_on_a_node_with_no_explained_behaviour_fails_even_next_to_a_declared_change():
    from verify_helpers import add_new_customer_block, base
    after = add_new_customer_block(base())
    after.configure("cust1", " neighbor 10.0.1.1 password s3cret")   # cust1's behaviour didn't change
    m = _m(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "failed" and {(d.key.kind, d.key.node) for d in m.undeclared} == {("config", "cust1")}


# R6: `no neighbor X send-community` toward a peer verify doesn't observe: Adj-RIB-Out JSON shows communities
# before encoding, so only the running config shows it. Now it is a config change with no observable effect.

def test_send_community_removed_fails_as_a_config_change():
    from verify_helpers import base
    after = base()
    after.configure("edge1", " address-family ipv4 unicast", "  no neighbor 10.0.3.2 send-community",
                    " exit-address-family")
    m = _m(base(), after)
    assert m.status == "failed" and {d.key.kind for d in m.undeclared} == {"config"}


# --- running config: normalised, and only what FRR itself formats ----------------------------------------------

RUNNING = """Building configuration...

Current configuration:
!
frr version 10.4.1_git
frr defaults traditional
hostname edge1
service integrated-vtysh-config
!
router bgp 65000
 bgp router-id 192.0.2.1
 bgp conditional-advertisement timer 30
 neighbor 10.0.2.2 remote-as 65200
 neighbor 10.0.2.2 description upstream-1
 !
 address-family ipv4 unicast
  neighbor 10.0.2.2 advertise-map ADV exist-map EXIST
 exit-address-family
exit
!
end
"""


def test_the_running_config_is_normalised_without_dropping_anything_semantic():
    from netdryrun.verify import frr
    lines = frr.parse_running_config(RUNNING)
    assert lines[0] == "frr version 10.4.1_git" and "hostname edge1" in lines
    assert " neighbor 10.0.2.2 description upstream-1" in lines
    assert frr.parse_running_config(" description x   ") == (" description x",)    # trailing spaces only
    assert not any(ln.strip() in ("!", "", "end") or ln.startswith(("Building", "Current configuration"))
                   for ln in lines)
    assert ("router bgp 65000 > address-family ipv4 unicast > neighbor 10.0.2.2 advertise-map ADV exist-map EXIST"
            in frr.qualified(lines))


# ------------------------------------------------------------------------------------------------------- S2
# `advertise-map ... exist-map` is evaluated by a scanner every `bgp conditional-advertisement timer` seconds (60 by
# default): a change it makes can land after two identical snapshots `settle` apart. settle now covers it.

def test_the_conditional_advertisement_timer_is_read_from_the_config():
    from netdryrun.verify import frr
    assert frr.cond_adv_timer(frr.parse_running_config(RUNNING)) == 30.0
    plain = RUNNING.replace(" bgp conditional-advertisement timer 30\n", "")
    assert frr.cond_adv_timer(frr.parse_running_config(plain)) == 60.0              # FRR's default
    none = plain.replace("  neighbor 10.0.2.2 advertise-map ADV exist-map EXIST\n", "")
    assert frr.cond_adv_timer(frr.parse_running_config(none)) == 0.0


def test_settle_stretches_past_the_conditional_advertisement_timer():
    from netdryrun.verify import converge
    logs, samples, clock = [], [], [0.0]

    def take():
        from verify_helpers import base
        samples.append(clock[0])
        snap = base().snap()
        snap.nodes["edge1"].cond_adv_timer = 30.0
        return snap

    def sleep(s):
        clock[0] += s
    converge.stable_snapshot(take, settle=10, timeout=300, log=logs.append, clock=lambda: clock[0], sleep=sleep,
                             bgp_nodes=set())
    assert samples[-1] - samples[-2] >= 30 + converge.ADV_MARGIN
    assert any("conditional advertisement" in line for line in logs)


def test_link_local_addresses_from_a_live_frr_node():
    """`ip -6 addr show scope link` in quay.io/frrouting/frr:10.4.1 (live, 2026-10-30): the image has `ip`."""
    from pathlib import Path

    from netdryrun.verify import frr
    text = (Path(__file__).parent / "fixtures" / "verify-ip6-link-edge1.txt").read_text(encoding="utf-8")
    owners = frr.parse_link_local(text, "edge1")
    assert owners["fe80::a8c1:abff:fed0:6702"] == "edge1:eth1" and owners["fe80::ec30:cff:fe18:9544"] == "edge1:eth0"
    assert len(owners) == 7


def test_the_live_running_config_parses_and_keeps_every_command():
    from pathlib import Path

    from netdryrun.verify import frr
    text = (Path(__file__).parent / "fixtures" / "verify" / "running_config.txt").read_text(encoding="utf-8")
    lines = frr.parse_running_config(text.split("\n", 1)[1])
    assert lines[0] == "frr version 10.4.1_git" and "route-map CUSTOMER-IN permit 10" in lines
    assert " set local-preference 200" in lines and frr.cond_adv_timer(lines) == 0.0
