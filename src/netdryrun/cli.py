"""Command-line interface: netdryrun run | check | validate."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, report
from .config import ConfigError, load
from .runner import run


def _write_outputs(rep, args) -> None:
    outputs = {"json": report.to_json, "markdown": report.to_markdown, "junit": report.to_junit}
    for key, render in outputs.items():
        path = getattr(args, key, None)
        if path:
            Path(path).write_text(render(rep), encoding="utf-8")
            print(f"  wrote {key} report: {path}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not args.no_step_summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report.to_markdown(rep))


def _cmd_run(args, deploy: bool) -> int:
    try:
        cfg = load(args.path)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    print(f"Netdryrun {__version__}: {len(cfg.checks)} checks from {cfg.path}")
    rep = run(cfg, deploy=deploy, keep=args.keep, keep_on_failure=getattr(args, 'keep_on_failure', False),
              settle=args.settle, hold=args.hold,
              on_result=lambda r: print(report.console_line(r), flush=True),
              log=lambda m: print(m, flush=True))
    print(report.summary_line(rep))
    _write_outputs(rep, args)
    return rep.exit_code


def _cmd_validate(args) -> int:
    try:
        cfg = load(args.path)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    print(f"OK: {cfg.path} ({len(cfg.checks)} checks, lab {cfg.lab})")
    for c in cfg.checks:
        print(f"  - [{c.type}] {c.name}")
    return 0


def _cmd_record(args) -> int:
    import os
    import time

    from .lab import Lab, LabError
    from .record import record, render

    topo = Path(args.topology).resolve()
    if not topo.exists():
        print(f"error: {topo} not found", file=sys.stderr)
        return 2
    out = Path(args.out).resolve() if args.out else topo.parent / "netdryrun.yml"
    if out.exists() and not args.force:
        print(f"error: {out} exists; use --force to overwrite or --out to pick another file", file=sys.stderr)
        return 2
    lab = Lab(topo)
    try:
        if args.deploy:
            print(f"Deploying lab {lab.name}, then waiting {args.wait:g}s for the network to converge...", flush=True)
            lab.deploy()
            time.sleep(args.wait)
        data, warnings = record(topo, include_routes=not args.no_routes, exact_prefixes=not args.min_prefixes,
                                log=lambda m: print(m, flush=True))
    except LabError as e:
        print(f"lab error: {e}", file=sys.stderr)
        return 2
    finally:
        if args.deploy:
            lab.destroy()
    if not data["checks"]:
        for w in warnings:
            print(f"warning: {w}")
        print("error: nothing to record (no established BGP sessions or BGP routes found); is the lab converged? "
              "Try --deploy with a longer --wait.", file=sys.stderr)
        return 2
    data["lab"] = os.path.relpath(topo, out.parent).replace(os.sep, "/")
    out.write_text(render(data, warnings), encoding="utf-8")
    for w in warnings:
        print(f"warning: {w}")
    print(f"Recorded {len(data['checks'])} checks to {out}. Review it, then: netdryrun run {out.parent}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="netdryrun", description="Test network changes in a real virtual lab before production.")
    ap.add_argument("--version", action="version", version=f"netdryrun {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_run_opts(p):
        p.add_argument("path", nargs="?", default=".", help="netdryrun.yml or the folder containing it")
        p.add_argument("--json", metavar="FILE", help="write the full evidence report as JSON")
        p.add_argument("--markdown", metavar="FILE", help="write a Markdown summary (for PR comments)")
        p.add_argument("--junit", metavar="FILE", help="write JUnit XML (for CI test reporting)")
        p.add_argument("--settle", type=float, default=10.0, help="seconds to wait before negative checks (default 10)")
        p.add_argument("--hold", type=float, default=10.0, help="seconds a negative check must hold (default 10)")
        p.add_argument("--no-step-summary", action="store_true", help="don't append to $GITHUB_STEP_SUMMARY")

    p_run = sub.add_parser("run", help="deploy the lab, run checks, destroy the lab")
    add_run_opts(p_run)
    p_run.add_argument("--keep", action="store_true", help="leave the lab running afterwards (for debugging)")
    p_run.add_argument("--keep-on-failure", action="store_true", help="leave the lab running only if a check fails")

    p_check = sub.add_parser("check", help="run checks against an already running lab")
    add_run_opts(p_check)
    p_check.set_defaults(keep=True)

    p_val = sub.add_parser("validate", help="validate netdryrun.yml without running anything")
    p_val.add_argument("path", nargs="?", default=".")

    p_rec = sub.add_parser("record", help="snapshot a known-good lab into a netdryrun.yml baseline")
    p_rec.add_argument("topology", help="containerlab topology file of the lab to record")
    p_rec.add_argument("--out", metavar="FILE", help="where to write (default: netdryrun.yml next to the topology)")
    p_rec.add_argument("--deploy", action="store_true", help="deploy the lab first and destroy it afterwards")
    p_rec.add_argument("--wait", type=float, default=45.0, help="with --deploy: seconds to let BGP converge (default 45)")
    p_rec.add_argument("--min-prefixes", action="store_true", help="record prefix counts as minimums instead of exact")
    p_rec.add_argument("--no-routes", action="store_true", help="don't record individual BGP routes")
    p_rec.add_argument("--force", action="store_true", help="overwrite an existing output file")

    sub.add_parser("mcp", help="run the MCP server (stdio) so AI agents can dry-run changes")

    args = ap.parse_args(argv)
    if args.cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
        return 0
    if args.cmd == "validate":
        return _cmd_validate(args)
    if args.cmd == "record":
        return _cmd_record(args)
    return _cmd_run(args, deploy=args.cmd == "run")


if __name__ == "__main__":
    sys.exit(main())
