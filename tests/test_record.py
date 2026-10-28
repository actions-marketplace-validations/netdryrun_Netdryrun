from pathlib import Path

from netdryrun.record import render


def test_render_has_review_header_and_warnings():
    text = render({"lab": "topology.clab.yml", "timeout": 120, "checks": [{"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2"}]},
                  ["r2: BGP neighbor 10.0.0.9 is active; not recorded"])
    assert text.startswith("# Recorded by netdryrun")
    assert "# warning: r2" in text
    assert "neighbor: 10.0.0.2" in text


def test_attribute_check_pins_best_path():
    from netdryrun.drivers.base import BgpPath, Observation
    from netdryrun.record import _attribute_check

    class Drv:
        def bgp_paths(self, prefix, vrf="default"):
            return Observation([
                BgpPath(best=False, as_path="65020 65020", next_hop="10.0.0.6", local_pref=100, med=10),
                BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=200, med=50,
                        communities=["65020:100", "65535:65281"], large_communities=["65020:1:1"]),
            ], [])

    c = _attribute_check(Drv(), "r1", "192.168.20.0/24")
    assert c == {"type": "bgp_route", "node": "r1", "prefix": "192.168.20.0/24", "as_path": "65020",
                 "local_pref": 200, "communities": ["65020:100", "no-export", "65020:1:1"]}


# ------------------------------------------------------------------------- 0.3.3 (c): ranges, truncation, guards

import ipaddress  # noqa: E402

import pytest  # noqa: E402

from netdryrun import record as rec  # noqa: E402
from netdryrun.drivers.base import BgpNeighbor, Observation, Route  # noqa: E402
from netdryrun.lab import Node  # noqa: E402


class FakeLab:
    def __init__(self, topology, addresses=None, links=None):
        self.nodes = {n: Node(n, f"clab-t-{n}", "linux", "frr") for n in ("r1", "r2")}
        self.links = links if links is not None else [(("r1", "eth1"), ("r2", "eth1"))]
        self.addresses = addresses or {("r1", "eth1"): ["10.0.12.1/30"], ("r2", "eth1"): ["10.0.12.2/30"]}

    def interface_addresses(self, node, iface):
        return [ipaddress.ip_interface(a) for a in self.addresses.get((node, iface), [])]


class FakeDrv:
    name = "frr"

    def __init__(self, counts, routes4=(), routes6=()):
        self.counts, self.routes = counts, {4: list(routes4), 6: list(routes6)}

    def bgp_neighbors(self, vrf="default"):
        return Observation({a: BgpNeighbor(a, "established", pfx) for a, pfx in self.counts.items()}, [])

    def all_routes(self, vrf="default", family=4):
        return Observation([Route(p, "bgp", True) for p in self.routes[family]], [])


def run_record(monkeypatch, drivers, lab=None, **kw):
    lab = lab or FakeLab(None)
    monkeypatch.setattr(rec, "Lab", lambda topology: lab)
    monkeypatch.setattr(rec, "detect", lambda node: "frr")
    monkeypatch.setattr(rec, "for_node", lambda lab_, name: drivers[name])
    return rec.record(Path("t.clab.yml"), **kw)


def prefixes(data, node="r1"):
    return [c for c in data["checks"] if c["type"] == "bgp_prefixes" and c["node"] == node]


def test_prefix_counts_are_ranges_by_default(monkeypatch):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 4}, "10.0.13.2": {"ipv4-unicast": 20, "ipv6-unicast": 0}}),
               "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers)
    got = {(c["neighbor"], c["afi"]): {k: c[k] for k in ("min", "max", "exact") if k in c} for c in prefixes(data)}
    assert got == {("10.0.12.2", "ipv4-unicast"): {"min": 4, "max": 6},     # +max(2, 20%)
                   ("10.0.13.2", "ipv4-unicast"): {"min": 20, "max": 24},
                   ("10.0.13.2", "ipv6-unicast"): {"exact": 0}}               # min: 0 is refused; nothing stays nothing


@pytest.mark.parametrize("mode,want", [("exact", {"exact": 4}), ("min", {"min": 4})])
def test_exact_and_min_prefixes_stay_available(monkeypatch, mode, want):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 4}}), "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers, prefix_mode=mode)
    c = prefixes(data)[0]
    assert {k: c[k] for k in ("min", "max", "exact") if k in c} == want


def test_every_recorded_range_loads(monkeypatch, tmp_path):
    from netdryrun.config import load
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 0}, "10.0.13.2": {"ipv4-unicast": 7}}),
               "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, guards=True)
    (tmp_path / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n    r2: {kind: linux, image: frr}\n")
    data["lab"] = "topology.clab.yml"
    (tmp_path / "netdryrun.yml").write_text(rec.render(data, warnings))
    assert load(tmp_path / "netdryrun.yml").checks


def test_truncation_is_loud(monkeypatch):
    many = [f"10.{i // 250}.{i % 250}.0/24" for i in range(rec.MAX_ROUTES_PER_NODE + 10)]
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 60}}, routes4=many), "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers)
    assert any(w.startswith("INCOMPLETE BASELINE") and "r1" in w and "60" in w for w in warnings)
    text = rec.render(data, warnings)
    head = text.splitlines()
    assert head[0].startswith("# INCOMPLETE BASELINE"), head[:3]   # first line of the file, before anything else


def guards(data, node="r1"):
    return sorted(c["prefix"] for c in data["checks"]
                  if c["type"] == "route" and c["node"] == node and c.get("present") is False)


def test_guards_add_no_default_route_and_no_link_subnets(monkeypatch):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}, routes4=["192.168.2.0/24"]),
               "r2": FakeDrv({"10.0.12.1": {"ipv4-unicast": 1}, "fd00::1": {"ipv6-unicast": 1}},
                             routes4=["192.168.1.0/24"], routes6=["fd01::/64"])}
    data, _ = run_record(monkeypatch, drivers, guards=True)
    assert guards(data, "r1") == ["0.0.0.0/0", "10.0.12.0/30"]
    assert guards(data, "r2") == ["0.0.0.0/0", "10.0.12.0/30", "::/0"]   # IPv6 BGP on r2: ::/0 too
    for c in data["checks"]:
        if c.get("present") is False:
            assert c["protocol"] == "bgp"


def test_no_guard_against_what_the_network_does_today(monkeypatch):
    # r1 learns a default and the link subnet via BGP today: a guard against them would fail the baseline
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}, routes4=["0.0.0.0/0", "10.0.12.0/30"]),
               "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, guards=True)
    assert guards(data, "r1") == []
    assert any("r1" in w and "0.0.0.0/0" in w for w in warnings)


def test_no_guards_unless_asked(monkeypatch):
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers)
    assert guards(data) == []


def test_an_unreadable_interface_is_a_warning_not_a_missing_guard(monkeypatch):
    # 0.3.3 cold review 5: interface_addresses raises LabError when it can't read them; that was swallowed
    from netdryrun.lab import LabError

    class Unreadable(FakeLab):
        def interface_addresses(self, node, iface):
            if node == "r2":
                raise LabError("could not read the addresses of r2 eth1")
            return super().interface_addresses(node, iface)
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2}}), "r2": FakeDrv({})}
    data, warnings = run_record(monkeypatch, drivers, lab=Unreadable(None), guards=True)
    assert "10.0.12.0/30" in guards(data, "r1")        # r1's end was read
    assert any("r2" in w and "eth1" in w and "guard" in w for w in warnings)


def test_ipv6_over_ipv4_sessions_gets_the_ipv6_default_guard(monkeypatch):
    # 0.3.3 cold review 6: IPv6 unicast carried over IPv4 neighbors, no IPv6 BGP route today
    drivers = {"r1": FakeDrv({"10.0.12.2": {"ipv4-unicast": 2, "ipv6-unicast": 0}}), "r2": FakeDrv({})}
    data, _ = run_record(monkeypatch, drivers, guards=True)
    assert "::/0" in guards(data, "r1")
