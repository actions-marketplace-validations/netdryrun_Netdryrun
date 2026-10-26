---
title: AI agents (MCP server)
description: The netdryrun MCP server lets an AI agent dry-run a network change in a real containerlab lab and proceed only if every check passes. Install, tools, verdict field and safety model.
---

# AI agents (MCP server)

AI agents are starting to change networks. netdryrun includes an [MCP](https://modelcontextprotocol.io) server that gives an agent a safety gate: it dry-runs the proposed change in a real lab and proceeds only if every check passes.

## Install

```bash
pip install "netdryrun[mcp]"
```

This adds the `netdryrun-mcp` command, a stdio MCP server. The same requirements apply as for the CLI: Linux or WSL2, Docker, containerlab.

Add it to your MCP client. For example, Claude Code:

```bash
claude mcp add netdryrun -- netdryrun-mcp
```

Other clients: configure a stdio server whose command is `netdryrun-mcp`.

## Workflow

1. The agent writes its proposed change into the lab's configs (in a lab folder with a containerlab topology and a `netdryrun.yml`).
2. It calls `dry_run` on that folder.
3. It applies the change elsewhere only if `status` is `passed`.

## Tools

| Tool | Arguments | What it does |
|---|---|---|
| `dry_run` | `path`, `keep_lab` (default `false`) | Deploy the lab, run every check, destroy the lab, return the verdict. Takes 1 to 5 minutes. |
| `run_checks` | `path` | Run the checks against a lab that is already running (no deploy or destroy) |
| `validate` | `path` | Validate `netdryrun.yml` without starting a lab |
| `check_types` | | List supported check types and their keys, to help write `netdryrun.yml` |

The server also exposes the last full JSON report as a resource, `netdryrun://report/{path}`.

## Result and verdict

`dry_run` and `run_checks` return JSON like this:

```json
{
  "status": "failed",
  "passed": 5,
  "failed": 1,
  "error": null,
  "lab": "ndr-frr-broken",
  "checks": [
    {"name": "r1: route 0.0.0.0/0 via bgp is absent", "passed": false,
     "detail": "unexpectedly present via bgp (not selected)"}
  ],
  "evidence_file": "/path/to/lab/netdryrun-report.json",
  "verdict": "DO NOT APPLY THIS CHANGE"
}
```

(`checks` is shortened here; the real result lists every check.)

`verdict` is a separate field with one of two values:

- `SAFE TO PROCEED` when `status` is `passed`
- `DO NOT APPLY THIS CHANGE` for `failed` or `error`, including config errors

The full evidence is written to `netdryrun-report.json` next to `netdryrun.yml`.

## Safety model

- **It never touches production.** The server has no tool that pushes config anywhere. It only builds and tests labs.
- **No raw device output in tool results.** Tool results contain normalized check results (name, pass/fail, a short detail), not raw device output. Text inside a lab, such as a banner or a route description, cannot inject instructions into the agent through the tool result. Raw evidence goes to the JSON report file.
- **Labs are code.** containerlab runs privileged containers. Only point the server at topologies you trust, on a machine you would let run Docker.

A pass is evidence from a lab, not a guarantee about production. See [what a lab cannot prove](trust.md#what-a-lab-cannot-prove).
