"""MCP server: tools are registered and the no-lab tools work."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXAMPLE = str(Path(__file__).parents[1] / "examples" / "frr-bgp")


async def _call(tool: str, args: dict) -> tuple[list[str], str]:
    params = StdioServerParameters(command=sys.executable, args=["-m", "netdryrun.mcp_server"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            res = await s.call_tool(tool, args)
            return tools, res.content[0].text


def test_tools_and_validate_over_stdio():
    tools, text = asyncio.run(_call("validate", {"path": EXAMPLE}))
    assert {"dry_run", "run_checks", "validate", "check_types"} <= set(tools)
    data = json.loads(text)
    assert data["valid"] and len(data["checks"]) == 6


def test_validate_reports_errors():
    _, text = asyncio.run(_call("validate", {"path": "/nonexistent"}))
    assert json.loads(text)["valid"] is False
