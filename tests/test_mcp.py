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


@pytest.mark.skipif(os.name != "posix", reason="the server runs on Linux")
def test_windows_paths_stay_inside_netdryrun_mcp_root(tmp_path, monkeypatch):
    # a Windows path is translated first, then held to NETDRYRUN_MCP_ROOT like any other: .. can't step outside
    from netdryrun import mcp_server
    monkeypatch.setattr(mcp_server, "WSL_MOUNTS", tmp_path)
    for name in ("lab", "other"):
        d = tmp_path / "c" / name
        d.mkdir(parents=True)
        (d / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
        (d / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "c" / "lab"))
    assert json.loads(mcp_server.validate(r"C:\lab"))["valid"] is True
    out = json.loads(mcp_server.validate(r"C:\lab\..\other"))
    assert out["valid"] is False and "outside NETDRYRUN_MCP_ROOT" in out["error"]


def _two_labs(tmp_path):
    for name in ("lab", "other"):
        d = tmp_path / name
        d.mkdir()
        (d / "topology.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: frr}\n")
        (d / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: route, node: r1, prefix: 10.0.0.0/24}\n")
        (d / "netdryrun-report.json").write_text(f'{{"lab": "{name}"}}')
    elsewhere = tmp_path / "server-cwd"
    elsewhere.mkdir()
    return elsewhere


class _Ran(Exception):
    pass


def test_relative_paths_resolve_against_a_single_mcp_root(tmp_path, monkeypatch):
    # an agent passes netdryrun.yml relative to its project; the server's own working directory is elsewhere
    from netdryrun import mcp_server
    monkeypatch.chdir(_two_labs(tmp_path))
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "lab"))
    for path in ("netdryrun.yml", ".", "./netdryrun.yml"):
        out = json.loads(mcp_server.validate(path))
        assert out["valid"] is True, out
        assert out["lab"] == str((tmp_path / "lab" / "topology.clab.yml").resolve())
    assert json.loads(mcp_server.last_report("."))["lab"] == "lab"
    # the topology is read from the root too (the server's cwd has none)
    err = json.loads(mcp_server.record_baseline("missing.clab.yml", deploy=False))["error"]
    assert str(tmp_path / "lab" / "missing.clab.yml") in err

    seen = []

    def fake_run(cfg, **_):
        seen.append(cfg.path)
        raise _Ran
    monkeypatch.setattr(mcp_server, "run", fake_run)
    for tool in (mcp_server.dry_run, mcp_server.run_checks):
        with pytest.raises(_Ran):
            tool("netdryrun.yml")
    assert seen == [(tmp_path / "lab" / "netdryrun.yml").resolve()] * 2


def test_relative_paths_cannot_escape_a_single_mcp_root(tmp_path, monkeypatch):
    from netdryrun import mcp_server
    monkeypatch.chdir(_two_labs(tmp_path))
    monkeypatch.setenv("NETDRYRUN_MCP_ROOT", str(tmp_path / "lab"))
    out = json.loads(mcp_server.validate("../other"))
    assert out["valid"] is False and "outside NETDRYRUN_MCP_ROOT" in out["error"]
    assert "outside NETDRYRUN_MCP_ROOT" in json.loads(mcp_server.record_baseline("../other/topology.clab.yml"))["error"]
    assert mcp_server.last_report("../other") == "{}"
    out = json.loads(mcp_server.dry_run("../other/netdryrun.yml"))
    assert out["status"] == "error" and "outside NETDRYRUN_MCP_ROOT" in out["error"]


@pytest.mark.parametrize("roots", ["", "lab+other"])
def test_relative_paths_without_a_single_root_ask_for_an_absolute_path(tmp_path, monkeypatch, roots):
    # no root, or several: there is no one folder to resolve against, so say what to pass instead of guessing
    from netdryrun import mcp_server
    _two_labs(tmp_path)
    monkeypatch.chdir(tmp_path / "lab")   # even a cwd that holds the file is not a guess we make
    monkeypatch.setattr(mcp_server, "run", lambda *a, **k: (_ for _ in ()).throw(_Ran()))   # never a real lab
    if roots:
        monkeypatch.setenv("NETDRYRUN_MCP_ROOT", os.pathsep.join(str(tmp_path / r) for r in roots.split("+")))
    else:
        monkeypatch.delenv("NETDRYRUN_MCP_ROOT", raising=False)
    for err in (json.loads(mcp_server.validate("netdryrun.yml"))["error"],
                json.loads(mcp_server.dry_run("netdryrun.yml"))["error"],
                json.loads(mcp_server.run_checks("netdryrun.yml"))["error"],
                json.loads(mcp_server.record_baseline("topology.clab.yml", deploy=False))["error"]):
        assert "relative path" in err and "absolute path" in err and "such as /" in err
        assert "outside NETDRYRUN_MCP_ROOT" not in err
    assert mcp_server.last_report(".") == "{}"
