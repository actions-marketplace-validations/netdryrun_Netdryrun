# Layer 6: independent review, Netdryrun 0.3.2

## Cold code review (fresh agent, no context, the diff v0.3.1..ndr/agent-contract, src/ and tests/)
The question: any way the change can report `passed` or SAFE TO PROCEED without testing what the file or the agent's request says; any way the MCP path handling can be steered outside `NETDRYRUN_MCP_ROOT`; any exit-code change that turns a failure into a non-failure. The reviewer found no false pass on a run with a failed check and no escape from the root (`..`, symlinks, `~`, drive-relative, UNC and unmounted Windows paths all checked after `resolve()`).

| # | Finding | Severity | Decision | Commit |
|---|---|---|---|---|
| 1 | A relative MCP path resolved against the root could pick the main checkout's copy when the agent edited a worktree copy inside the root: SAFE TO PROCEED for a file the agent never changed | Possible false pass | Refused when the working directory holds a different file at that path (a folder counts when it holds `netdryrun.yml`); the working-directory file is used when only it exists, as before; the root check still follows | `319e989` |
| 2 | Skipping scenarios after an inconclusive main phase looked only at the main checks' nodes: a scenario on readable nodes that would have failed (exit 1) became inconclusive (exit 3) | Wrong exit (still non-passing) | Skip only when every node a scenario faults or checks never gave state (`checks.never_ready_nodes`, the same rule as `inconclusive_reason`) | `f8bb3fd` |
| 3 | An IPv6 scope ID (`fe80::1%…`) accepts any text, newlines included; it reached device CLI commands and the MCP `next_diagnostic` (EOS `Cli -c` runs each line) | Injection | The scope must be an interface name; anything else is a config error (exit 2) | `6175c2f` |
| 4 | A crash while building `failures` would lose the verdict (MCP error) | Low | Rejected: `evidence` entries are built by the drivers as dicts, never from lab or file input; a crash there is an MCP error with no verdict, which fails closed | — |
| 5 | `run_checks` returns SAFE TO PROCEED for a kept lab whose configs may be older than the agent's edits | Design, not new | Rejected for 0.3.2: the verdict strings are frozen for v1 and the description already says edited configs don't reach a running lab; backlog item: a `tested_change: false` field for `run_checks` | — |

Each fix was test-first: the tests failed on the branch before the fix (`test_relative_path_that_names_two_files_is_refused`, `test_scenarios_on_nodes_that_gave_state_still_run_after_an_unready_main_phase`, `test_ipv6_scope_id_must_be_an_interface_name`).

**Note on finding 3:** the same addresses already reached the lab's own commands in 0.3.1 (`drivers/eos.py`); the config check closes both.
