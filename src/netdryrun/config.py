"""Load and validate netdryrun.yml."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CHECK_TYPES = {
    "bgp_session": {"required": ("node", "neighbor"), "optional": ("state", "vrf")},
    "bgp_prefixes": {"required": ("node", "neighbor"), "optional": ("min", "max", "exact", "afi", "vrf")},
    "route": {"required": ("node", "prefix"), "optional": ("present", "protocol", "vrf", "active")},
    "ping": {"required": ("node", "target"), "optional": ("source", "expect", "vrf", "count", "min_replies")},
}
COMMON_KEYS = ("type", "name", "timeout", "hold")
BGP_STATES = ("idle", "connect", "active", "opensent", "openconfirm", "established", "down")  # down = any state except established


class ConfigError(ValueError):
    pass


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
    kind: str          # "link_down" or "node_isolated"
    node: str
    interface: str | None = None

    def describe(self) -> str:
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
        if ctype == "route":
            params["prefix"] = str(ipaddress.ip_network(str(params["prefix"]), strict=False))
        for key in ("neighbor", "target", "source"):
            if key in params:
                params[key] = str(ipaddress.ip_address(str(params[key])))
    except ValueError as e:
        raise ConfigError(f"{where}: {e}") from None
    for key in ("min", "max", "exact", "count", "min_replies"):
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
    timeout = float(raw.get("timeout", default_timeout))
    hold = float(raw["hold"]) if "hold" in raw else None
    return Check(type=ctype, params=params, name=raw.get("name") or _describe(ctype, params), timeout=timeout, hold=hold)


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
    unknown = set(raw) - {"name", "link_down", "node_isolated", "checks"}
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
    if not faults:
        raise ConfigError(f"{where}: define at least one fault (link_down or node_isolated)")
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
