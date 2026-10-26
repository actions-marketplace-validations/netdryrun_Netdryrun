"""Arista EOS (cEOS-lab) driver: `Cli ... | json` state, ping from the EOS CLI.

Routes are read from both the routing table (active routes) and the BGP table, because a
received-but-not-selected BGP path only appears in the BGP table and must still count as present
for `present: false` checks.
"""
from __future__ import annotations

import ipaddress
import json

from .base import BgpNeighbor, Driver, DriverError, Observation, Route
from .frr import _canon_addr, parse_ping

PROTOCOLS = {"ebgp": "bgp", "ibgp": "bgp", "bgp": "bgp", "connected": "connected", "static": "static",
             "ospf": "ospf", "ospfintraarea": "ospf", "ospfinterarea": "ospf", "ospfexternaltype1": "ospf",
             "ospfexternaltype2": "ospf", "isis": "isis", "isislevel1": "isis", "isislevel2": "isis",
             "aggregate": "aggregate", "droproute": "static", "dropped": "static"}  # static discard (Null0)


def _json(text: str) -> dict:
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise DriverError(f"unexpected EOS output: {text.strip()[:200]}") from None
    if isinstance(data, dict) and "errors" in data:
        raise DriverError(f"EOS error: {data['errors']}")
    return data if isinstance(data, dict) else {}


def _vrf(data: dict, vrf: str) -> dict:
    return (data.get("vrfs") or {}).get(vrf) or {}


def parse_bgp_summary(text: str, vrf: str = "default", afi: str = "ipv4-unicast",
                      into: dict[str, BgpNeighbor] | None = None) -> dict[str, BgpNeighbor]:
    out = into if into is not None else {}
    for addr, p in (_vrf(_json(text), vrf).get("peers") or {}).items():
        key = _canon_addr(addr)
        n = out.get(key) or BgpNeighbor(addr, str(p.get("peerState", "")).split()[0].lower())
        if "prefixAccepted" in p:
            n.prefixes[afi] = int(p["prefixAccepted"])
        out[key] = n
    return out


def parse_routes(route_text: str, bgp_text: str, prefix: str, vrf: str = "default") -> list[Route]:
    want = ipaddress.ip_network(prefix)
    out = []
    for key, r in (_vrf(_json(route_text), vrf).get("routes") or {}).items():
        if ipaddress.ip_network(key) == want:
            rtype = str(r.get("routeType", "")).lower().replace(" ", "")
            out.append(Route(prefix, PROTOCOLS.get(rtype, rtype), True))
    # A BGP path can be "best" inside BGP and still not be installed (a static or connected route with
    # a better preference wins the routing table). Unless BGP is the installed route, every BGP path is
    # "present but not selected": a leak that must still fail `present: false`.
    has_installed_bgp = any(r.protocol == "bgp" for r in out)
    for key, e in (_vrf(_json(bgp_text), vrf).get("bgpRouteEntries") or {}).items():
        if ipaddress.ip_network(key) != want:
            continue
        if e.get("bgpRoutePaths") and not has_installed_bgp:
            out.append(Route(prefix, "bgp", False))
    return out


class EosDriver(Driver):
    name = "eos"

    def _cli(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["Cli", "-p", "15", "-c", command], evidence)

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        out: dict[str, BgpNeighbor] = {}
        parse_bgp_summary(self._cli(f"show ip bgp summary vrf {vrf} | json", ev), vrf, "ipv4-unicast", out)
        try:
            parse_bgp_summary(self._cli(f"show ipv6 bgp summary vrf {vrf} | json", ev), vrf, "ipv6-unicast", out)
        except DriverError:
            pass  # no IPv6 BGP configured
        return Observation(out, ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        fam = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ip"
        rt = self._cli(f"show {fam} route vrf {vrf} {prefix} | json", ev)
        bgp = self._cli(f"show {fam} bgp {prefix} vrf {vrf} | json", ev)
        return Observation(parse_routes(rt, bgp, prefix, vrf), ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        ev: list[dict] = []
        fam = "ipv6" if family == 6 else "ip"
        out = []
        for key, r in (_vrf(_json(self._cli(f"show {fam} route vrf {vrf} | json", ev)), vrf).get("routes") or {}).items():
            rtype = str(r.get("routeType", "")).lower().replace(" ", "")
            out.append(Route(key, PROTOCOLS.get(rtype, rtype), True))
        return Observation(out, ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        fam = "ipv6 " if ipaddress.ip_address(target).version == 6 else ""
        cmd = f"ping {fam}vrf {vrf} {target} repeat {count}" + (f" source {source}" if source else "")
        r = self.lab.exec(self.node, ["Cli", "-p", "15", "-c", cmd], timeout=count * 2 + 15)
        ev.append({"node": self.node, "cmd": f"Cli -c {cmd}", "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        return Observation(parse_ping(r.stdout), ev)
