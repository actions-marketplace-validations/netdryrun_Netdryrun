"""MCP server: lets AI agents dry-run a network change before applying it.

Run with `netdryrun-mcp` (stdio). Install with `pip install "netdryrun[mcp]"`.
An agent that proposes a config change calls `dry_run` on the lab that contains the change,
and only proceeds if the status is "passed".
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server import MCPServer

from . import __version__, report
from .config import CHECK_TYPES, ConfigError, load
from .runner import run

mcp = MCPServer("netdryrun", version=__version__, website_url="https://netdryrun.com")


def _summary(rep, evidence_path: str | None) -> dict:
    return {
        "status": rep.status,
        "passed": rep.passed,
        "failed": rep.failed,
        "error": rep.error or None,
        "lab": rep.lab_name,
        "checks": [{"name": r.check.name, "passed": r.passed, "detail": r.detail} for r in rep.results],
        "evidence_file": evidence_path,
        "verdict": "SAFE TO PROCEED" if rep.status == "passed" else "DO NOT APPLY THIS CHANGE",
    }


def _execute(path: str, deploy: bool, keep: bool) -> str:
    try:
        cfg = load(path)
    except ConfigError as e:
        return json.dumps({"status": "error", "error": str(e), "verdict": "DO NOT APPLY THIS CHANGE"})
    rep = run(cfg, deploy=deploy, keep=keep)
    evidence = cfg.path.parent / "netdryrun-report.json"
    evidence.write_text(report.to_json(rep), encoding="utf-8")
    return json.dumps(_summary(rep, str(evidence)), indent=2)


@mcp.tool()
def dry_run(path: str, keep_lab: bool = False) -> str:
    """Deploy the containerlab lab described by netdryrun.yml at `path`, run every behavioral check
    (BGP sessions, prefix counts, routes, reachability), then destroy the lab.
    Returns status, per-check results and a verdict. Only apply a network change if status is "passed".
    Takes 1-5 minutes."""
    return _execute(path, deploy=True, keep=keep_lab)


@mcp.tool()
def run_checks(path: str) -> str:
    """Run the checks in netdryrun.yml at `path` against a lab that is already running (no deploy/destroy)."""
    return _execute(path, deploy=False, keep=True)


@mcp.tool()
def record_baseline(topology: str, deploy: bool = True, wait_seconds: float = 45) -> str:
    """Snapshot a known-good lab (containerlab topology file) into netdryrun.yml check text: every
    established BGP session, prefix count and BGP route. Use it BEFORE proposing a change, then dry-run
    the change against this baseline. Returns the YAML; it is not written to disk."""
    import time

    from .lab import Lab, LabError
    from .record import record, render

    topo = Path(topology).resolve()
    lab = Lab(topo)
    try:
        if deploy:
            lab.deploy()
            time.sleep(wait_seconds)
        data, warnings = record(topo)
    except LabError as e:
        return json.dumps({"error": str(e)})
    finally:
        if deploy:
            lab.destroy()
    return render(data, warnings)


@mcp.tool()
def validate(path: str) -> str:
    """Validate netdryrun.yml at `path` without starting a lab. Returns the parsed checks or the error."""
    try:
        cfg = load(path)
    except ConfigError as e:
        return json.dumps({"valid": False, "error": str(e)})
    return json.dumps({"valid": True, "lab": str(cfg.lab), "checks": [c.name for c in cfg.checks]}, indent=2)


@mcp.tool()
def check_types() -> str:
    """List supported check types and their keys, to help write netdryrun.yml."""
    return json.dumps({"netdryrun": __version__, "check_types": {
        k: {"required": list(v["required"]), "optional": list(v["optional"]) + ["name", "timeout"]}
        for k, v in CHECK_TYPES.items()}}, indent=2)


@mcp.resource("netdryrun://report/{path}")
def last_report(path: str) -> str:
    """The last full JSON evidence report written next to netdryrun.yml at `path`."""
    p = Path(path)
    p = (p if p.is_dir() else p.parent) / "netdryrun-report.json"
    return p.read_text(encoding="utf-8") if p.exists() else "{}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
