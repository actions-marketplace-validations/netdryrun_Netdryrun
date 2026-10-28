---
title: "AI agents without Docker: the pull-request path"
description: How a coding agent with no local Docker gets a Netdryrun verdict: it opens a pull request, the GitHub Action runs the lab, and the agent reads a fixed-format comment or a machine-readable verdict artifact.
---

# AI agents without Docker: the pull-request path

The [MCP server](../ai-agents.md) needs Docker and containerlab on the machine the agent runs on. Many coding agents run in a sandbox without them. They can still get a verdict: they push their change to a branch and open a pull request, the [GitHub Action](../github-action.md) runs the lab on a GitHub runner, and the agent reads the result. This page is that flow, from 0.3.3.

## 1. The workflow in the network repository

```yaml
# .github/workflows/netdryrun.yml
name: Netdryrun
on: pull_request
permissions:
  contents: read
  pull-requests: write      # for the comment
jobs:
  verdict:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.3
        with:
          path: network/        # the folder with netdryrun.yml
          pr-comment: true
```

The job fails on anything but a pass, so branch protection can require it. A pull request from a fork can't be commented on (GitHub gives fork runs a read-only token); the verdict is still in the job result and the artifact.

## 2. What the agent reads

**The comment.** The Action posts one comment and updates it on every push. Its first lines have a fixed format:

```text
<!-- netdryrun-comment -->
<!-- netdryrun-verdict: {"schema": "netdryrun.mcp-result/v1", "status": "failed", "verdict": "DO NOT APPLY THIS CHANGE", "passed": 5, "failed": 1} -->
**Netdryrun: DO NOT APPLY THIS CHANGE** · status `failed` · 5 passed, 1 failed
```

Read the JSON on the second line and decide on `status`. The rest of the comment is the human summary: failed checks first, with their evidence.

**The artifact.** For the full detail, the job uploads `netdryrun-verdict.json` with the reports (artifact `netdryrun-report`). It is the same object the MCP tools return: `status`, the frozen `verdict`, `failures` with a reason, an evidence excerpt and a read-only `next_diagnostic` command for each failed check, and `tested`, a sha256 of `netdryrun.yml`, the topology and every config file the run used. Schema: [mcp-result-v1.json](https://netdryrun.com/schemas/mcp-result-v1.json).

## 3. What the agent does with it

- **`passed`**: propose the change, and say the pass covers only what the checks look at (`CHECKS PASSED (only what the checks cover)`).
- **`failed`**: read `failures`, fix the config, push again. The comment updates in place. Never edit `netdryrun.yml` to make a change pass.
- **`inconclusive`** or **`error`**: a setup problem that says nothing about the change. Push no fix for it; report it to the human.

The verdict applies to the commit the job ran on. After any push, wait for the new run.

## Paste this into the repository's AGENTS.md

```markdown
Network changes in this repository are dry-run by Netdryrun on every pull request. After you push, wait for
the "Netdryrun" check, then read the second line of the Netdryrun comment (a JSON object) and act on its
`status`: propose the change only on `passed`; on `failed`, fix the config and push again; on `inconclusive`
or `error`, stop and tell the human. Never edit `netdryrun.yml` to make a change pass.
```
