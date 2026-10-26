"""FRRouting driver: vtysh JSON output plus ping from the container."""
from __future__ import annotations

import ipaddress
import json
import re

from .base import BgpNeighbor, Driver, Observation, Route

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
