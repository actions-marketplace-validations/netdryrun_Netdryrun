"""0.3.3 (a): the Action's PR comment starts with the fixed verdict header, built from the agent result and
held to the run's checked status. Runs the comment step's own script, taken from action.yml."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from netdryrun import agent_result

ROOT = Path(__file__).resolve().parents[1]
STEPS = {s.get("id") or s.get("name"): s for s in yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["runs"]["steps"]}


def comment_script() -> str:
    run = STEPS["Comment on the pull request"]["run"]
    m = re.search(r"<<'EOF'\n(.*?)\n\s*EOF\n", run, re.S)
    assert m, "the comment step no longer builds the body in an inline Python heredoc: update this test"
    lines = m.group(1).splitlines()
    indent = min(len(x) - len(x.lstrip()) for x in lines if x.strip())
    return "\n".join(x[indent:] for x in lines)


def body(tmp_path, verdict: dict | None, status: str) -> str:
    (tmp_path / "netdryrun-summary.md").write_text("## Netdryrun\n\nthe summary\n", encoding="utf-8")
    vpath = tmp_path / "netdryrun-verdict.json"
    if verdict is not None:
        vpath.write_text(json.dumps(verdict), encoding="utf-8")
    env = {"NDR_VERDICT": str(vpath), "NDR_STATUS": status, "PATH": "", "PYTHONPATH": str(ROOT / "src")}  # installed, in the Action
    subprocess.run([sys.executable, "-c", comment_script()], cwd=tmp_path, env=env, check=True)
    return json.loads((tmp_path / "netdryrun-comment.json").read_text(encoding="utf-8"))["body"]


def result(status, passed=3, failed=0):
    return {"schema": agent_result.RESULT_SCHEMA, "status": status, "passed": passed, "failed": failed,
            "verdict": agent_result.VERDICTS.get(status, agent_result.DO_NOT_APPLY)}


@pytest.mark.parametrize("status,failed", [("passed", 0), ("failed", 1), ("inconclusive", 2), ("error", 0)])
def test_the_comment_starts_with_the_update_marker_then_the_fixed_header(tmp_path, status, failed):
    b = body(tmp_path, result(status, failed=failed), status)
    lines = b.split("\n")
    assert lines[0] == "<!-- netdryrun-comment -->"
    assert lines[1] == agent_result.pr_comment_header(result(status, failed=failed)).split("\n")[0]
    assert lines[2].startswith(f"**Netdryrun: {result(status)['verdict']}**")
    assert b.endswith("the summary\n")


def test_a_verdict_file_that_disagrees_with_the_run_reads_as_error(tmp_path):
    # the run exited 1 (status failed), but the file says passed: never a passing header
    b = body(tmp_path, result("passed"), "failed")
    assert '"status": "error"' in b.split("\n")[1] and agent_result.DO_NOT_APPLY in b.split("\n")[2]


def test_no_verdict_file_reads_as_error(tmp_path):
    b = body(tmp_path, None, "passed")
    assert '"status": "error"' in b.split("\n")[1]
