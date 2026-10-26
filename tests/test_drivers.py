"""Parsers against real device output captured from live labs (tests/fixtures)."""
from pathlib import Path

import pytest

from netdryrun.drivers import DriverError, frr, srlinux

FIX = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIX / name).read_text()


def test_frr_bgp_neighbors():
    n = frr.parse_bgp_neighbors(read("frr_bgp_neighbors.txt"))
    assert n["10.0.12.2"].state == "established"
    assert n["10.0.12.2"].prefixes["ipv4-unicast"] >= 1


def test_frr_routes():
    routes = frr.parse_routes(read("frr_route.txt"), "192.168.3.0/24")
    assert any(r.protocol == "bgp" and r.active for r in routes)
    assert frr.parse_routes(read("frr_route.txt"), "10.99.0.0/16") == []


def test_ping_busybox_and_iputils():
    assert frr.parse_ping(read("frr_ping.txt")) == (3, 3)
    assert frr.parse_ping(read("srl_ping.txt")) == (3, 3)
    assert frr.parse_ping("garbage") == (0, 0)


def test_srl_bgp_neighbors():
    n = srlinux.parse_bgp_neighbors(read("srl_bgp_neighbors.txt"))
    nb = n["10.0.100.2"]
    assert nb.state == "established"
    assert nb.prefixes["ipv4-unicast"] >= 1
    assert "evpn" not in nb.prefixes  # families without counters are skipped


def test_srl_routes():
    routes = srlinux.parse_routes(read("srl_route.txt"), "192.168.20.0/24")
    assert routes and routes[0].protocol == "bgp" and routes[0].active


def test_srl_bad_output_is_an_error():
    with pytest.raises(DriverError):
        srlinux.parse_bgp_neighbors("Parsing error: nope")
    assert srlinux.parse_bgp_neighbors("") == {}


def test_frr_all_routes():
    routes = frr.parse_all_routes(read("frr_route.txt"))
    assert any(r.prefix == "192.168.3.0/24" and r.protocol == "bgp" for r in routes)


# --- Arista EOS (real cEOS-lab 4.36.3M output) ---
from netdryrun.drivers import eos  # noqa: E402


def test_eos_bgp_summary():
    n = eos.parse_bgp_summary(read("eos_bgp_summary.txt"))
    assert n["10.0.200.2"].state == "established"
    assert n["10.0.200.2"].prefixes["ipv4-unicast"] == 1


def test_eos_routes_active_bgp():
    routes = eos.parse_routes(read("eos_route.txt"), read("eos_bgp_route.txt"), "192.168.20.0/24")
    assert [(r.protocol, r.active) for r in routes] == [("bgp", True)]


def test_eos_leak_received_but_not_installed():
    """Regression (live-found): BGP 'best' default losing to a static must still count as present."""
    routes = eos.parse_routes(read("eos_leak_route.txt"), read("eos_leak_bgp.txt"), "0.0.0.0/0")
    assert ("static", True) in [(r.protocol, r.active) for r in routes]
    assert ("bgp", False) in [(r.protocol, r.active) for r in routes]


def test_eos_ping():
    assert frr.parse_ping(read("eos_ping.txt")) == (3, 3)


def test_eos_error_output_is_an_error():
    with pytest.raises(DriverError):
        eos.parse_bgp_summary("% Invalid input")


def test_srl_leak_received_but_not_installed():
    """Regression (live-found): SR Linux's route table only shows the installed static; the leaked
    BGP default lives in the BGP RIB and must still count as present."""
    routes = srlinux.parse_routes(read("srl_leak_route.txt"), "0.0.0.0/0", read("srl_leak_rib.txt"))
    assert ("static", True) in [(r.protocol, r.active) for r in routes]
    assert ("bgp", False) in [(r.protocol, r.active) for r in routes]


def test_srl_empty_rib_adds_nothing():
    assert srlinux.parse_routes("", "10.99.0.0/16", read("srl_rib_empty.txt")) == []


def test_detect_sonic_and_others():
    from netdryrun.drivers import detect
    from netdryrun.lab import Node
    def n(kind, image):
        return Node(name="x", kind=kind, image=image, container="c")
    assert detect(n("sonic-vs", "docker-sonic-vs:latest")) == "sonic"
    assert detect(n("linux", "docker-sonic-vs:latest")) == "sonic"
    assert detect(n("arista_ceos", "ceos:4.36.3M")) == "eos"
    assert detect(n("linux", "quay.io/frrouting/frr:10.4.1")) == "frr"


def test_sonic_reads_frr_output():
    # docker-sonic-vs runs FRR 10.7 inside; output captured from examples/sonic-frr
    n = frr.parse_bgp_neighbors(read("sonic_bgp_neighbors.txt"))
    assert n["10.0.40.2"].state == "established"
    assert n["10.0.40.2"].prefixes["ipv4-unicast"] == 1
    routes = frr.parse_routes(read("sonic_route.txt"), "192.168.20.0/24")
    assert any(r.protocol == "bgp" and r.active for r in routes)
