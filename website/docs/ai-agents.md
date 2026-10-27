---
title: AI agents (MCP server)
description: The Netdryrun MCP server lets an AI agent dry-run a network change in a real containerlab lab and proceed only if every check passes. Install, tools, verdict field and safety model.
---

# AI agents (MCP server)

AI agents are starting to change networks. Netdryrun™ includes an [MCP](https://modelcontextprotocol.io) server that gives an agent a safety gate: it dry-runs the proposed change in a real lab and proceeds only if every check passes.

## Install

```bash
pip install netdryrun
```

The MCP server is built in: `netdryrun mcp` starts it over stdio. The same requirements apply as for the CLI: Linux or WSL2, Docker, containerlab.

Add it to your MCP client. For example, Claude Code:

```bash
claude mcp add netdryrun -- netdryrun mcp
```

Other clients: configure a stdio server with command `netdryrun` and argument `mcp` (or `uvx netdryrun mcp` with no install).

## Workflow

1. The agent writes its proposed change into the lab's configs (in a lab folder with a containerlab topology and a `netdryrun.yml`).
2. It calls `dry_run` on that folder.
3. It applies the change elsewhere only if `status` is `passed`.

## Demo: a ticket, a tempting change, a verdict

![An attempt that passes the ticket checks but leaks routes is rejected; the proper fix passes the same checks](assets/netdryrun-agent-demo.gif)

[`examples/agent-demo`](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo): the customer's new block must reach the upstream and the peer. The tempting change, removing the prefix-list filters, passes every ticket check, session check and ping, but leaks upstream routes and the upstream's default route to the peer, and accepts a prefix the customer doesn't own. The network team's leak guards fail, so the verdict is `DO NOT APPLY THIS CHANGE`. The proper fix, two prefix-list lines, passes the same checks. The checks never change; only the config does. Both attempts are a scripted replay (hand-written diffs, not output from a real agent); `demo.sh` runs them, and CI runs it on pushes to `main` and on pull requests. In a [real run](https://github.com/netdryrun/netdryrun/blob/main/examples/agent-demo/AGENT-RUN.md), a fresh Claude Code agent with only the ticket, the lab and these MCP tools made the correct two-line change on the first try and proposed it with a `passed` verdict.

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

`verdict` is a separate field with one of three values:

- `SAFE TO PROCEED` when `status` is `passed`
- `DO NOT APPLY THIS CHANGE` for `failed` or `error`, including config errors
- `INCONCLUSIVE: the lab did not reach a testable state; this says nothing about your change. Do not apply it until a run passes.` when `status` is `inconclusive`: the lab never came up far enough for the checks to mean anything ([rules](reference/cli.md#when-a-run-is-inconclusive)). `inconclusive_reason` says what was seen. Rerun it, perhaps with a longer `timeout`; don't rewrite the change because of it.

The full evidence is written to `netdryrun-report.json` next to `netdryrun.yml`.

## Safety model

- **It never touches production.** The server has no tool that pushes config anywhere. It only builds and tests labs.
- **No raw device output in tool results.** Tool results contain normalized check results (name, pass/fail, a short detail), not raw device output. Text inside a lab, such as a banner or a route description, cannot inject instructions into the agent through the tool result. Raw evidence goes to the JSON report file.
- **Labs are code.** containerlab runs privileged containers. Only point the server at topologies you trust, on a machine you would let run Docker.

A pass is evidence from a lab, not a guarantee about production. See [what a lab cannot prove](trust.md#what-a-lab-cannot-prove).
