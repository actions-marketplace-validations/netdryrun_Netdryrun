# Agent demo: a ticket, a tempting change, and a verdict

An edge router (`edge1`, AS 65000) has a customer, an upstream and a peer. The ticket ([TICKET.md](TICKET.md)): the customer's new block 10.101.0.0/24 must reach the upstream and the peer. The network team's [`netdryrun.yml`](netdryrun.yml) has the ticket's acceptance checks plus standing guards, including route-leak guards. Whoever works the ticket, human or agent, may only change `configs/edge1.conf`.

```bash
examples/agent-demo/demo.sh
```

The script is a **scripted replay**: the two attempts are hand-written diffs showing how an agent might work the ticket, not output from a real agent. It runs them on a scratch copy, so nothing in this folder changes (set `OUT=<folder>` to keep the JSON reports).

| Attempt | Change | Ticket checks, sessions, pings | Leak guards | Verdict |
|---|---|---|---|---|
| 1 ([diff](changes/attempt-1-open-filters.diff)) | "The prefix lists block the new block": removes the three prefix-list matches (customer import, upstream export, peer export) | all pass | fail: upstream routes and the upstream's default leak to the peer, peer routes leak to the upstream, edge1 accepts 8.8.8.0/24, which the customer doesn't own | `FAILED` (exit 1), do not apply |
| 2 ([diff](changes/attempt-2-prefix-lists.diff)) | Adds 10.101.0.0/24 to the two prefix lists | all pass | all pass | `PASSED` (exit 0) |

Attempt 1 is a change an engineer or an agent in a hurry could make: it does what the ticket asked, and a ping or a "sessions are up" test would approve it. Netdryrun rejects it because the network team's guards say what must never happen. The leaked default route even arrives on the peer as received but not selected (the container's own default route wins); Netdryrun still counts it as present.

`demo.sh` exits 0 only if attempt 1 fails on exactly the leak guards, with every other check passing, and attempt 2 passes every check. CI runs it on pushes to `main` and on pull requests.

**A real agent run** is recorded in [AGENT-RUN.md](AGENT-RUN.md): a fresh Claude Code agent with only the ticket, the lab and the Netdryrun MCP tools made the correct two-line change on the first try and proposed it with a 14/14 `passed` verdict.

To let a real agent work the ticket, give it only `TICKET.md`, `netdryrun.yml`, `topology.clab.yml` and `configs/` (not this README, `changes/` or `demo.sh`, which contain the answer), plus the `netdryrun mcp` tools.

To see the starting point, run `netdryrun run examples/agent-demo`: the guards pass and the 3 ticket checks fail, because the work isn't done yet.
