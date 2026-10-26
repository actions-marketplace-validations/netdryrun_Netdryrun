"""Render corpus/results/results.json into corpus/RESULTS.md and the website's corpus page.

Usage: python corpus/render.py
Also prints the launch numbers ({{x}}, {{fp_ping}}, ...) used in the announcement drafts.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE_PAGE = HERE.parent / "website" / "docs" / "corpus.md"
LABELS = {"ping": "Ping only", "sessions": "All BGP sessions up", "netdryrun": "Netdryrun intent checks"}
MARK = {"correct": "✅", "false pass": "❌ approved a bad change", "false block": "⚠️ blocked a good change", "error": "💥 error"}

# Post-run findings, appended without touching the pre-registered expected verdicts.
AMENDMENTS = HERE / "AMENDMENTS.md"


def outcome(expected: str, verdict: str) -> str:
    if verdict == "error":
        return "error"
    if verdict == expected:
        return "correct"
    return "false pass" if expected == "unsafe" else "false block"


def stats(rows: list[dict]) -> dict:
    out = {}
    unsafe = [r for r in rows if r["expected"] == "unsafe"]
    for s in LABELS:
        oc = [outcome(r["expected"], r["strategies"][s]["verdict"]) for r in rows]
        out[s] = {
            "correct": oc.count("correct"), "false_pass": oc.count("false pass"),
            "false_block": oc.count("false block"), "error": oc.count("error"),
            "caught": sum(1 for r in unsafe if r["strategies"][s]["verdict"] == "unsafe"),
        }
    out["total"], out["unsafe"], out["safe"] = len(rows), len(unsafe), len(rows) - len(unsafe)
    return out


def results_markdown(data: dict) -> str:
    rows, env = data["cases"], data["environment"]
    st = stats(rows)
    lines = [
        f"Generated {env['generated']} with netdryrun {env['netdryrun']}, containerlab {env['containerlab']}, "
        f"FRR {env['frr_image']}, commit `{env.get('commit', '?')}`. Rerun everything with `python corpus/run.py`.", "",
        "**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. Expected verdicts were "
        "committed before any run (see the git history of `corpus/cases/`). Losses are kept and shown at the same size as the catches.", "",
        f"## Summary ({st['total']} cases: {st['unsafe']} harmful, {st['safe']} safe)", "",
        "| Strategy | Correct | Harmful changes caught | Approved a bad change | Blocked a good change | Errors |",
        "|---|---|---|---|---|---|",
    ]
    for s, label in LABELS.items():
        x = st[s]
        lines.append(f"| {label} | **{x['correct']}/{st['total']}** | {x['caught']}/{st['unsafe']} | {x['false_pass']} | {x['false_block']} | {x['error']} |")
    lines += ["", "## Every case", "", "| Case | Category | Expected | Ping only | Sessions up | Netdryrun | What Netdryrun flagged |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        cells = [MARK[outcome(r["expected"], r["strategies"][s]["verdict"])] for s in LABELS]
        flagged = "; ".join(r["strategies"]["netdryrun"]["failed_checks"]) or "nothing"
        lines.append(f"| `{r['id']}` {r['title']} | {r['category']} | {r['expected']} | {' | '.join(cells)} | {flagged} |")
    losses = [r for r in rows if outcome(r["expected"], r["strategies"]["netdryrun"]["verdict"]) != "correct"]
    lines += ["", "## Netdryrun's losses", ""]
    if not losses:
        lines.append("None in this run.")
    for r in losses:
        oc = outcome(r["expected"], r["strategies"]["netdryrun"]["verdict"])
        lines.append(f"- **`{r['id']}` {r['title']}** ({oc}). {r.get('note') or r['rationale']}")
    if AMENDMENTS.exists():
        lines += ["", "## Findings after the run", "", AMENDMENTS.read_text(encoding="utf-8").strip()]
    return "\n".join(lines) + "\n"


def main() -> None:
    data = json.loads((HERE / "results" / "results.json").read_text(encoding="utf-8"))
    body = results_markdown(data)
    (HERE / "RESULTS.md").write_text("# Verdict Corpus results\n\n" + body, encoding="utf-8")
    page = SITE_PAGE.read_text(encoding="utf-8")
    marker = "<!-- RESULTS -->"
    head = page.split(marker)[0]
    SITE_PAGE.write_text(head + marker + "\n\n" + body.replace("`corpus/cases/`", "[`corpus/cases/`](https://github.com/netdryrun/netdryrun/tree/main/corpus/cases)"), encoding="utf-8")
    st = stats(data["cases"])
    print(json.dumps({
        "30": st["total"], "unsafe": st["unsafe"],
        "x": st["ping"]["correct"], "y": st["sessions"]["correct"], "z": st["netdryrun"]["correct"],
        "fp_ping": st["ping"]["false_pass"], "fp_sessions": st["sessions"]["false_pass"],
        "caught": st["netdryrun"]["caught"],
    }, indent=1))


if __name__ == "__main__":
    main()
