"""0.3.3 cross-platform review (Grok): driver shapes that could pass without testing, from captured-output
fixtures with the field each finding names changed."""
import json
from pathlib import Path

from netdryrun.drivers import eos, frr, srlinux

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


# --- #4: two scoped link-local neighbors collapse into one key: keep the one that isn't established ---------------

def _frr_neighbors(states: dict) -> str:
    return json.dumps({addr: {"bgpState": st, "addressFamilyInfo": {"ipv6Unicast": {"acceptedPrefixCounter": 1}}
                              if st == "Established" else {}} for addr, st in states.items()})


def test_frr_link_local_neighbors_that_collapse_keep_the_down_one():
    for order in (["fe80::1%eth1", "fe80::1%eth2"], ["fe80::1%eth2", "fe80::1%eth1"]):
        states = {order[0]: "Established", order[1]: "Idle"} if order[0].endswith("eth1") else \
                 {order[0]: "Idle", order[1]: "Established"}
        out = frr.parse_bgp_neighbors(_frr_neighbors(dict(states)))
        assert out["fe80::1"].state == "idle", order


def test_srl_link_local_neighbors_that_collapse_keep_the_down_one():
    for first, second in (("established", "idle"), ("idle", "established")):
        text = json.dumps({"neighbor": [
            {"peer-address": "fe80::1%e1-1.0", "session-state": first,
             "afi-safi": [{"afi-safi-name": "ipv6-unicast", "received-routes": 1}] if first == "established" else []},
            {"peer-address": "fe80::1%e1-2.0", "session-state": second,
             "afi-safi": [{"afi-safi-name": "ipv6-unicast", "received-routes": 1}] if second == "established" else []}]})
        assert srlinux.parse_bgp_neighbors(text)["fe80::1"].state == "idle", (first, second)


def _eos_summary(peers: dict) -> str:
    return json.dumps({"vrfs": {"default": {"peers": {
        a: {"peerState": st, **({"prefixAccepted": 1} if st == "Established" else {})} for a, st in peers.items()}}}})


def test_eos_link_local_neighbors_that_collapse_keep_the_down_one():
    for peers in ({"fe80::1%Et1": "Established", "fe80::1%Et2": "Idle"},
                  {"fe80::1%Et2": "Idle", "fe80::1%Et1": "Established"}):
        out = eos.parse_bgp_summary(_eos_summary(peers))
        assert out["fe80::1"].state == "idle", peers


# --- EOS prints Idle(Admin) with no space ---------------------------------------------------------------------------

def test_eos_admin_idle_reads_as_idle():
    out = eos.parse_bgp_summary(_eos_summary({"10.0.0.2": "Idle(Admin)", "10.0.0.3": "Idle(MaxPath)"}))
    assert out["10.0.0.2"].state == "idle" and out["10.0.0.3"].state == "idle"


# --- #7: an SR Linux route learned through EVPN is a BGP route for `protocol: bgp` -----------------------------------

def test_srl_bgp_evpn_route_type_is_bgp():
    row = json.loads(read("srl_leak_route.txt"))
    row["route"][0]["route-type"] = "bgp-evpn"
    routes = srlinux.parse_routes(json.dumps(row), "0.0.0.0/0")
    assert routes and routes[0].protocol == "bgp" and routes[0].active


# --- #5: FRR marks a graceful-restart stale path ("stale": true); a check never passes on one -------------------------

def _frr_stale(index: int = 0) -> str:
    data = json.loads(read("frr_bgp_paths.txt"))
    data["paths"][index]["stale"] = True
    return json.dumps(data)


def _frr_table(prefix: str) -> str:
    route = json.loads(read("frr_route.txt"))["192.168.3.0/24"][0]
    return json.dumps({prefix: [dict(route, prefix=prefix)]})


def test_frr_route_with_a_stale_bgp_path_is_not_settled():
    import pytest
    from netdryrun.drivers.base import DriverError
    prefix = "192.168.20.0/24"
    for i in (0, 1):   # the best path or another one
        with pytest.raises(DriverError, match="stale"):
            frr.parse_routes(_frr_table(prefix), prefix, _frr_stale(i))
    assert frr.parse_routes(_frr_table(prefix), prefix, read("frr_bgp_paths.txt"))   # no stale path: as before


def test_frr_bgp_paths_with_a_stale_path_are_not_settled():
    import pytest
    from netdryrun.drivers.base import DriverError
    with pytest.raises(DriverError, match="stale"):
        frr.parse_bgp_paths(_frr_stale(0), "192.168.20.0/24")


def test_a_route_check_never_passes_on_a_stale_frr_path_present_or_absent():
    from netdryrun.checks import Unready, _evaluate
    from netdryrun.config import Check
    from netdryrun.drivers.base import Observation
    prefix = "192.168.20.0/24"

    class Drv:
        name = "frr"

        def routes(self, p, vrf="default"):
            return Observation(frr.parse_routes(_frr_table(prefix), p, _frr_stale(0)), [])

        def bgp_paths(self, p, vrf="default"):
            return Observation(frr.parse_bgp_paths(_frr_stale(0), p), [])

    for params in ({"prefix": prefix}, {"prefix": prefix, "protocol": "bgp", "present": False}):
        ok, detail, _ = _evaluate(Check("route", {"node": "r1", **params}, "c", 30), Drv())
        assert not ok and isinstance(detail, Unready) and "stale" in detail, params
    ok, detail, _ = _evaluate(Check("bgp_route", {"node": "r1", "prefix": prefix, "local_pref": 200}, "c", 30), Drv())
    assert not ok and "stale" in detail
