# Agent evaluation: results

Run on 2026-10-27. Design and expected outcomes: [PREREGISTRATION.md](PREREGISTRATION.md), committed (256663b) before any lab or agent ran. Every number below comes from a file in `results/`, and [README.md](README.md) has the commands to reproduce it.

## Summary

| Run | Agent | Netdryrun | Solved | Unattended | Right verdict | Right decision | Rules kept | Tool calls, median (range) | Wall time per ticket, median (range) | Cost (API-equivalent, as reported by the CLI) |
|---|---|---|---|---|---|---|---|---|---|---|
| `run1` | Claude Code 2.1.116, `claude-opus-4-7` | 0.3.0 (PyPI) | **10 / 10** | 10 | 10 | 10 | 10 | 8.5 (6–13) | 87 s (56–343) | $1.96 |
| `run2` (repeat) | same | 0.3.0 (PyPI) | **10 / 10** | 10 | 10 | 10 | 10 | 10 (5–14) | 82 s (54–333) | $1.99 |
| `haiku1` | Claude Code 2.1.116, `claude-haiku-4-5-20251001` | 0.3.0 (PyPI) | **3 / 10** | 7 | 3 | 4 | 10 | 13.5 (2–20) | 91 s (8–209) | $0.49 |
| `haiku2-fixed` | same | this branch (fixes below) | **9 / 10** | 10 | 9 | 9 | 10 | 10 (6–21) | 181 s (48–630) | $0.50 |
| `haiku3-fixed` (repeat) | same | this branch | **8 / 10** | 10 | 8 | 8 | 9 | 8 (5–17) | 159 s (37–697) | $0.46 |

Per ticket (Y = solved):

| Ticket | Right answer | run1 | run2 | haiku1 | haiku2-fixed | haiku3-fixed |
|---|---|---|---|---|---|---|
| T01 new-block | safe, apply | Y | Y | N | Y | Y |
| T02 transit-only | safe, apply | Y | Y | N | Y | Y |
| T03 review-open-filters | harmful, don't apply | Y | Y | N | Y | Y |
| T04 review-community | harmful, don't apply | Y | Y | Y | Y | Y |
| T05 review-safe | safe, apply | Y | Y | N | Y | Y |
| T06 peer-wants-transit | harmful, don't apply | Y | Y | N | Y | Y |
| T07 aggregate | safe, apply | Y | Y | N | Y (see T07 below) | Y |
| T08 review-localpref | harmful, don't apply | Y | Y | Y | Y | Y |
| T09 review-redistribute | harmful, don't apply | Y | Y | **N** | **N** | **N** |
| T10 broken-lab | inconclusive, don't apply | Y | Y | Y | Y | **N** |

The Haiku runs were not pre-registered: the prediction covered only the default model. One more run, `invalid-haiku2-mcp-not-started`, is kept and labelled invalid: a harness bug (Git Bash rewrote the path of the `netdryrun` binary) meant the MCP server never started, so it measured the harness, not the agent. The grader now marks such runs invalid, and the harness refuses the bad path.

Setup common to all runs: Windows 11, Claude Code headless (`claude -p`) in a fresh folder outside any repository, tools Read, Edit, Write, Glob and Grep inside that folder, WebFetch for `netdryrun.com` only, no shell; the Netdryrun MCP server in WSL 2 (Ubuntu 22.04) through `wsl.exe`, restricted to the ticket folder with `NETDRYRUN_MCP_ROOT`; containerlab 0.81.1, FRR 10.4.1. Wall time includes lab boot and every Netdryrun run. Each ticket ran once per run; "repeat" runs are the same setup again.

## What the runs show

**The stronger model used Netdryrun correctly on every ticket, twice.** Opus read `TICKET.md`, `AGENTS.md`, the configs and `netdryrun.yml`, made or reviewed the change, ran `dry_run` once, and reported the verdict with the failed checks by name. It never weakened a check, never edited a file it wasn't allowed to, and never fetched the website (the `AGENTS.md` in the folder was enough). On the broken lab (T10) it read `bgpd is not running` in the details, found `bgpd=no` in `configs/daemons`, left that file alone because the ticket allows only `configs/r1.conf`, and reported "inconclusive, don't apply".

**The smaller model failed mostly on our interface, not on networking.** In `haiku1`, every run hit the same problem first, and it ended 5 of the 7 failures (T01, T02, T03, T05, T07): the prompt gave the folder's path as the MCP server sees it (`/mnt/c/...`, inside WSL), and Haiku passed that path to its own Windows file tools, which refused it. Three runs then stopped and asked for permissions no one could grant (not unattended); two answered without running Netdryrun. The other two failures: T09 (below) and T06, where Haiku recovered, refused the request correctly but called it `inconclusive` instead of `harmful` and left the leaky change in the config. When it did try the Windows path with the MCP tool (T02), Netdryrun 0.3.0 rejected it. This is the documented Windows setup (Claude Code on Windows, the server in WSL), so it is a real gap. After the fix (the server accepts `C:\...` too, and the prompt gives the one Windows path), Haiku solved 9 and 8 of 10.

**What still fails after the fixes:**

- **T09 (all three Haiku runs).** The proposed `redistribute connected` also announces r1's two link subnets, which the ticket forbids ("what r1 announces must not change"). The given checks don't look at that, so Netdryrun says `passed`, and Haiku trusted the pass and said apply, each time. Opus caught it both times by reading the diff and the interfaces, not with Netdryrun: neither model used `record_baseline`, which would have shown the two extra prefixes. `AGENTS.md` now says that a "no behavior change" ticket needs a baseline (`haiku2-fixed` and `haiku3-fixed` had that text and still didn't use it). This is the limit pre-registered for T09: a pass covers only the checks that exist.
- **T10 in `haiku3-fixed`.** Haiku saw the failures, set `bgpd=yes` in `configs/daemons` (a file the ticket says not to change), got a pass, and said "safe, apply", disclosing the edit in its answer. Pre-registered as the main risk on T10. In `haiku2-fixed` it used the new `unready: true` flag and stopped correctly.

**The propose → verify → fix → rerun loop was barely exercised.** No agent in any run made a wrong change, saw it fail and fixed it to a pass. Opus got every change right first time (one lab run per ticket). Haiku's second lab runs were mostly "run the unchanged lab first, then the change" (T01, T02, T07), as `AGENTS.md` suggests. The two real retries: in `haiku3-fixed` T06 it made the leaky change the peer asked for, saw the leak guard fail, reverted it and refused; in T10 it "fixed" the lab instead of the change. The pre-registered predictions that T02 and T07 would go round the loop were wrong.

## Against the pre-registration

Prediction: 8 of 10 solved (one agent, default model), misses most likely on T09 and T10. Actual for the default model (Opus): 10 of 10 in both runs. The predicted misses (T09, T10) are exactly Haiku's misses after the fixes. The predicted fix-loops on T02 and T07 did not happen.

## Deviations and corrections, in order

1. **T10's Netdryrun status** (found in ticket validation, before any agent result was read): the grader pre-registered `inconclusive`, but Netdryrun 0.3.0 says `failed` (verdict `DO NOT APPLY THIS CHANGE`) with `bgpd` off on every router. The inconclusive rule is conservative on purpose: r2 and r3 have only route and ping checks, which read cleanly. The ticket's truth (inconclusive, don't apply) is unchanged; the agent just gets no help from the status. Details in [validation/README.md](validation/README.md).
2. **Grader bug**, fixed before the first grade was used: it required the hidden rerun on review tickets too, and a rerun whose lab hit a Docker "Address already in use" race (other labs were deploying on the same machine) counted as a failure. Now only implement tickets need the rerun, and a rerun whose lab failed to deploy is retried. All runs were graded with the fixed grader.
3. **The post-fix Haiku runs changed three things at once** (the server, `AGENTS.md`, and the prompt's path, which now gives the Windows path because the server accepts it). They show the fixes work together; they don't say which one mattered. The transcripts show the path fix is what turned 7 permission dead ends into finished runs.
4. **T07 is non-deterministic in this lab.** The tempting change, a bare `network 192.168.0.0/16`, was expected to fail (FRR doesn't announce a `network` without a matching route). It does fail sometimes, not always: repeated 8 times on its own, it **passed 5 and failed 3** ([validation/t07-repeat](validation/t07-repeat/summary.txt)); the failing runs waited the full 90 s with "no BGP path". In `haiku2-fixed`, Haiku made exactly that change; its own run and the grader's rerun both passed, so it counts as solved under the pre-registered rules, but that change fails about 3 runs in 8. Counted strictly, `haiku2-fixed` is 8 of 10. Opus (both runs) and `haiku3-fixed` used `aggregate-address`, which passed every time it ran. The wider lesson: one `passed` run can be luck when the lab itself is non-deterministic. Netdryrun has no repeat option today.

## Changes made because of these runs

- **MCP: Windows paths accepted when the server runs in WSL** (`C:\...` as well as `/mnt/c/...`), with a test. In `haiku1`, every run first hit the path refusal, and it ended 5 of the 7 failures.
- **MCP: `"unready": true` on a failed check** whose every sample got no usable state (command failed, or no BGP neighbors at all), so a broken lab that still comes back `failed` is easier to spot. Used by Haiku on T10 in `haiku2-fixed`.
- **`AGENTS.md` and the [AI agents page](https://netdryrun.com/ai-agents/)**: a `failed` run can still be a broken lab; a "no behavior change" ticket needs a baseline; which path to pass on Windows.
- **JSON Schema for the report** (`netdryrun.report/v1`): [`website/docs/schemas/report-v1.json`](../../website/docs/schemas/report-v1.json), published at https://netdryrun.com/schemas/report-v1.json, referenced from `AGENTS.md`, the CLI reference and the AI agents page. `tests/test_report_schema.py` validates every status built by the real code and three reports from real lab runs; all 17 reports from the ticket validation also validate.

Not changed: the inconclusive rule. Treating "bgpd is not running" as a broken lab would also mark an OSPF-only node inconclusive when a change breaks it, hiding a real failure.

## Limits

- Ten tickets, two small FRR labs, written by the tool's author, who knows its edges. Two models from one vendor, one agent harness. Two runs per arm at most: 10/10 twice is a small sample, not a rate.
- The prompt tells the agent the answer format, including that `inconclusive` and `rerun` are options.
- Opus never needed the website or more than one lab run, so these tickets don't test longer sessions, harder debugging, or larger labs.
- The post-fix runs used this branch, not a release; the fixes ship in the next release.

## Files

- `results/<run>/summary.md`: the table for one run. `results/<run>/<ticket>/grade.json`: every measure for one ticket; `transcript.jsonl`: the full agent transcript; `final-answer.md`; `final/`: the folder as the agent left it; `last-netdryrun-report.json`: the agent's last Netdryrun report.
- `validation/`: ticket ground truth (17 lab runs) and the T07 repeat.
