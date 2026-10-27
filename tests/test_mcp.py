"""MCP server: tools are registered and the no-lab tools work."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXAMPLE = str(Path(__file__).parents[1] / "examples" / "frr-bgp")


async def _call(tool: str, args: dict) -> tuple[list[str], str]:
    # the same environment as the tests (the MCP client otherwise passes only a minimal one)
    params = StdioServerParameters(command=sys.executable, args=["-m", "netdryrun", "mcp"], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            res = await s.call_tool(tool, args)
            return tools, res.content[0].text


def test_tools_and_validate_over_stdio():
    tools, text = asyncio.run(_call("validate", {"path": EXAMPLE}))
    assert {"dry_run", "run_checks", "validate", "check_types", "record_baseline"} <= set(tools)
    data = json.loads(text)
    assert data["valid"] and len(data["checks"]) == 7


def test_validate_reports_errors():
    _, text = asyncio.run(_call("validate", {"path": "/nonexistent"}))
    assert json.loads(text)["valid"] is False


@pytest.mark.skipif(os.name != "posix", reason="the server runs on Linux")
def test_windows_paths_reach_the_server_in_wsl(tmp_path, monkeypatch):
    # Claude Code on Windows with the server in WSL: the agent's file tools know C:\lab, the server needs /mnt/c/lab
    from netdryrun import mcp_server
    (tmp_path / "c").mkdir()
    monkeypatch.setattr(mcp_server, "WSL_MOUNTS", tmp_path)
    assert mcp_server._host_path(r"C:\Users\me\lab") == f"{tmp_path}/c/Users/me/lab"
    assert mcp_server._host_path("c:/Users/me/lab/netdryrun.yml") == f"{tmp_path}/c/Users/me/lab/netdryrun.yml"
    assert mcp_server._host_path("/home/me/lab") == "/home/me/lab"
    assert mcp_server._host_path("lab") == "lab"
    assert mcp_server._host_path(r"Q:\lab") == r"Q:\lab"  # no such drive mounted: left as it is
    lab = tmp_path / "c" / "lab"
    lab.mkdir()
    (lab / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    assert json.loads(mcp_server.validate(r"C:\lab"))["valid"] is True
