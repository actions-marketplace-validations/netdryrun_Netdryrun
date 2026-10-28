"""0.3.3 (b): the asynchronous MCP shape. start_run answers at once with a run ID; get_result polls.

A dry run takes 60-120 s and some MCP clients give up on a tool call long before that, so the agent must never
have to wait inside one call. A pending answer carries no verdict, so it can't be read as one."""
import json
import threading
import time

import pytest

pytest.importorskip("mcp")
jsonschema = pytest.importorskip("jsonschema")

from netdryrun import mcp_server  # noqa: E402
from netdryrun.checks import Result  # noqa: E402
from netdryrun.config import Check  # noqa: E402
from netdryrun.runner import RunReport  # noqa: E402

from test_mcp import _two_labs  # noqa: E402

SCHEMA = mcp_server.Path(__file__).resolve().parents[1] / "website" / "docs" / "schemas" / "mcp-result-v1.json"


def _validate(data):
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(data)


class Gate:
    """A fake run() that blocks until the test releases it, then returns the report it was given."""

    def __init__(self, passed=True, error=None):
        self.release, self.started = threading.Event(), threading.Event()
        self.passed, self.error, self.calls = passed, error, []

    def __call__(self, cfg, deploy, keep, **_):
        self.calls.append((deploy, keep))
        self.started.set()
        assert self.release.wait(10), "the test never released the run"
        if self.error:
            raise self.error
        c = Check("route", {"node": "r1", "prefix": "10.0.0.0/24"}, "r1 route", 30)
        return RunReport(config=cfg, results=[Result(c, self.passed, "ok" if self.passed else "seen: nothing", 2, 1.0, "t")])


def _wait_finished(run_id, limit=10):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        out = json.loads(mcp_server.get_result(run_id))
        if out["status"] != "running":
            return out
        time.sleep(0.05)
    raise AssertionError("never finished")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    _two_labs(tmp_path)
    monkeypatch.setattr(mcp_server, "_RUNS", {})
    return tmp_path / "lab"


def test_start_run_answers_at_once_and_get_result_polls_to_the_verdict(lab, monkeypatch):
    g = Gate(passed=True)
    monkeypatch.setattr(mcp_server, "run", g)
    t0 = time.monotonic()
    started = json.loads(mcp_server.start_run(str(lab)))
    assert time.monotonic() - t0 < 2 and g.started.wait(5)
    assert started["status"] == "running" and started["run_id"] and "verdict" not in started
    assert started["poll_after_s"] > 0
    _validate(started)
    pending = json.loads(mcp_server.get_result(started["run_id"]))
    assert pending["status"] == "running" and "verdict" not in pending and pending["elapsed_s"] >= 0
    _validate(pending)
    g.release.set()
    done = _wait_finished(started["run_id"])
    assert done["status"] == "passed" and done["verdict"] == mcp_server.CHECKS_PASSED
    assert done["run_id"] == started["run_id"] and done["tested"]["lab_deployed_by_this_run"] is True
    _validate(done)
    assert g.calls == [(True, False)]   # deploys and destroys, like dry_run
    # the finished result stays readable
    assert json.loads(mcp_server.get_result(started["run_id"]))["status"] == "passed"


def test_a_failed_run_is_do_not_apply(lab, monkeypatch):
    g = Gate(passed=False)
    monkeypatch.setattr(mcp_server, "run", g)
    rid = json.loads(mcp_server.start_run(str(lab)))["run_id"]
    g.release.set()
    done = _wait_finished(rid)
    assert done["status"] == "failed" and done["verdict"] == mcp_server.DO_NOT_APPLY and done["failures"]


def test_keep_lab_is_passed_through(lab, monkeypatch):
    g = Gate()
    monkeypatch.setattr(mcp_server, "run", g)
    rid = json.loads(mcp_server.start_run(str(lab), keep_lab=True))["run_id"]
    g.release.set()
    _wait_finished(rid)
    assert g.calls == [(True, True)]


def test_a_config_error_is_answered_at_once_with_no_run(lab, monkeypatch):
    monkeypatch.setattr(mcp_server, "run", lambda *a, **k: pytest.fail("no run for a bad config"))
    out = json.loads(mcp_server.start_run(str(lab.parent / "nope")))
    assert out["status"] == "error" and out["verdict"] == mcp_server.DO_NOT_APPLY and "run_id" not in out
    _validate(out)


def test_a_crash_in_the_run_is_an_error_result_not_a_run_stuck_running(lab, monkeypatch):
    g = Gate(error=RuntimeError("boom"))
    monkeypatch.setattr(mcp_server, "run", g)
    rid = json.loads(mcp_server.start_run(str(lab)))["run_id"]
    g.release.set()
    done = _wait_finished(rid)
    assert done["status"] == "error" and done["verdict"] == mcp_server.DO_NOT_APPLY and "boom" in done["error"]
    _validate(done)


def test_an_unknown_run_id_is_an_error_with_no_verdict_to_act_on(lab):
    out = json.loads(mcp_server.get_result("no-such-run"))
    assert out["status"] == "error" and out["verdict"] == mcp_server.DO_NOT_APPLY and "no-such-run" in out["error"]
    _validate(out)


def test_start_run_is_held_to_netdryrun_mcp_root(lab, monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_server, "run", lambda *a, **k: pytest.fail("no run outside the root"))
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(lab))
    out = json.loads(mcp_server.start_run(str(tmp_path / "other")))
    assert out["status"] == "error" and "outside NETDRYRUN_MCP_ROOT" in out["error"]


def test_old_finished_runs_are_forgotten_but_running_ones_never(lab, monkeypatch):
    g = Gate()
    monkeypatch.setattr(mcp_server, "run", g)
    monkeypatch.setattr(mcp_server, "RUNS_KEPT", 2)
    first = json.loads(mcp_server.start_run(str(lab)))["run_id"]   # still running while the others finish
    g2 = Gate()
    monkeypatch.setattr(mcp_server, "run", g2)
    g2.release.set()
    done = [json.loads(mcp_server.start_run(str(lab)))["run_id"] for _ in range(3)]
    for rid in done:
        _wait_finished(rid)
    json.loads(mcp_server.start_run(str(lab)))   # pruning happens on start
    assert json.loads(mcp_server.get_result(first))["status"] == "running"
    assert json.loads(mcp_server.get_result(done[0]))["status"] == "error"   # forgotten
    g.release.set()
    assert _wait_finished(first)["status"] == "passed"


def test_the_tools_are_listed_with_the_contract():
    import asyncio
    tools = {t.name: " ".join(t.description.split()) for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"start_run", "get_result", "dry_run"} <= set(tools)
    assert "returns at once" in tools["start_run"].lower() and "get_result" in tools["start_run"]
    assert "running" in tools["get_result"] and "no verdict" in tools["get_result"].lower()
    for name in ("start_run", "get_result"):
        assert mcp_server.CONTRACT in tools[name]
