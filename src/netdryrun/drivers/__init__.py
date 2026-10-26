"""Per-platform drivers that turn device state into a common shape."""
from __future__ import annotations

from ..lab import Lab, Node
from .base import Driver, DriverError
from .eos import EosDriver
from .frr import FrrDriver
from .srlinux import SrlDriver

DRIVERS: dict[str, type[Driver]] = {"frr": FrrDriver, "srlinux": SrlDriver, "eos": EosDriver}


def detect(node: Node) -> str:
    if node.kind in ("nokia_srlinux", "srl"):
        return "srlinux"
    if node.kind in ("arista_ceos", "ceos"):
        return "eos"
    if "frr" in node.image.lower():
        return "frr"
    raise DriverError(
        f"cannot detect driver for node {node.name} (kind={node.kind!r}, image={node.image!r}); "
        f"set nodes.{node.name}.driver in netdryrun.yml to one of {sorted(DRIVERS)}"
    )


def for_node(lab: Lab, node: str, override: str | None = None) -> Driver:
    if node not in lab.nodes:
        raise DriverError(f"node {node!r} is not in the topology (nodes: {', '.join(lab.nodes)})")
    name = override or detect(lab.nodes[node])
    if name not in DRIVERS:
        raise DriverError(f"unknown driver {name!r} for node {node}; expected one of {sorted(DRIVERS)}")
    return DRIVERS[name](lab, node)


__all__ = ["Driver", "DriverError", "DRIVERS", "detect", "for_node"]
