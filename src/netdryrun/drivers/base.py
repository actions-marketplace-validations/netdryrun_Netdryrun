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
class BgpPath:
    """One path for a prefix in the BGP table. None means the attribute could not be read."""
    best: bool
    as_path: str | None             # ASNs separated by spaces, sets as {a,b}; "" for a locally originated route
    next_hop: str | None
    local_pref: int | None          # effective value: the default local preference when the path carries none
    med: int | None                 # a path without MED counts as 0, as best-path selection treats it by default
    communities: list[str] = field(default_factory=list)        # canonical (config.parse_community), standard
    large_communities: list[str] = field(default_factory=list)  # canonical a:b:c
    neighbor: str | None = None
    # The router's own non-BGP route listed in its BGP table, possibly not advertised at all (SR Linux lists
    # its static and interface routes this way). Counts for best-path checks, not for `present: false`.
    local_candidate: bool = False

    def all_communities(self) -> list[str]:
        return self.communities + self.large_communities


def canon_communities(tokens) -> list[str]:
    """Device community strings in the canonical form used by netdryrun.yml; unknown names kept as printed."""
    from ..config import parse_community
    out = []
    for t in tokens or []:
        try:
            out.append(parse_community(t))
        except ValueError:
            out.append(str(t).strip().lower())
    return out


def render_as_path(segments: list[tuple[str, list]]) -> str:
    """(segment type, ASNs) pairs to the netdryrun.yml form: sequences space-separated, sets {a,b},
    confederation sequences (a b), confederation sets [a,b]."""
    parts = []
    for kind, members in segments:
        asns = [str(int(a)) for a in members]
        kind = kind.lower().replace("_", "-")
        if kind in ("as-set", "set"):
            parts.append("{" + ",".join(asns) + "}")
        elif "confed" in kind and "set" in kind:
            parts.append("[" + ",".join(asns) + "]")
        elif "confed" in kind:
            parts.append("(" + " ".join(asns) + ")")
        else:
            parts += asns
    return " ".join(parts)


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

    # bgp_route keys this driver cannot read; a check that uses one is a setup error, never a guess
    unsupported_bgp_attributes: frozenset[str] = frozenset()

    def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
        """Every path for exactly `prefix` in the BGP table (list[BgpPath]), best path flagged."""
        raise NotImplementedError

    def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
        """Every route in the table (used by `netdryrun record`)."""
        raise NotImplementedError
