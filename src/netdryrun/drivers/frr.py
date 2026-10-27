"""FRRouting driver: vtysh JSON output plus ping from the container."""
from __future__ import annotations

import ipaddress
import json
import re

from .base import BgpNeighbor, BgpPath, Driver, DriverError, Observation, Route, canon_communities, render_as_path

AFI_NAMES = {"ipv4Unicast": "ipv4-unicast", "ipv6Unicast": "ipv6-unicast", "l2VpnEvpn": "evpn"}


def _canon_addr(addr: str) -> str:
    """Canonical address key so 2001:db8:0::1 and 2001:db8::1 match; non-IP keys (interfaces) kept."""
    try:
        return str(ipaddress.ip_address(addr.split("%")[0]))
    except ValueError:
        return addr


def parse_bgp_neighbors(text: str) -> dict[str, BgpNeighbor]:
    data = json.loads(text or "{}")
    out = {}
    for addr, info in data.items():
        if not isinstance(info, dict) or "bgpState" not in info:
            continue
        prefixes = {}
        for afi, af in (info.get("addressFamilyInfo") or {}).items():
            if isinstance(af, dict) and "acceptedPrefixCounter" in af:
                prefixes[AFI_NAMES.get(afi, afi)] = int(af["acceptedPrefixCounter"])
        # "Idle (Admin)" -> "idle": the first word is the FSM state
        out[_canon_addr(addr)] = BgpNeighbor(addr, str(info["bgpState"]).split()[0].lower(), prefixes)
    return out


def parse_routes(text: str, prefix: str) -> list[Route]:
    data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"unexpected vtysh route output: {text.strip()[:200]}")
    want = ipaddress.ip_network(prefix)
    out = []
    for key, entries in data.items():
        try:
            if ipaddress.ip_network(key) != want:
                continue
        except ValueError:
            continue
        if not isinstance(entries, list):
            raise ValueError(f"unexpected vtysh route entry for {key}: {str(entries)[:200]}")
        out += [Route(prefix, str(e.get("protocol", "")).lower(), bool(e.get("selected")) and bool(e.get("installed", True)))
                for e in entries]
    return out


def parse_all_routes(text: str) -> list[Route]:
    data = json.loads(text or "{}")
    out = []
    for prefix, entries in (data.items() if isinstance(data, dict) else []):
        for e in entries if isinstance(entries, list) else []:
            out.append(Route(prefix, str(e.get("protocol", "")).lower(),
                             bool(e.get("selected")) and bool(e.get("installed", True))))
    return out


def _bgp_json(text: str) -> dict:
    data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"unexpected vtysh BGP output: {text.strip()[:200]}")
    if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
        raise DriverError(f"vtysh: {data['warning']}")
    return data


def _next_hop(hops: list) -> str | None:
    """The global next hop (an IPv6 path may also list a link-local one); link-local only if nothing else."""
    hops = [h for h in hops if isinstance(h, dict) and h.get("ip")]
    best = next((h for h in hops if h.get("scope", "global") == "global"), hops[0] if hops else None)
    return _canon_addr(best["ip"]) if best else None


def parse_bgp_paths(text: str, prefix: str, default_local_pref: int | None = 100) -> list[BgpPath]:
    """`show bgp <afi> unicast <prefix> json`. A path without locPrf carries no LOCAL_PREF attribute
    (eBGP-learned or local), and FRR applies the instance's default local preference to it."""
    data = _bgp_json(text)
    if data.get("prefix") and ipaddress.ip_network(data["prefix"]) != ipaddress.ip_network(prefix):
        return []
    out = []
    for p in data.get("paths") or []:
        segs = [(s.get("type", ""), s.get("list") or []) for s in (p.get("aspath") or {}).get("segments") or []]
        out.append(BgpPath(
            best=bool((p.get("bestpath") or {}).get("overall")),
            as_path=render_as_path(segs),  # not aspath.string: FRR prints "Local" for an empty path
            next_hop=_next_hop(p.get("nexthops") or []),
            local_pref=int(p["locPrf"]) if "locPrf" in p else default_local_pref,
            med=int(p.get("metric", 0)),
            communities=canon_communities(((p.get("community") or {}).get("string") or "").split()),
            large_communities=canon_communities(((p.get("largeCommunity") or {}).get("string") or "").split()),
            neighbor=(p.get("peer") or {}).get("peerId"),
        ))
    return out


def parse_default_local_pref(text: str) -> int | None:
    """defaultLocPrf from the header of a BGP table listing (`bgp default local-preference`)."""
    v = _bgp_json(text).get("defaultLocPrf")
    return int(v) if v is not None else None


def parse_ping(text: str) -> tuple[int, int]:
    m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", text)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


class FrrDriver(Driver):
    name = "frr"

    def _vtysh(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["vtysh", "-c", command], evidence)

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        cmd = "show bgp neighbors json" if vrf == "default" else f"show bgp vrf {vrf} neighbors json"
        return Observation(parse_bgp_neighbors(self._vtysh(cmd, ev)), ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        fam = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ip"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        text = self._vtysh(f"show {fam} route{vrf_part} {prefix} json", ev)
        return Observation(parse_routes(text, prefix), ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        ev: list[dict] = []
        fam = "ipv6" if family == 6 else "ip"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        return Observation(parse_all_routes(self._vtysh(f"show {fam} route{vrf_part} json", ev)), ev)

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        afi = "ipv6" if ipaddress.ip_network(prefix).version == 6 else "ipv4"
        vrf_part = "" if vrf == "default" else f" vrf {vrf}"
        text = self._vtysh(f"show bgp{vrf_part} {afi} unicast {prefix} json", ev)
        paths = parse_bgp_paths(text, prefix, default_local_pref=None)
        if any(p.local_pref is None for p in paths):
            # Some path has no LOCAL_PREF attribute: read the default it gets (an empty table listing)
            default = parse_default_local_pref(
                self._vtysh(f"show bgp{vrf_part} ipv4 unicast 255.255.255.255/32 longer-prefixes json", ev))
            paths = parse_bgp_paths(text, prefix, default_local_pref=default)
        return Observation(paths, ev)

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        cmd = ["ping", "-c", str(count), "-W", "1"]
        if source:
            cmd += ["-I", source]
        cmd.append(target)
        if vrf != "default":
            cmd = ["ip", "vrf", "exec", vrf, *cmd]
        r = self.lab.exec(self.node, cmd, timeout=count * 2 + 10)
        ev.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        return Observation(parse_ping(r.stdout), ev)
