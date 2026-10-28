"""`netdryrun record`: snapshot a known-good running lab into a netdryrun.yml baseline.

The recorded file asserts today's behavior: every established BGP session stays up, prefix
counts stay the same, and every BGP-learned route stays present. Run it once on the network
as it is (before a change), commit the file, then every future change is tested against it.
"""
from __future__ import annotations

import ipaddress
import math
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__
from .config import community_name
from .drivers import DriverError, detect, for_node
from .lab import Lab

MAX_ROUTES_PER_NODE = 50
MAX_LINK_GUARDS_PER_NODE = 20


def prefix_range(count: int) -> dict:
    """The default prefix-count check (0.3.3): today's count as the floor, and headroom for normal growth
    (20%, at least 2) as the ceiling, which still catches a leak that multiplies the count. A neighbor that
    sends nothing stays at exactly 0 (min: 0 would be refused, and any prefix from it is new)."""
    if count == 0:
        return {"exact": 0}
    return {"min": count, "max": count + max(2, math.ceil(count / 5))}


def record(topology: Path, include_routes: bool = True, prefix_mode: str = "range", attributes: bool = False,
           guards: bool = False, log=lambda _: None) -> tuple[dict, list[str]]:
    """Return (netdryrun.yml data, warnings) for the running lab described by `topology`.
    prefix_mode: "range" (default: prefix_range), "exact", or "min".
    With `attributes`, each recorded BGP route also gets a bgp_route check pinning its best path's
    AS path, local preference and communities (not MED or next hop, which follow the topology).
    With `guards`, the standard guard recipes that can be read from the lab: no default route via BGP, and
    no link subnet of the topology via BGP, on every BGP node, except what the node learns via BGP today."""
    if prefix_mode not in ("range", "exact", "min"):
        raise ValueError(f"prefix_mode must be range, exact or min, got {prefix_mode!r}")
    lab = Lab(topology)
    warnings: list[str] = []
    checks: list[dict] = []
    link_subnets = _link_subnets(lab) if guards else []
    for name, node in lab.nodes.items():
        try:
            detect(node)
        except DriverError:
            warnings.append(f"{name}: no driver for kind={node.kind!r} image={node.image!r}; skipped")
            continue
        drv = for_node(lab, name)
        log(f"recording {name} ({drv.name})")
        if drv.name == "sonic":
            warnings.append(f"{name}: SONiC is configured after boot; add its commands under nodes.{name}.setup "
                            "or the checks will fail on a fresh deploy")
        try:
            neighbors = drv.bgp_neighbors().value
        except DriverError as e:
            warnings.append(f"{name}: could not read BGP state ({e}); skipped")
            continue
        for addr, n in sorted(neighbors.items()):
            try:
                ipaddress.ip_address(addr)
            except ValueError:
                warnings.append(f"{name}: BGP neighbor {addr!r} is not an IP address (unnumbered?); not recorded")
                continue
            if n.state != "established":
                warnings.append(f"{name}: BGP neighbor {addr} is {n.state}; not recorded (fix it or add a check by hand)")
                continue
            checks.append({"type": "bgp_session", "node": name, "neighbor": addr})
            for afi, count in sorted(n.prefixes.items()):
                c = {"type": "bgp_prefixes", "node": name, "neighbor": addr, "afi": afi}
                if prefix_mode == "exact":
                    c["exact"] = count
                elif prefix_mode == "min" and count > 0:
                    c["min"] = count
                else:
                    c.update(prefix_range(count))
                checks.append(c)
        bgp_now: dict[int, set[str]] = {}   # every BGP route the node has today, received selected or not
        if include_routes or guards:
            for fam in (4, 6):
                try:
                    every = [r for r in drv.all_routes(family=fam).value if r.protocol == "bgp"]
                except DriverError as e:
                    warnings.append(f"{name}: could not read IPv{fam} routes ({e})")
                    continue
                bgp_now[fam] = {r.prefix for r in every}
                if not include_routes:
                    continue
                routes = [r for r in every if r.active]
                if len(routes) > MAX_ROUTES_PER_NODE:
                    warnings.append(f"INCOMPLETE BASELINE: {name} has {len(routes)} BGP routes (IPv{fam}); only the "
                                    f"first {MAX_ROUTES_PER_NODE} are recorded as checks. A change to any other route "
                                    "goes unnoticed: add checks for the routes that matter")
                for r in sorted(routes, key=lambda r: r.prefix)[:MAX_ROUTES_PER_NODE]:
                    checks.append({"type": "route", "node": name, "prefix": r.prefix, "protocol": "bgp"})
                    if attributes:
                        try:
                            c = _attribute_check(drv, name, r.prefix)
                        except DriverError as e:
                            warnings.append(f"{name}: could not read BGP attributes of {r.prefix} ({e})")
                            continue
                        if c:
                            checks.append(c)
        if guards and neighbors:
            checks += _guards(name, neighbors, bgp_now, link_subnets, warnings)
    data = {"lab": topology.name, "timeout": 120, "checks": checks}
    return data, warnings


def _link_subnets(lab) -> list[str]:
    """The subnets of the topology's links, from the addresses on their interfaces."""
    nets: set = set()
    for end in (e for link in lab.links for e in link):
        try:
            nets |= {a.network for a in lab.interface_addresses(*end) if not a.ip.is_link_local}
        except Exception:   # an endpoint that isn't a container (a bridge, a host link): no address to read
            continue
    return [str(n) for n in sorted(nets, key=lambda n: (n.version, n))]


def _guards(name: str, neighbors: dict, bgp_now: dict[int, set[str]], link_subnets: list[str],
            warnings: list[str]) -> list[dict]:
    """--guards for one BGP node: checks that must never pass on what the network does today."""
    v6 = any(":" in a for a in neighbors) or bool(bgp_now.get(6))
    out = []
    for fam, default in ((4, "0.0.0.0/0"), (6, "::/0")):
        if (fam == 6 and not v6) or fam not in bgp_now:   # no IPv6 BGP; or its routes couldn't be read (warned)
            continue
        if default in bgp_now[fam]:
            warnings.append(f"{name}: learns {default} via BGP today; no 'no default route' guard recorded")
            continue
        out.append({"type": "route", "node": name, "prefix": default, "protocol": "bgp", "present": False})
    # a subnet the node learns via BGP today, or whose family couldn't be read, gets no guard
    links = [n for n in link_subnets if n not in bgp_now.get(6 if ":" in n else 4, {n})]
    if len(links) > MAX_LINK_GUARDS_PER_NODE:
        warnings.append(f"{name}: {len(links)} link subnets; guarded the first {MAX_LINK_GUARDS_PER_NODE}")
    out += [{"type": "route", "node": name, "prefix": n, "protocol": "bgp", "present": False}
            for n in links[:MAX_LINK_GUARDS_PER_NODE]]
    return out


def _attribute_check(drv, node: str, prefix: str) -> dict | None:
    best = next((p for p in drv.bgp_paths(prefix).value if p.best), None)
    if best is None:
        return None
    c: dict = {"type": "bgp_route", "node": node, "prefix": prefix}
    if best.as_path is not None:
        c["as_path"] = best.as_path
    if best.local_pref is not None:
        c["local_pref"] = best.local_pref
    if best.all_communities():
        c["communities"] = [community_name(x) for x in best.all_communities()]
    return c


def render(data: dict, warnings: list[str]) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    head = [
        f"# Recorded by netdryrun {__version__} record on {stamp}.",
        "# This is a baseline of the network's behavior when it was recorded. Review it before committing:",
        "# remove anything that is allowed to change, and add negative checks (route present: false,",
        "# ping expect: failure) for things that must never happen. Docs: https://netdryrun.com/reference/config/",
    ]
    # one comment line per warning: device output in a warning must not add YAML (a setup command) to the file
    head += [f"# warning: {' '.join(str(w).split())}" for w in warnings]
    incomplete = [" ".join(str(w).split()) for w in warnings if str(w).startswith("INCOMPLETE BASELINE")]
    if incomplete:   # first in the file, so nobody commits a partial baseline without seeing it
        head = [f"# {w}" for w in incomplete] + ["#"] + head
    return "\n".join(head) + "\n" + yaml.safe_dump(data, sort_keys=False, width=200)
