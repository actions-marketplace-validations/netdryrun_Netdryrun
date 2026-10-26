"""Render a run as console text, JSON evidence, Markdown and JUnit XML."""
from __future__ import annotations

import json
from xml.sax.saxutils import escape, quoteattr

from .checks import Result
from .runner import RunReport

ICON = {True: "PASS", False: "FAIL"}


def console_line(r: Result) -> str:
    return f"  [{ICON[r.passed]}] {r.check.name} -- {r.detail} ({r.duration}s)"


def summary_line(rep: RunReport) -> str:
    if rep.error:
        return f"ERROR: {rep.error}"
    return f"{rep.status.upper()}: {rep.passed} passed, {rep.failed} failed ({len(rep.results)} checks)"


def to_json(rep: RunReport) -> str:
    data = {
        "schema": "netdryrun.report/v1",
        "status": rep.status,
        "lab": rep.lab_name,
        "config": str(rep.config.path),
        "started": rep.started,
        "finished": rep.finished,
        "error": rep.error or None,
        "environment": rep.environment,
        "summary": {"passed": rep.passed, "failed": rep.failed, "total": len(rep.results)},
        "checks": [
            {
                "name": r.check.name,
                "type": r.check.type,
                "params": r.check.params,
                "passed": r.passed,
                "detail": r.detail,
                "attempts": r.attempts,
                "duration_s": r.duration,
                "started": r.started,
                "history": r.history,
                "evidence": r.evidence,
            }
            for r in rep.results
        ],
    }
    return json.dumps(data, indent=2)


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _evidence_excerpt(output: str, params: dict, max_lines: int = 15) -> str:
    """The part of a raw command output a reviewer needs: lines mentioning the prefix or neighbor
    under test (with a little context), else the first lines. Kept short enough to paste in a PR."""
    rows = output.splitlines()
    keys = [str(params[k]) for k in ("prefix", "neighbor", "target") if params.get(k)]
    if keys and len(rows) > max_lines:
        hits = [i for i, row in enumerate(rows) if any(k in row for k in keys)]
        if hits:
            start = max(0, hits[0] - 2)
            rows = rows[start:start + max_lines]
            return "\n".join(rows + ["..."])
    return "\n".join(rows[:max_lines] + (["..."] if len(rows) > max_lines else []))


def to_markdown(rep: RunReport) -> str:
    head = {"passed": "✅ Netdryrun passed", "failed": "❌ Netdryrun failed", "error": "⚠️ Netdryrun could not run"}[rep.status]
    lines = [f"### {head}", ""]
    if rep.error:
        lines += ["```", rep.error, "```"]
        return "\n".join(lines) + "\n"
    lines += [f"**{rep.passed} passed, {rep.failed} failed** on lab `{rep.lab_name}`", "",
              "| | Check | Result | Time |", "|---|---|---|---|"]
    for r in sorted(rep.results, key=lambda r: r.passed):  # failures first
        lines.append(f"| {'✅' if r.passed else '❌'} | {_md_cell(r.check.name)} | {_md_cell(r.detail)} | {r.duration}s |")
    failures = [r for r in rep.results if not r.passed]
    for r in failures[:5]:
        ev = r.evidence[-1] if r.evidence else None
        if not ev:
            continue
        out = _evidence_excerpt(ev.get("output") or ev.get("stderr") or "", r.check.params)
        lines += ["", f"<details><summary>Evidence: {_md_cell(r.check.name)}</summary>", "",
                  f"`{ev['node']}$ {ev['cmd']}`", "", "```", out, "```", "", "</details>"]
    env = rep.environment
    lines += ["", f"<sub>netdryrun {env.get('netdryrun', '?')} · containerlab {env.get('containerlab', '?')} · "
              f"{rep.started} · full evidence in the JSON report</sub>"]
    return "\n".join(lines) + "\n"


def to_junit(rep: RunReport) -> str:
    cases = []
    for r in rep.results:
        body = "" if r.passed else f"<failure message={quoteattr(r.detail)}>{escape(json.dumps(r.evidence, indent=1)[:20000])}</failure>"
        cases.append(f'  <testcase classname="netdryrun.{r.check.type}" name={quoteattr(r.check.name)} time="{r.duration}">{body}</testcase>')
    errors = 1 if rep.error else 0
    if rep.error:
        cases.append(f'  <testcase classname="netdryrun" name="lab"><error message={quoteattr(rep.error)}/></testcase>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="netdryrun" tests="{len(rep.results) + errors}" failures="{rep.failed}" errors="{errors}">\n'
        + "\n".join(cases) + "\n</testsuite>\n"
    )
