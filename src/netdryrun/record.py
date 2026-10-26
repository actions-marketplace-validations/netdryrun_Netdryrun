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
from .drivers import DriverError, detect, for_node
from .lab import Lab

MAX_ROUTES_PER_NODE = 50


def record(topology: Path, include_routes: bool = True, exact_prefixes: bool = True,
           log=lambda _: None) -> tuple[dict, list[str]]:
    """Return (netdryrun.yml data, warnings) for the running lab described by `topology`."""
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
                if exact_prefixes:
                    c["exact"] = count
                else:
                    c["min"] = count
                checks.append(c)
        if include_routes:
            for fam in (4, 6):
                try:
                    routes = [r for r in drv.all_routes(family=fam).value if r.protocol == "bgp" and r.active]
                except DriverError as e:
                    warnings.append(f"{name}: could not read IPv{fam} routes ({e})")
                    continue
                if len(routes) > MAX_ROUTES_PER_NODE:
                    warnings.append(f"{name}: {len(routes)} BGP routes (IPv{fam}); recorded the first {MAX_ROUTES_PER_NODE}")
                for r in sorted(routes, key=lambda r: r.prefix)[:MAX_ROUTES_PER_NODE]:
                    checks.append({"type": "route", "node": name, "prefix": r.prefix, "protocol": "bgp"})
    data = {"lab": topology.name, "timeout": 120, "checks": checks}
    return data, warnings


def render(data: dict, warnings: list[str]) -> str:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    head = [
        f"# Recorded by netdryrun {__version__} record on {stamp}.",
        "# This is a baseline of the network's behavior when it was recorded. Review it before committing:",
        "# remove anything that is allowed to change, and add negative checks (route present: false,",
        "# ping expect: failure) for things that must never happen. Docs: https://netdryrun.com/reference/config/",
    ]
    head += [f"# warning: {w}" for w in warnings]
    return "\n".join(head) + "\n" + yaml.safe_dump(data, sort_keys=False, width=200)
