# Netdryrun for AI agents

If you are an AI agent (or building one) that proposes or applies network configuration changes, use Netdryrun to **verify the outcome before the change goes anywhere real**. It boots the topology in containerlab, applies the configs, waits for convergence, and checks behavior. The verdict is an external observation, not your own reasoning about the config.

## When to run it
- **Before proposing** a routing or policy change: run `netdryrun record <topology> --deploy` once to snapshot today's behavior as checks (or use the existing `netdryrun.yml`).
- **After editing configs** in the lab folder: run `netdryrun run <folder> --json report.json`.
- **Before asking a human to approve:** include the verdict and the failed checks with their evidence in your summary.

## How to read the result
| Signal | Meaning | What you should do |
|---|---|---|
| exit code `0`, `status: passed` | Every check passed after convergence | Present the change with the evidence. This proves only the checks that exist, in this lab |
| exit code `1`, `status: failed` | At least one check failed | Read `checks[].detail` and `checks[].evidence` for the failed ones, fix the config, rerun |
| exit code `2`, `status: error` | Config or lab problem (bad YAML, unknown node, lab didn't start) | Fix the setup; this says nothing about your change |

JSON report: `schema: netdryrun.report/v1`, with `checks[]` of `{name, type, params, passed, detail, attempts, duration_s, history, evidence}`.

## Rules
- **Never treat a pass as proof of production safety.** It covers the checks that exist, on the network OSes in the lab (FRR, SR Linux, Arista EOS), in steady state and in the defined failure scenarios.
- **Don't weaken checks to make a change pass.** If a check is wrong, say so explicitly to the human.
- Netdryrun never touches production devices. Only run topologies you were given or created in the lab folder.

## MCP
`netdryrun mcp` starts an MCP server (stdio) with the tools `dry_run`, `run_checks`, `record_baseline`, `validate` and `check_types`. Each result has a separate `verdict` field: `SAFE TO PROCEED` or `DO NOT APPLY THIS CHANGE`. Add it with `claude mcp add netdryrun -- netdryrun mcp`, or run it with `uvx netdryrun mcp`.

Docs: https://netdryrun.com/ai-agents/ · Full docs in one file: https://netdryrun.com/llms-full.txt
