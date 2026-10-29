"""The machine-readable capability statement (website/docs/capabilities.json, https://netdryrun.com/capabilities.json):
generated from the source, so it can't drift, and referenced wherever an agent looks first (server.json, AGENTS.md,
llms.txt, the MCP server's instructions)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import capabilities  # noqa: E402

from netdryrun import __version__  # noqa: E402
from netdryrun.config import CHECK_TYPES  # noqa: E402
from netdryrun.drivers import DRIVERS  # noqa: E402
from netdryrun.verify.report import VERDICTS as VERIFY_VERDICTS  # noqa: E402

DOC = json.loads(capabilities.PAGE.read_text(encoding="utf-8"))


def test_the_published_file_is_the_generated_one():
    assert capabilities.PAGE.read_text(encoding="utf-8") == capabilities.render(), "run python scripts/sync_facts.py"


def test_its_facts_are_the_codes():
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    assert DOC["schema"] == "netdryrun.capabilities/v1" and DOC["url"] == capabilities.URL
    assert DOC["version"] == __version__
    assert {p["driver"] for p in DOC["platforms"]} == set(DRIVERS)
    assert DOC["check_types"] == list(CHECK_TYPES)
    assert DOC["verdicts"]["run"] == list(mcp_server.VERDICT_ENUM)
    assert DOC["verdicts"]["verify"] == list(VERIFY_VERDICTS.values())
    tools = set(DOC["mcp"]["tools"])
    assert {"dry_run", "verify_change", "record_baseline", "validate"} <= tools
    for uc in DOC["use_cases"]:
        if "mcp" in uc:
            assert uc["mcp"]["tool"] in tools
            import inspect
            params = inspect.signature(getattr(mcp_server, uc["mcp"]["tool"])).parameters
            assert set(uc["mcp"]["arguments"]) <= set(params), uc["id"]
        if "github_action" in uc:
            assert uc["github_action"]["uses"] == f"netdryrun/netdryrun@v{__version__}"


def test_every_use_case_says_when_and_how():
    for uc in DOC["use_cases"]:
        assert uc["when"] and uc["cli"].startswith("netdryrun ") and ("mcp" in uc), uc["id"]
    assert DOC["prerequisites"] and DOC["limits"] and DOC["exit_codes"]["run"] and DOC["exit_codes"]["verify"]


def test_the_known_limits_are_stated():
    limits = " ".join(DOC["limits"])
    for phrase in ("only what the checks look at", "FRR only", "out-delay", "INCONCLUSIVE", "never from the diff"):
        assert phrase in limits, phrase


def test_it_is_referenced_where_agents_look_first():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]["capabilities"] == capabilities.URL
    for rel in ("AGENTS.md", "website/docs/llms.txt", "website/docs/ai-agents.md"):
        assert capabilities.URL in (ROOT / rel).read_text(encoding="utf-8"), rel
    mcp_server = pytest.importorskip("netdryrun.mcp_server")
    assert capabilities.URL in (mcp_server.mcp.instructions or "")
