"""Driver interface. Every method returns normalized data plus the raw evidence it came from."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..lab import Lab


class DriverError(RuntimeError):
    pass


@dataclass
class BgpNeighbor:
    address: str
    state: str                                          # lower-case, e.g. "established"
    prefixes: dict[str, int] = field(default_factory=dict)  # afi -> accepted/received prefixes


@dataclass
class Route:
    prefix: str
    protocol: str   # lower-case, e.g. "bgp", "connected", "static"
    active: bool


@dataclass
class Observation:
    """What a driver saw, with the raw command output kept as evidence."""
    value: object
    evidence: list[dict]


class Driver:
    name = "base"

    def __init__(self, lab: Lab, node: str):
        self.lab = lab
        self.node = node

    def _exec(self, cmd: list[str], evidence: list[dict], timeout: float = 60) -> str:
        """Run a state command; a failing command is an error, never silently 'empty state'."""
        r = self.lab.exec(self.node, cmd, timeout=timeout)
        evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
        if r.rc != 0:
            msg = (r.stderr or r.stdout).strip().splitlines()
            raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
        return r.stdout

    def bgp_neighbors(self, vrf: str = "default") -> Observation:
        raise NotImplementedError

    def routes(self, prefix: str, vrf: str = "default") -> Observation:
        raise NotImplementedError

    def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
        raise NotImplementedError

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        """Every route in the table (used by `netdryrun record`)."""
        raise NotImplementedError
