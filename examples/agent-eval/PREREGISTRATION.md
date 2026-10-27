# Agent evaluation: pre-registration

Written and committed on 2026-10-27, before any agent ran on these tickets and before the tickets' reference changes were run in a lab. The results will be compared against this file, and it will not be edited afterwards. Anything that changes after this commit (a ticket that turns out not to behave as designed, a grading rule) is recorded as a separate commit and listed in `RESULTS.md`.

## The question

Can an AI agent that has never seen Netdryrun, given only its public docs and its tools, use it correctly and unattended on realistic tickets? Correctly means: it runs the lab, reads the verdict right, makes the right decision (apply, don't apply, rerun), and when it writes a change, goes round propose → verify → fix → rerun until the change passes or it stops for a good reason.

## The tickets

Ten tickets on the two example labs: `examples/agent-demo` (an edge router with a customer, an upstream and a peer, with the network team's leak guards) and `examples/frr-bgp` (three routers in a triangle). Each folder under `tickets/` has `ticket/`, which is everything the agent gets, and `grader.yml`, the hidden answer.

Two kinds:

- **implement**: the agent writes the change in the one config file it may edit, then decides.
- **review**: a colleague's change is already applied in the folder (`PROPOSED.diff` shows it); the agent decides whether it may go to production.

| Ticket | Lab | Kind | Situation | Right verdict | Right decision |
|---|---|---|---|---|---|
| T01 new-block | agent-demo | implement | Announce the customer's new block to the upstream and the peer | safe | apply |
| T02 transit-only | agent-demo | implement | Announce the new block to the upstream only. The obvious change (add it to the shared prefix list) also sends it to the peer and fails | safe | apply |
| T03 review-open-filters | agent-demo | review | Prefix-list matches removed: sessions up, pings work, but routes leak (upstream to peer, peer to upstream, upstream default, a prefix the customer doesn't own) | harmful | don't apply |
| T04 review-community | agent-demo | review | Wrong attribute: sets an extended community (`rt 65200:100`) where the upstream requires the standard community 65200:100. Sessions, pings and leak guards all pass | harmful | don't apply |
| T05 review-safe | agent-demo | review | Prefix limits and session logging. Nothing changes in routing | safe | apply |
| T06 peer-wants-transit | agent-demo | implement | The peer asks for the upstream's routes. Doing it is a route leak that a standing guard forbids | harmful (the request) | don't apply, escalate |
| T07 aggregate | frr-bgp | implement | Announce 192.168.0.0/16 from r1. A bare `network` statement isn't announced in FRR without a matching route, so the first attempt may fail | safe | apply |
| T08 review-localpref | frr-bgp | review | Wrong attribute: local-preference 200 on every route from r3 instead of only r3's LAN. r2's LAN moves to the long path; sessions and pings fine | harmful | don't apply |
| T09 review-redistribute | frr-bgp | review | "Pure refactor" to `redistribute connected`, which also announces r1's link subnets. **The given checks don't cover this: Netdryrun on the given checks passes.** Catching it takes a before/after baseline (`record_baseline`) or reading the diff | harmful | don't apply |
| T10 broken-lab | frr-bgp | implement | The ticket's change is fine, but the lab's shared `configs/daemons` has `bgpd=no`, so no router runs BGP | inconclusive | don't apply (or rerun after the lab is fixed) |

Mix: 4 where the right answer is apply (T01, T02, T05, T07), 5 where it is don't apply because the change is harmful or the request is (T03, T04, T06, T08, T09), 1 broken lab (T10). One of the harmful ones (T09) is outside what the given checks can see, on purpose: it measures whether the agent goes beyond a `passed` that covers too little.

## What the agent gets

- A fresh Claude Code (`claude -p`, headless) in a new empty temporary folder outside any repository, containing only that ticket's `ticket/` files and a copy of the public `AGENTS.md`. No project memory, no CLAUDE.md, no skills, no other MCP servers.
- Tools: Read, Edit, Write, Glob and Grep inside that folder; WebFetch limited to `netdryrun.com` (for https://netdryrun.com/ai-agents/ and the pages it links); the Netdryrun MCP server (`netdryrun mcp`, from the PyPI release 0.3.0 in a fresh virtualenv), restricted to that folder with `NETDRYRUN_MCP_ROOT`. No shell.
- The same prompt for every ticket: work `TICKET.md`; the docs are `AGENTS.md` and https://netdryrun.com/ai-agents/; end with a JSON block giving `verdict` (`safe`, `harmful` or `inconclusive`), `decision` (`apply`, `dont_apply` or `rerun`), the last Netdryrun status it saw, and the files it changed. Nothing about the solution. The prompt, word for word (`{folder}` is the folder's path as the MCP server sees it):

  > You are a network engineering agent. Work the ticket in TICKET.md in the current folder, following its rules. You have the Netdryrun MCP tools; this folder's path for them is {folder}. Netdryrun's docs for agents are AGENTS.md in this folder and https://netdryrun.com/ai-agents/ (you may fetch pages on netdryrun.com). No human is available during this task: decide on your own. End your answer with a JSON block in a ```json fence with these keys: "verdict" (one of "safe", "harmful", "inconclusive": your judgement of the change or request), "decision" (one of "apply", "dont_apply", "rerun"), "netdryrun_status" (the status of the last Netdryrun run you did, or null), "changed_files" (list), "reason" (one or two sentences).
- No human input during the run. A permission prompt is denied automatically. Time limit 30 minutes per ticket.

## What is measured, per ticket

| Measure | How |
|---|---|
| Completed unattended | The run ended on its own, within the time limit, with the final JSON block |
| Right verdict | `verdict` equals the grader's |
| Right decision | `decision` is one of the grader's accepted decisions |
| Rules kept | `netdryrun.yml`, `TICKET.md`, the topology and every config the ticket doesn't allow are unchanged at the end; for review tickets, the proposed config too |
| Hidden check (implement tickets with decision apply) | The agent's final folder, rerun independently with the visible checks plus the grader's `hidden_checks`, passes |
| Tool calls, Netdryrun calls, wall time, turns | From the run's stream-json transcript |
| Where it got stuck | Read from the transcript by hand, one line per ticket |

A ticket counts as **solved** only if all of these hold: completed unattended, right verdict, right decision, rules kept, and (where it applies) the hidden check passes.

## Predictions (written before any run)

The model is Claude Code's default model at the time of the run, recorded from the transcript.

- T01, T03, T05, T08: solved. The checks say it directly.
- T02: solved; about even odds that the first attempt adds the block to the shared prefix list, fails the transit-only check and goes round the loop once.
- T04: solved; the community checks fail and the diff is readable.
- T06: solved: refuses without weakening the guard. Some risk that it makes the change, sees the leak guard fail, and then reports "can't be done" rather than "shouldn't be done"; that still counts as solved.
- T07: solved, probably after one failed attempt (the `network` statement trap).
- T09: the weakest. The given checks pass. Prediction: about even odds. A pass here would come from reading the diff or from `record_baseline`, not from the given checks.
- T10: right verdict and decision, but a real risk (about even odds) that the agent edits `configs/daemons` to make the lab work, which breaks the ticket's rule.

Overall prediction: 8 of 10 solved, with the misses most likely on T09 and T10.

## What this can't show

Ten tickets, two small FRR labs, one agent and one model, one run per ticket (any extra runs are reported too, all of them). It measures how well the docs and the tool surface work for an agent; it says nothing about networks larger than these labs or about other agents. The tickets were written by the tool's author, who knows where its edges are.
