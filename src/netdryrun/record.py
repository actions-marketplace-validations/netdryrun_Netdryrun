"""`netdryrun record`: snapshot a known-good running lab into a netdryrun.yml baseline.

The recorded file asserts today's behavior: every established BGP session stays up, prefix
counts stay the same, and every BGP-learned route stays present. Run it once on the network
as it is (before a change), commit the file, then every future change is tested against it.
"""
from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import __version__
from .config import community_name
from .drivers import DriverError, detect, for_node
from .drivers.base import NoSuchInstance
from .lab import Lab

MAX_ROUTES_PER_NODE = 50


def record(topology: Path, include_routes: bool = True, exact_prefixes: bool = True, attributes: bool = False,
           log=lambda _: None) -> tuple[dict, list[str]]:
    """Return (netdryrun.yml data, warnings) for the running lab described by `topology`.
    With `attributes`, each recorded BGP route also gets a bgp_route check pinning its best path's
    AS path, local preference and communities (not MED or next hop, which follow the topology)."""
    lab = Lab(topology)
    warnings: list[str] = []
    checks: list[dict] = []
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
        vrfs = ["default"]
        try:
            vrfs += [v for v in drv.vrfs().value if v != "default"]
        except DriverError as e:
            warnings.append(f"{name}: only the default VRF is recorded ({e}); add checks for other VRFs by hand")
        for vrf in vrfs:
            _record_vrf(drv, name, vrf, checks, warnings, include_routes, exact_prefixes, attributes)
    data = {"lab": topology.name, "timeout": 120, "checks": checks}
    return data, warnings


def _record_vrf(drv, name: str, vrf: str, checks: list[dict], warnings: list[str], include_routes: bool,
                exact_prefixes: bool, attributes: bool) -> None:
    """One VRF of one node; every check carries `vrf:` outside the default VRF."""
    at = {} if vrf == "default" else {"vrf": vrf}
    where = name if vrf == "default" else f"{name} (vrf {vrf})"
    try:
        neighbors = drv.bgp_neighbors(vrf).value
    except NoSuchInstance as e:
        if vrf == "default":
            warnings.append(f"{where}: could not read BGP state ({e}); skipped")
        return   # a VRF without a BGP instance: no session or BGP route to record
    except DriverError as e:
        warnings.append(f"{where}: could not read BGP state ({e}); skipped")
        return
    for addr, n in sorted(neighbors.items()):
        try:
            ipaddress.ip_address(addr)
        except ValueError:
            warnings.append(f"{where}: BGP neighbor {addr!r} is not an IP address (unnumbered?); not recorded")
            continue
        if n.state != "established":
            warnings.append(f"{where}: BGP neighbor {addr} is {n.state}; not recorded (fix it or add a check by hand)")
            continue
        checks.append({"type": "bgp_session", "node": name, "neighbor": addr, **at})
        for afi, count in sorted(n.prefixes.items()):
            c = {"type": "bgp_prefixes", "node": name, "neighbor": addr, "afi": afi, **at}
            if exact_prefixes:
                c["exact"] = count
            else:
                c["min"] = count
            checks.append(c)
    if include_routes:
        for fam in (4, 6):
            try:
                routes = [r for r in drv.all_routes(vrf=vrf, family=fam).value if r.protocol == "bgp" and r.active]
            except DriverError as e:
                warnings.append(f"{where}: could not read IPv{fam} routes ({e})")
                continue
            if len(routes) > MAX_ROUTES_PER_NODE:
                warnings.append(f"{where}: {len(routes)} BGP routes (IPv{fam}); recorded the first {MAX_ROUTES_PER_NODE}")
            for r in sorted(routes, key=lambda r: r.prefix)[:MAX_ROUTES_PER_NODE]:
                checks.append({"type": "route", "node": name, "prefix": r.prefix, "protocol": "bgp", **at})
                if attributes:
                    try:
                        c = _attribute_check(drv, name, r.prefix, vrf)
                    except DriverError as e:
                        warnings.append(f"{where}: could not read BGP attributes of {r.prefix} ({e})")
                        continue
                    if c:
                        checks.append(c)


def _attribute_check(drv, node: str, prefix: str, vrf: str = "default") -> dict | None:
    best = next((p for p in drv.bgp_paths(prefix, vrf=vrf).value if p.best), None)
    if best is None:
        return None
    c: dict = {"type": "bgp_route", "node": node, "prefix": prefix, **({} if vrf == "default" else {"vrf": vrf})}
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
    return "\n".join(head) + "\n" + yaml.safe_dump(data, sort_keys=False, width=200)
