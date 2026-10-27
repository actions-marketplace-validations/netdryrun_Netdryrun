"""Load and validate netdryrun.yml."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .faults import parse_inject

CHECK_TYPES = {
    "bgp_session": {"required": ("node", "neighbor"), "optional": ("state", "vrf")},
    "bgp_prefixes": {"required": ("node", "neighbor"), "optional": ("min", "max", "exact", "afi", "vrf")},
    "route": {"required": ("node", "prefix"), "optional": ("present", "protocol", "vrf", "active")},
    "bgp_route": {"required": ("node", "prefix"), "optional": ("present", "vrf", "communities", "without_communities",
                                                              "as_path", "as_path_regex", "local_pref", "med", "next_hop")},
    "ping": {"required": ("node", "target"), "optional": ("source", "expect", "vrf", "count", "min_replies")},
}
BGP_ATTRIBUTES = ("communities", "without_communities", "as_path", "as_path_regex", "local_pref", "med", "next_hop")
COMMON_KEYS = ("type", "name", "timeout", "hold")
BGP_STATES = ("idle", "connect", "active", "opensent", "openconfirm", "established", "down")  # down = any state except established


class ConfigError(ValueError):
    pass


# Well-known communities (RFC 1997, 3765, 7611, 7999, 8326, 8642, 9494) by the name most CLIs print
WELL_KNOWN_COMMUNITIES = {
    "graceful-shutdown": "65535:0", "accept-own": "65535:1", "llgr-stale": "65535:6", "no-llgr": "65535:7",
    "blackhole": "65535:666", "no-export": "65535:65281", "no-advertise": "65535:65282",
    "no-export-subconfed": "65535:65283", "local-as": "65535:65283", "no-peer": "65535:65284",
}
_COMMUNITY_NAMES = {v: k for k, v in WELL_KNOWN_COMMUNITIES.items() if k != "local-as"}


def parse_community(text: str) -> str:
    """Canonical form of a standard (`65000:100`), large (`65000:1:2`) or well-known (`no-export`)
    community: numbers without leading zeros, well-known names as their 65535:x value."""
    t = str(text).strip().lower().replace("_", "-")
    if t in WELL_KNOWN_COMMUNITIES:
        return WELL_KNOWN_COMMUNITIES[t]
    parts = t.split(":")
    if len(parts) in (2, 3) and all(x.isdigit() for x in parts):
        nums = [int(x) for x in parts]
        limit = 0xFFFF if len(parts) == 2 else 0xFFFFFFFF
        if all(n <= limit for n in nums):
            return ":".join(str(n) for n in nums)
    raise ValueError(f"bad community {text!r}: use 65000:100 (standard), 65000:1:2 (large) or a well-known name "
                     f"({', '.join(sorted(WELL_KNOWN_COMMUNITIES))})")


def community_name(canonical: str) -> str:
    """How a canonical community is shown in reports: well-known ones by name."""
    return _COMMUNITY_NAMES.get(canonical, canonical)


def normalize_as_path(value: Any) -> str:
    """An AS path as space-separated ASNs; AS sets as {a,b}. "" is the empty path (a locally originated route)."""
    if isinstance(value, bool):
        raise ValueError("as_path must be a string such as '65002 65003'")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return " ".join(str(normalize_as_path(v)) for v in value)
    text = re.sub(r"\s*,\s*", ",", str(value).strip())
    tokens = text.split()
    if not all(re.fullmatch(r"\d+|\{\d+(,\d+)*\}|\(\d+|\d+\)|\(\d+\)", t) for t in tokens):
        raise ValueError(f"bad as_path {value!r}: use ASNs separated by spaces, for example '65002 65003'")
    return " ".join(tokens)


@dataclass
class Check:
    type: str
    params: dict[str, Any]
    name: str
    timeout: float
    hold: float | None = None  # per-check hold window for post-convergence checks

    @property
    def node(self) -> str:
        return self.params["node"]


@dataclass
class Config:
    path: Path
    lab: Path
    timeout: float
    checks: list[Check]
    drivers: dict[str, str] = field(default_factory=dict)  # node -> driver override
    scenarios: list["Scenario"] = field(default_factory=list)
    setup: dict[str, list[str]] = field(default_factory=dict)   # node -> commands run after deploy


@dataclass
class Fault:
    kind: str          # "link_down", "node_isolated" or "inject_routes"
    node: str
    interface: str | None = None
    prefixes: list[str] = field(default_factory=list)   # inject_routes
    as_path: list[int] = field(default_factory=list)    # inject_routes: ASNs prepended to the injected routes

    def describe(self) -> str:
        if self.kind == "inject_routes":
            return f"{self.node} injects {len(self.prefixes)} route(s)"
        return f"{self.node} {self.interface} down" if self.kind == "link_down" else f"{self.node} isolated"


@dataclass
class Scenario:
    name: str
    faults: list[Fault]
    checks: list[Check]


def _describe(ctype: str, p: dict[str, Any]) -> str:
    if ctype == "bgp_session":
        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
    if ctype == "bgp_prefixes":
        rng = []
        if "exact" in p:
            rng.append(f"= {p['exact']}")
        if "min" in p:
            rng.append(f">= {p['min']}")
        if "max" in p:
            rng.append(f"<= {p['max']}")
        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
    if ctype == "route":
        verb = "present" if p.get("present", True) else "absent"
        via = f" via {p['protocol']}" if p.get("protocol") else ""
        return f"{p['node']}: route {p['prefix']}{via} is {verb}"
    if ctype == "bgp_route":
        if p.get("present", True) is False:
            return f"{p['node']}: no BGP path for {p['prefix']}"
        parts = []
        if p.get("communities"):
            parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
        if p.get("without_communities"):
            parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
        if "as_path" in p:
            parts.append(f"as-path '{p['as_path']}'")
        if "as_path_regex" in p:
            parts.append(f"as-path matching /{p['as_path_regex']}/")
        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
            if key in p:
                parts.append(f"{label} {p[key]}")
        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
    if ctype == "ping":
        exp = p.get("expect", "success")
        src = f" from {p['source']}" if p.get("source") else ""
        return f"{p['node']}: ping {p['target']}{src} expects {exp}"
    return ctype


def _validate_check(i: int, raw: Any, default_timeout: float) -> Check:
    where = f"checks[{i}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a mapping")
    ctype = raw.get("type")
    if ctype not in CHECK_TYPES:
        raise ConfigError(f"{where}: unknown type {ctype!r}; expected one of {sorted(CHECK_TYPES)}")
    spec = CHECK_TYPES[ctype]
    allowed = set(spec["required"]) | set(spec["optional"]) | set(COMMON_KEYS)
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(f"{where}: unknown keys {sorted(unknown)} for type {ctype}")
    for key in spec["required"]:
        if key not in raw:
            raise ConfigError(f"{where}: missing required key {key!r}")
    params = {k: v for k, v in raw.items() if k not in COMMON_KEYS}
    try:
        # canonical spellings so 2001:db8:0::1 in YAML matches 2001:db8::1 on the device
        if ctype in ("route", "bgp_route"):
            params["prefix"] = str(ipaddress.ip_network(str(params["prefix"]), strict=False))
        for key in ("neighbor", "target", "source", "next_hop"):
            if key in params:
                params[key] = str(ipaddress.ip_address(str(params[key])))
    except ValueError as e:
        raise ConfigError(f"{where}: {e}") from None
    for key in ("min", "max", "exact", "count", "min_replies", "local_pref", "med"):
        if key in params and (isinstance(params[key], bool) or not isinstance(params[key], int) or params[key] < 0):
            raise ConfigError(f"{where}: {key} must be a non-negative integer")
    if "exact" in params and ({"min", "max"} & set(params)):
        raise ConfigError(f"{where}: use exact on its own, or min/max, not both")
    if params.get("min", 0) > params.get("max", float("inf")):
        raise ConfigError(f"{where}: min is greater than max")
    for key in ("timeout", "hold"):
        if key in raw and (not isinstance(raw[key], (int, float)) or isinstance(raw[key], bool) or raw[key] <= 0):
            raise ConfigError(f"{where}: {key} must be a positive number of seconds")
    if "vrf" in params:
        params["vrf"] = str(params["vrf"])
    if ctype == "bgp_session":
        params["state"] = str(params.get("state", "established")).lower()
        if params["state"] not in BGP_STATES:
            raise ConfigError(f"{where}: state must be one of {', '.join(BGP_STATES)}")
    if ctype == "ping":
        params["expect"] = str(params.get("expect", "success")).lower()
        if params["expect"] not in ("success", "failure"):
            raise ConfigError(f"{where}: expect must be 'success' or 'failure'")
    if ctype == "bgp_prefixes" and not ({"min", "max", "exact"} & set(params)):
        raise ConfigError(f"{where}: bgp_prefixes needs at least one of min, max or exact")
    if ctype == "route" and "protocol" in params:
        params["protocol"] = str(params["protocol"]).lower()
    if ctype == "bgp_route":
        _validate_bgp_route(where, params)
    timeout = float(raw.get("timeout", default_timeout))
    hold = float(raw["hold"]) if "hold" in raw else None
    return Check(type=ctype, params=params, name=raw.get("name") or _describe(ctype, params), timeout=timeout, hold=hold)


def _validate_bgp_route(where: str, params: dict[str, Any]) -> None:
    if "present" in params and not isinstance(params["present"], bool):
        raise ConfigError(f"{where}: present must be true or false")
    attrs = [k for k in BGP_ATTRIBUTES if k in params]
    if params.get("present", True) is False and attrs:
        raise ConfigError(f"{where}: present: false means no BGP path at all, so it can't be combined with "
                          f"{', '.join(attrs)}; to forbid a community on the best path use without_communities")
    for key in ("communities", "without_communities"):
        if key not in params:
            continue
        raw = params[key] if isinstance(params[key], list) else [params[key]]
        if not raw:
            raise ConfigError(f"{where}: {key} must list at least one community")
        for c in raw:
            if isinstance(c, (int, float)) and not isinstance(c, bool):
                # YAML 1.1 reads 65000:10 (and 65000:1:2) unquoted as a base-60 number
                raise ConfigError(f"{where}: {key}: write communities as quoted strings, for example '65000:10'; "
                                  "YAML reads some unquoted values like 65000:10 as numbers")
        try:
            params[key] = [parse_community(c) for c in raw]
        except ValueError as e:
            raise ConfigError(f"{where}: {key}: {e}") from None
    both = set(params.get("communities", [])) & set(params.get("without_communities", []))
    if both:
        raise ConfigError(f"{where}: {', '.join(sorted(both))} is in both communities and without_communities")
    if "as_path" in params:
        try:
            params["as_path"] = normalize_as_path(params["as_path"])
        except ValueError as e:
            raise ConfigError(f"{where}: {e}") from None
    if "as_path_regex" in params:
        params["as_path_regex"] = str(params["as_path_regex"])
        try:
            re.compile(params["as_path_regex"])
        except re.error as e:
            raise ConfigError(f"{where}: as_path_regex is not a valid regular expression: {e}") from None


def load(path: str | Path) -> Config:
    path = Path(path)
    if path.is_dir():
        path = path / "netdryrun.yml"
    if not path.exists():
        raise ConfigError(f"{path}: not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    if "lab" not in data:
        raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
    lab = (path.parent / data["lab"]).resolve()
    if not lab.exists():
        raise ConfigError(f"{path}: lab file {lab} not found")
    timeout = float(data.get("timeout", 120))
    raw_checks = data.get("checks") or []
    if not raw_checks:
        raise ConfigError(f"{path}: no checks defined")
    checks = [_validate_check(i, c, timeout) for i, c in enumerate(raw_checks)]
    nodes_cfg = data.get("nodes") or {}
    drivers = {str(k): str(v.get("driver")) for k, v in nodes_cfg.items() if isinstance(v, dict) and v.get("driver")}
    setup: dict[str, list[str]] = {}
    for k, v in nodes_cfg.items():
        if isinstance(v, dict) and v.get("setup") is not None:
            cmds = v["setup"] if isinstance(v["setup"], list) else [v["setup"]]
            if not all(isinstance(x, str) and x.strip() for x in cmds):
                raise ConfigError(f"{path}: nodes.{k}.setup must be a list of shell commands")
            setup[str(k)] = cmds
    scenarios = [_validate_scenario(i, sc, timeout) for i, sc in enumerate(data.get("scenarios") or [])]
    return Config(path=path, lab=lab, timeout=timeout, checks=checks, drivers=drivers, scenarios=scenarios, setup=setup)


def _validate_scenario(i: int, raw: Any, default_timeout: float) -> Scenario:
    where = f"scenarios[{i}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a mapping")
    unknown = set(raw) - {"name", "link_down", "node_isolated", "inject_routes", "checks"}
    if unknown:
        raise ConfigError(f"{where}: unknown keys {sorted(unknown)}")
    faults = []
    for item in _as_list(raw.get("link_down")):
        if not isinstance(item, dict) or not {"node", "interface"} <= set(item):
            raise ConfigError(f"{where}: link_down needs node and interface")
        faults.append(Fault("link_down", str(item["node"]), str(item["interface"])))
    for item in _as_list(raw.get("node_isolated")):
        node = item.get("node") if isinstance(item, dict) else item
        if not node:
            raise ConfigError(f"{where}: node_isolated needs a node")
        faults.append(Fault("node_isolated", str(node)))
    for item in _as_list(raw.get("inject_routes")):
        try:
            inj = parse_inject(where, item)
        except ValueError as e:
            raise ConfigError(str(e)) from None
        faults.append(Fault("inject_routes", inj["node"], prefixes=inj["prefixes"], as_path=inj["as_path"]))
    if not faults:
        raise ConfigError(f"{where}: define at least one fault (link_down, node_isolated or inject_routes)")
    raw_checks = raw.get("checks") or []
    if not raw_checks:
        raise ConfigError(f"{where}: no checks defined")
    name = str(raw.get("name") or ", ".join(f.describe() for f in faults))
    checks = [_validate_check(j, c, default_timeout) for j, c in enumerate(raw_checks)]
    for c in checks:
        c.name = f"[{name}] {c.name}"
    return Scenario(name=name, faults=faults, checks=checks)


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
