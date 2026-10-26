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
