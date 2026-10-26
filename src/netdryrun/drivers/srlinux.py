"""Nokia SR Linux driver: sr_cli JSON state, ping from the network-instance namespace."""
from __future__ import annotations

import ipaddress
import json

from .base import BgpNeighbor, Driver, DriverError, Observation, Route
from .frr import _canon_addr, parse_ping

# SR Linux route-type names -> the shared vocabulary used in netdryrun.yml (FRR's names)
PROTOCOLS = {"local": "connected", "host": "local", "ospfv2": "ospf", "ospfv3": "ospf6"}


def _json(text: str) -> dict:
    if not text.strip():
        return {}  # sr_cli prints nothing when the path has no entries
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise DriverError(f"unexpected sr_cli output: {text.strip()[:200]}") from None
    return data if isinstance(data, dict) else {}


def parse_bgp_neighbors(text: str) -> dict[str, BgpNeighbor]:
    out = {}
    for n in _json(text).get("neighbor", []):
        prefixes = {}
        for af in n.get("afi-safi", []):
            if "received-routes" in af:
                # accepted = received minus rejected by import policy (matches FRR's acceptedPrefixCounter)
                prefixes[af["afi-safi-name"]] = int(af["received-routes"]) - int(af.get("rejected-routes", 0))
        addr = str(n.get("peer-address", ""))
        out[_canon_addr(addr)] = BgpNeighbor(addr, str(n.get("session-state", "")).lower(), prefixes)
    return out


def parse_routes(text: str, prefix: str, bgp_rib_text: str = "") -> list[Route]:
    """Route-table entries for `prefix`, plus BGP-RIB paths that aren't installed.

    SR Linux's route table only holds installed routes. A BGP path that lost to a static or local
    route (a leak that's received but not selected) only shows in the BGP RIB, and must still count
    as present for `present: false`.
    """
    want = ipaddress.ip_network(prefix)
    key = "ipv6-prefix" if want.version == 6 else "ipv4-prefix"
    out = []
    for r in _json(text).get("route", []):
        try:
            if ipaddress.ip_network(str(r.get(key))) != want:
                continue
        except ValueError:
            continue
        rtype = str(r.get("route-type", "")).lower()
        out.append(Route(prefix, PROTOCOLS.get(rtype, rtype), bool(r.get("active"))))
    if not any(r.protocol == "bgp" and r.active for r in out):
        for r in _json(bgp_rib_text).get("route", []):
            try:
                same = ipaddress.ip_network(str(r.get("prefix"))) == want
            except ValueError:
                continue
            if same and r.get("valid-route", True):
                out.append(Route(prefix, "bgp", False))
                break
    return out


class SrlDriver(Driver):
    name = "srlinux"

    def _cli(self, command: str, evidence: list[dict]) -> str:
        return self._exec(["sr_cli", "--output-format", "json", command], evidence)

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        text = self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor *", ev)
        return Observation(parse_bgp_neighbors(text), ev)

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        table = "ipv6-unicast" if ipaddress.ip_network(prefix).version == 6 else "ipv4-unicast"
        text = self._cli(
            f"info from state /network-instance {vrf} route-table {table} route {prefix} "
            "id * route-type * route-owner * origin-network-instance *",
            ev,
        )
        rib = self._cli(
            f"info from state /network-instance {vrf} bgp-rib afi-safi {table} {table} local-rib route {prefix} "
            "neighbor * origin-protocol * path-id *",
            ev,
        )
        return Observation(parse_routes(text, prefix, rib), ev)

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        ev: list[dict] = []
        table, key = ("ipv6-unicast", "ipv6-prefix") if family == 6 else ("ipv4-unicast", "ipv4-prefix")
        text = self._cli(f"info from state /network-instance {vrf} route-table {table} route * "
                         "id * route-type * route-owner * origin-network-instance *", ev)
        out = []
        for r in _json(text).get("route", []):
            rtype = str(r.get("route-type", "")).lower()
            out.append(Route(str(r.get(key, "")), PROTOCOLS.get(rtype, rtype), bool(r.get("active"))))
        return Observation(out, ev)

    def _netns(self, vrf: str) -> str:
        """Linux namespace of a network-instance: srbase-<name>; some releases name default plain 'srbase'."""
        r = self.lab.exec(self.node, ["ip", "netns", "list"], timeout=15)
        names = {line.split()[0] for line in r.stdout.splitlines() if line.strip()}
        wanted = f"srbase-{vrf}"
        if wanted in names or vrf != "default":
            return wanted
        return "srbase" if "srbase" in names else wanted

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        ev: list[dict] = []
        ping = "ping6" if ipaddress.ip_address(target).version == 6 else "ping"
        cmd = ["ip", "netns", "exec", self._netns(vrf), ping, "-c", str(count), "-W", "1"]
        if source:
            cmd += ["-I", source]
        cmd.append(target)
        r = self.lab.exec(self.node, cmd, timeout=count * 2 + 10)
        ev.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-5000:], "stderr": r.stderr[-1000:]})
        return Observation(parse_ping(r.stdout), ev)
