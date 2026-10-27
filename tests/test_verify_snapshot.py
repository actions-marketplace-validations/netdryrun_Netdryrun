"""verify's snapshot model and its FRR collection: normalisation and strict validation.

The FRR outputs in tests/fixtures/verify are synthetic (built from the captured path and neighbor objects
in tests/fixtures/frr_*.txt) until a live capture replaces them; each starts with a marker line."""
import json

import pytest

from netdryrun.drivers.base import DriverError
from netdryrun.verify import frr
from netdryrun.verify.snapshot import (AsPath, ItemKey, NodeSnapshot, Snapshot, SnapshotError, canon_community,
                                       canon_ext_communities, canon_large_community, canon_set, parse_asn)
from verify_helpers import FIX, SYNTHETIC, base, fixture, nh, rib

ADJ = {
    "show bgp ipv4 unicast neighbors 10.0.2.2 advertised-routes detail json": "adj_out_default_ipv4_10.0.2.2.txt",
    "show bgp ipv4 unicast neighbors 10.0.2.2 received-routes detail json": "adj_in_default_ipv4_10.0.2.2.txt",
    "show bgp ipv4 unicast neighbors 10.0.3.2 advertised-routes detail json": "adj_out_default_ipv4_10.0.3.2.txt",
    "show bgp ipv6 unicast neighbors 2001:db8:11::2 advertised-routes detail json":
        "adj_out_default_ipv6_2001_db8_11__2.txt",
    "show bgp vrf cust ipv4 unicast neighbors 10.10.1.2 advertised-routes detail json": "adj_out_cust_ipv4_10.10.1.2.txt",
}
OUTPUTS = {"show vrf": "show_vrf.txt", frr.NEIGHBORS_CMD: "neighbors.txt",
           frr.ROUTE_CMDS["ipv4"]: "route_v4.txt", frr.ROUTE_CMDS["ipv6"]: "route_v6.txt",
           frr.BGP_CMDS["ipv4"]: "bgp_v4_detail.txt", frr.BGP_CMDS["ipv6"]: "bgp_v6_detail.txt", **ADJ}


class FakeNode:
    def __init__(self, overrides=None, fail=()):
        self.texts = {cmd: fixture(name) for cmd, name in OUTPUTS.items()}
        self.texts.update(overrides or {})
        self.fail = set(fail)
        self.calls = []

    def __call__(self, node, argv):
        assert argv[:2] == ["vtysh", "-c"]
        cmd = argv[2]
        self.calls.append(cmd)
        if cmd in self.fail:
            return 1, "", "Exiting: failed to connect to any daemons."
        if cmd not in self.texts:
            raise AssertionError(f"unexpected command {cmd!r}")
        return 0, self.texts[cmd], ""


def collect(**kw):
    return frr.FrrCollector("edge1", FakeNode(**kw)).collect()


def edited(cmd, fn):
    data = json.loads(fixture(OUTPUTS[cmd]))
    fn(data)
    return {cmd: json.dumps(data)}


def test_every_verify_fixture_is_marked_synthetic():
    files = sorted(FIX.iterdir())
    assert len(files) >= 10
    for f in files:
        assert f.read_text(encoding="utf-8").splitlines()[0] == SYNTHETIC, f.name


# --- normalisation ---------------------------------------------------------------------------------------

def test_as_set_is_a_sorted_set_and_sequence_order_is_kept():
    a = AsPath.build([("as-sequence", [65003, 65001]), ("as-set", [65021, 65020, 65021])])
    b = AsPath.parse("65003 65001 {65020,65021}")
    assert a == b and a.render() == "65003 65001 {65020,65021}"
    assert AsPath.parse("65001 65003") != AsPath.parse("65003 65001")
    assert AsPath.build([("as-sequence", [1]), ("as-sequence", [2])]) == AsPath.parse("1 2")   # merged
    assert AsPath.parse("") == AsPath(())
    with pytest.raises(SnapshotError):
        AsPath.build([("as-weird", [1])])
    with pytest.raises(SnapshotError):
        AsPath.parse("65001 foo")


def test_asns_are_asplain():
    assert parse_asn("1.10") == 65546 and parse_asn(65546) == 65546 and parse_asn("65546") == 65546
    for bad in (True, -1, 2 ** 32, "x", "1.70000"):
        with pytest.raises(SnapshotError):
            parse_asn(bad)


@pytest.mark.parametrize("token,canonical", [
    ("no-export", "65535:65281"), ("NO_EXPORT", "65535:65281"), ("65535:65281", "65535:65281"),
    ("local-AS", "65535:65283"), ("no-export-subconfed", "65535:65283"), ("internet", "0:0"),
    ("blackhole", "65535:666"), ("graceful-shutdown", "65535:0"), ("065000:0100", "65000:100"),
    ("4259840100", "65000:100"),
])
def test_standard_communities_have_one_form(token, canonical):
    assert canon_community(token) == canonical


def test_large_and_extended_communities():
    assert canon_large_community("65000:001:2") == "65000:1:2"
    assert canon_ext_communities("RT:65002:100 LB:65002:125000 (1.000 Mbps) SoO:65000:1") == \
        ("lb:65002:125000", "rt:65002:100", "soo:65000:1")
    for bad in ("65000:1", "1:2:4294967296"):
        with pytest.raises(SnapshotError):
            canon_large_community(bad)
    with pytest.raises(SnapshotError):
        canon_ext_communities("RT:65002:100 garbage!")
    with pytest.raises(SnapshotError):
        canon_community("65536:1")


def test_ecmp_next_hops_are_a_set():
    a = canon_set([nh("10.0.0.2"), nh("10.0.0.1")])
    b = canon_set([nh("10.0.0.1"), nh("10.0.0.2"), nh("10.0.0.1")])
    assert a == b and len(a) == 2


def test_ecmp_order_in_frr_output_does_not_matter():
    entries = frr.parse_routes(fixture("route_v4.txt"), "ipv4")["default"][("203.0.113.0/24", "bgp")]
    data = json.loads(fixture("route_v4.txt"))
    data["default"]["203.0.113.0/24"][0]["nexthops"].reverse()
    data["default"]["203.0.113.0/24"][0]["uptime"] = "00:09:59"           # noise
    data["default"]["203.0.113.0/24"][0]["nexthops"][0]["interfaceIndex"] = 99   # ifindex varies across boots
    again = frr.parse_routes(json.dumps(data), "ipv4")["default"][("203.0.113.0/24", "bgp")]
    assert entries == again


def test_absent_med_and_local_pref_stay_absent():
    paths = frr.parse_bgp_table(fixture("bgp_v4_detail.txt"), "ipv4")["default"]
    ibgp = paths[("198.18.0.0/24", "10.0.2.2", 0)]
    assert ibgp.attrs.med is None and ibgp.attrs.local_pref == 100
    local = paths[("192.0.2.0/24", "local", 0)]
    assert local.attrs.local_pref is None and local.attrs.med == 0 and local.peer_type == "local"


# --- FRR collection --------------------------------------------------------------------------------------

def test_collect_reads_every_vrf_afi_protocol_and_session():
    ns = collect()
    assert ns.vrfs == ("cust", "default")
    kinds = {}
    for k in ns.items:
        kinds.setdefault(k.kind, set()).add((k.vrf, k.afi))
    assert kinds["session"] == {("default", ""), ("cust", "")}
    assert {("default", "ipv4"), ("default", "ipv6"), ("cust", "ipv4")} <= kinds["rib"]
    assert {("default", "ipv4"), ("default", "ipv6"), ("cust", "ipv4")} <= kinds["path"]
    assert kinds["adj_out"] == {("default", "ipv4")}
    assert kinds["adj_in"] == {("default", "ipv4")}
    protos = {k.protocol for k in ns.items if k.kind == "rib"}
    assert protos == {"connected", "local", "ospf", "static", "bgp"}
    s = ns.items[ItemKey("session", "edge1", "default", neighbor="10.0.2.2")]
    assert s.established and s.local_address == "10.0.2.1" and s.afis == ("ipv4-unicast",)
    assert s.soft_reconfig_in == ("ipv4-unicast",) and dict(s.prefix_counts) == {"ipv4-unicast": 2}
    down = ns.items[ItemKey("session", "edge1", "default", neighbor="10.0.9.2")]
    assert down.state == "active" and down.local_address is None


def test_collect_keeps_raw_output_for_every_command():
    fake = FakeNode()
    ns = frr.FrrCollector("edge1", fake).collect()
    assert [r["cmd"] for r in ns.raw] == [f"vtysh -c '{c}'" for c in fake.calls]
    assert all(r["rc"] == 0 and r["output"] for r in ns.raw)


def test_received_only_and_selected_routes():
    ns = collect()
    adj_in = {k.prefix for k in ns.items if k.kind == "adj_in"}
    assert adj_in == {"0.0.0.0/0", "203.0.113.0/24"}       # 0/0 is received-only (filtered inbound)
    assert not any(k.prefix == "0.0.0.0/0" and k.kind in ("rib", "path") for k in ns.items)
    statics = ns.items[ItemKey("rib", "edge1", "default", "ipv4", "unicast", "192.0.2.0/24", protocol="static")]
    assert [(e.distance, e.selected, e.fib) for e in sorted(statics, key=lambda e: e.distance)] == \
        [(1, True, True), (250, False, False)]


def test_recursive_next_hop_keeps_its_resolver():
    entries = frr.parse_routes(fixture("route_v4.txt"), "ipv4")["default"][("198.18.0.0/24", "bgp")]
    (hop,) = entries[0].nexthops
    assert hop.recursive and hop.ip == "10.255.0.2" and [r.ip for r in hop.resolved_via] == ["10.0.2.2"]


def test_link_local_next_hop_keeps_its_interface():
    entries = frr.parse_routes(fixture("route_v6.txt"), "ipv6")["default"][("2001:db8:20::/48", "bgp")]
    (hop,) = entries[0].nexthops
    assert hop.ip == "fe80::a8c1:abff:fe10:79d6" and hop.interface == "eth5"


def test_every_bgp_path_with_all_attributes():
    paths = frr.parse_bgp_table(fixture("bgp_v4_detail.txt"), "ipv4")["default"]
    up = paths[("203.0.113.0/24", "10.0.2.2", 0)]
    peer = paths[("203.0.113.0/24", "10.0.3.2", 0)]
    assert up.best and not peer.best and up.multipath and peer.multipath
    assert up.attrs.large_communities == ("65020:1:1", "65020:2:2")
    assert up.attrs.ext_communities == ("lb:65002:125000", "rt:65002:100")
    assert peer.attrs.as_path.render() == "65003 {65020,65021}"
    assert "65535:65281" in peer.attrs.communities                        # no-export, canonical
    ibgp = paths[("198.18.0.0/24", "10.0.2.2", 0)]
    assert ibgp.attrs.cluster_list == ("10.255.0.2", "10.255.0.1") and ibgp.attrs.originator_id == "10.255.0.9"
    assert ibgp.peer_type == "internal" and ibgp.attrs.next_hops[0].igp_metric == 20
    cust = frr.parse_bgp_table(fixture("bgp_v4_detail.txt"), "ipv4")["cust"]
    assert list(cust) == [("10.101.0.0/24", "10.10.1.2", 0)]              # the list form of a destination


# --- strict validation: an unknown or missing field is an error, never a smaller snapshot ------------------

def _route_entry(d):
    return d["default"]["203.0.113.0/24"][0]


def _path(d):
    return d["default"]["routes"]["203.0.113.0/24"]["paths"][0]


@pytest.mark.parametrize("cmd,mutate", [
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).update(aigp=1)),                       # unknown field
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).pop("distance")),                     # missing field
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).update(protocol="ebgp")),             # unknown protocol
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d).update(selected="true")),             # wrong type
    (frr.ROUTE_CMDS["ipv4"], lambda d: _route_entry(d)["nexthops"][0].update(color=3)),
    (frr.ROUTE_CMDS["ipv4"], lambda d: d["default"].update({"not-a-prefix": []})),
    (frr.ROUTE_CMDS["ipv4"], lambda d: d.pop("cust")),                                       # a VRF missing
    (frr.ROUTE_CMDS["ipv6"], lambda d: d["default"].update({"10.9.9.0/24": d["default"]["2001:db8:11::/64"]})),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d).update(newAttribute=1)),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d).pop("origin")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d).update(origin="weird")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d)["aspath"]["segments"][0].update(type="as-strange")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d)["community"].update(string="65000:1 bogus")),
    (frr.BGP_CMDS["ipv4"], lambda d: _path(d)["peer"].update(type="sideways")),
    (frr.BGP_CMDS["ipv4"], lambda d: d["default"]["routes"]["203.0.113.0/24"].update(pathCount=3)),
    (frr.BGP_CMDS["ipv4"], lambda d: d.pop("cust")),                                         # instance missing
    (frr.BGP_CMDS["ipv6"], lambda d: d["default"].update(extra=1)),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"].pop("bgpState")),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"]["addressFamilyInfo"].update(l2VpnEvpn={"acceptedPrefixCounter": 1})),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"]["addressFamilyInfo"].update(ipv9Magic={"acceptedPrefixCounter": 1})),
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"]["addressFamilyInfo"]["ipv4Unicast"].pop("acceptedPrefixCounter")),
    (frr.NEIGHBORS_CMD, lambda d: d["default"].update(eth1=d["default"]["10.0.2.2"])),        # unnumbered
    (frr.NEIGHBORS_CMD, lambda d: d["default"]["10.0.2.2"].pop("hostLocal")),
    (list(ADJ)[0], lambda d: d.update(totalPrefixCounter=5)),
    (list(ADJ)[0], lambda d: d["advertisedRoutes"]["192.0.2.0/24"]["paths"][0].update(mystery=True)),
    (list(ADJ)[1], lambda d: d.update(advertisedRoutes={})),
])
def test_unknown_or_missing_fields_are_errors(cmd, mutate):
    with pytest.raises(SnapshotError):
        collect(overrides=edited(cmd, mutate))


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"warning": "Unknown command"}', "null"])
def test_unreadable_output_is_an_error(text):
    with pytest.raises(DriverError):
        collect(overrides={frr.ROUTE_CMDS["ipv4"]: text})


def test_a_failed_command_is_a_command_failure():
    with pytest.raises(frr.CommandFailed):
        collect(fail={frr.NEIGHBORS_CMD})


def test_a_router_without_bgp_has_no_sessions_or_paths():
    empty = {frr.NEIGHBORS_CMD: "{}", frr.BGP_CMDS["ipv4"]: "{}", frr.BGP_CMDS["ipv6"]: "{}"}
    ns = collect(overrides=empty)
    assert not [k for k in ns.items if k.kind in ("session", "path", "adj_out", "adj_in")]
    assert [k for k in ns.items if k.kind == "rib"]


def test_bgp_instances_must_match_between_outputs():
    with pytest.raises(SnapshotError):
        collect(overrides={frr.BGP_CMDS["ipv4"]: "{}"})


# --- stored snapshots --------------------------------------------------------------------------------------

def test_snapshot_round_trips_through_json():
    snap = Snapshot({"edge1": collect()}, {"host1": "a host"})
    data = json.loads(json.dumps(snap.to_json()))
    again = Snapshot.from_json(data)
    assert again.items() == snap.items() and again.unobserved == snap.unobserved
    lab = base().snap()
    assert Snapshot.from_json(json.loads(json.dumps(lab.to_json()))).items() == lab.items()


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(extra=1),
    lambda d: d.update(schema="netdryrun.snapshot/v0"),
    lambda d: d["nodes"]["edge1"]["items"][0]["value"].update(unknown=1),
    lambda d: d["nodes"]["edge1"]["items"][-1]["value"].pop(next(iter(d["nodes"]["edge1"]["items"][-1]["value"]))),
    lambda d: d["nodes"]["edge1"]["items"][0]["key"].update(kind="mystery"),
    lambda d: d["nodes"]["edge1"]["items"].append(d["nodes"]["edge1"]["items"][0]),
    lambda d: d["nodes"]["edge1"].pop("items"),
])
def test_stored_snapshot_is_validated_strictly(mutate):
    data = json.loads(json.dumps(Snapshot({"edge1": collect()}).to_json()))
    mutate(data)
    with pytest.raises(SnapshotError):
        Snapshot.from_json(data)


def test_values_validate_their_normal_form():
    with pytest.raises(SnapshotError):
        NodeSnapshot("r1", "frr", ("default",), {ItemKey("rib", "r2", "default", "ipv4", "unicast", "10.0.0.0/8",
                                                         protocol="bgp"): rib()})
    with pytest.raises(SnapshotError):
        ItemKey("rib", "r1", "default", "ipv6", "unicast", "10.0.0.0/8", protocol="bgp")
    with pytest.raises(SnapshotError):
        AsPath((("set", (3, 1)),))
