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


def test_eos_two_down_link_locals_keep_the_first_like_frr():
    # two sessions that aren't established share a key: the first state read stays, as FRR and SR Linux do
    out = eos.parse_bgp_summary(_eos_summary({"fe80::1%Et1": "Idle", "fe80::1%Et2": "Active"}))
    assert out["fe80::1"].state == "idle"
    assert frr.parse_bgp_neighbors(_frr_neighbors({"fe80::1%eth1": "Idle", "fe80::1%eth2": "Active"}))["fe80::1"].state == "idle"


# --- Grok 2026-10-29 (a): a path with no MED field has no known MED; it is not MED 0 -----------------------------------
# With `bgp bestpath med missing-as-worst` a missing MED is the worst, not 0, so `med: 0` must not pass on one.

def test_a_missing_med_is_unknown_on_every_driver():
    data = json.loads(read("frr_bgp_paths.txt"))
    for p in data["paths"]:
        p.pop("metric", None)
    assert all(p.med is None for p in frr.parse_bgp_paths(json.dumps(data), "192.168.20.0/24"))

    data = json.loads(read("eos_bgp_paths.txt"))
    for p in data["vrfs"]["default"]["bgpRouteEntries"]["192.168.20.0/24"]["bgpRoutePaths"]:
        p.pop("med", None)
    assert all(p.med is None for p in eos.parse_bgp_paths(json.dumps(data), "192.168.20.0/24"))

    rows = srlinux.parse_rib_paths(read("srl_bgp_rib_paths.txt"), "192.168.20.0/24")
    attr = json.loads(read("srl_attr_set_best.txt"))
    attr.pop("med")
    assert srlinux.parse_attr_set(json.dumps(attr), rows[0]).med is None


def test_med_zero_never_passes_on_a_path_without_med():
    from netdryrun.checks import _evaluate
    from netdryrun.config import Check
    from netdryrun.drivers.base import Observation
    data = json.loads(read("frr_bgp_paths.txt"))
    for p in data["paths"]:
        p.pop("metric", None)

    class Drv:
        name = "frr"

        def bgp_paths(self, prefix, vrf="default"):
            return Observation(frr.parse_bgp_paths(json.dumps(data), prefix), [])

    ok, detail, _ = _evaluate(Check("bgp_route", {"node": "r1", "prefix": "192.168.20.0/24", "med": 0}, "c", 30), Drv())
    assert not ok and "MED is not set" in detail


# --- Grok 2026-10-29 (b): truncated output, or error text returned with exit 0, is never an empty RIB ---------------

import pytest  # noqa: E402

from netdryrun.drivers.base import DriverError  # noqa: E402

_EMPTY_BGP_EOS = read("eos_bgp_paths_empty.txt")
_READERS = [   # every parser a route, prefix or session verdict reads, with a real capture it parses
    ("frr-route", lambda t: frr.parse_routes(t, "192.168.3.0/24"), "frr_route.txt"),
    ("frr-route-bgp-side", lambda t: frr.parse_routes("{}", "192.168.20.0/24", t), "frr_bgp_paths.txt"),
    ("frr-all-routes", frr.parse_all_routes, "frr_route.txt"),
    ("frr-bgp-paths", lambda t: frr.parse_bgp_paths(t, "192.168.20.0/24"), "frr_bgp_paths.txt"),
    ("frr-neighbors", frr.parse_bgp_neighbors, "frr_bgp_neighbors.txt"),
    ("eos-route", lambda t: eos.parse_routes(t, _EMPTY_BGP_EOS, "192.168.20.0/24"), "eos_route.txt"),
    ("eos-route-bgp-side", lambda t: eos.parse_routes(read("eos_leak_route.txt"), t, "0.0.0.0/0"), "eos_leak_bgp.txt"),
    ("eos-bgp-paths", lambda t: eos.parse_bgp_paths(t, "192.168.20.0/24"), "eos_bgp_paths.txt"),
    ("eos-summary", eos.parse_bgp_summary, "eos_bgp_summary.txt"),
    ("srl-route", lambda t: srlinux.parse_routes(t, "192.168.20.0/24", "{}"), "srl_route.txt"),
    ("srl-route-rib-side", lambda t: srlinux.parse_routes("{}", "0.0.0.0/0", t), "srl_leak_rib.txt"),
    ("srl-rib-paths", lambda t: srlinux.parse_rib_paths(t, "0.0.0.0/0"), "srl_leak_rib.txt"),
    ("srl-neighbors", srlinux.parse_bgp_neighbors, "srl_bgp_neighbors.txt"),
]
_EXIT0_ERRORS = ["% Unknown command: show bgp", "Error: Path not found", "bgpd is not running",
                 "% BGP instance not found", "connect: Connection refused", "\n", "% Command incomplete"]


@pytest.mark.parametrize("parse, fixture", [(p, f) for _, p, f in _READERS], ids=[i for i, _, _ in _READERS])
def test_cut_off_or_error_output_is_never_an_empty_answer(parse, fixture):
    full = read(fixture)
    assert parse(full) is not None   # the capture itself parses
    cuts = sorted({len(full) * k // 16 for k in range(1, 16)} | {1, len(full.rstrip()) - 1})
    for cut in cuts:
        with pytest.raises(DriverError):
            parse(full[:cut])
    for text in _EXIT0_ERRORS + [full + "\n% Warning: output truncated"]:
        with pytest.raises(DriverError):
            parse(text)


# --- Grok 2026-10-29 (c): a covering, default or more-specific route never answers for the exact prefix ------------

_WANT = "192.168.20.0/24"
_OTHERS = ["0.0.0.0/0", "192.168.0.0/16", "192.168.20.0/25"]


def _as(fixture: str, other: str) -> str:
    text = read(fixture)
    assert _WANT in text
    return text.replace(_WANT, other)


@pytest.mark.parametrize("other", _OTHERS)
def test_only_the_exact_prefix_counts_on_every_driver(other):
    frr_table = json.dumps({other: [dict(json.loads(read("frr_route.txt"))["192.168.3.0/24"][0], prefix=other)]})
    assert frr.parse_routes(frr_table, _WANT, _as("frr_bgp_paths.txt", other)) == []
    assert frr.parse_bgp_paths(_as("frr_bgp_paths.txt", other), _WANT) == []
    assert eos.parse_routes(_as("eos_route.txt", other), _as("eos_bgp_route.txt", other), _WANT) == []
    assert eos.parse_bgp_paths(_as("eos_bgp_paths.txt", other), _WANT) == []
    assert srlinux.parse_routes(_as("srl_route.txt", other), _WANT, _as("srl_bgp_rib_paths.txt", other)) == []
    assert srlinux.parse_rib_paths(_as("srl_bgp_rib_paths.txt", other), _WANT) == []
    # the same captures with the exact prefix do answer (so the rewrite, not the capture, makes them empty)
    assert eos.parse_routes(read("eos_route.txt"), read("eos_bgp_route.txt"), _WANT)
    assert srlinux.parse_routes(read("srl_route.txt"), _WANT, read("srl_bgp_rib_paths.txt"))
    assert frr.parse_bgp_paths(read("frr_bgp_paths.txt"), _WANT)


def test_a_route_check_fails_when_only_a_covering_route_exists():
    from netdryrun.checks import _evaluate
    from netdryrun.config import Check
    from netdryrun.drivers.base import Observation

    class Drv:
        name = "eos"

        def routes(self, prefix, vrf="default"):
            return Observation(eos.parse_routes(_as("eos_route.txt", "0.0.0.0/0"),
                                                _as("eos_bgp_route.txt", "0.0.0.0/0"), prefix), [])

    ok, detail, _ = _evaluate(Check("route", {"node": "r1", "prefix": _WANT, "protocol": "bgp"}, "c", 30), Drv())
    assert not ok and "not active" in detail
