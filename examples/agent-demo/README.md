# Agent demo: a ticket, a tempting change, and a verdict

An edge router (`edge1`, AS 65000) has a customer, an upstream and a peer. The ticket ([TICKET.md](TICKET.md)): the customer's new block 10.101.0.0/24 must reach the upstream and the peer. The network team's [`netdryrun.yml`](netdryrun.yml) has the ticket's acceptance checks plus standing guards, including route-leak guards. The agent may only change `configs/edge1.conf`.

```bash
examples/agent-demo/demo.sh
```

The script replays two attempts on a scratch copy (this folder is never modified):

| Attempt | Change | Ticket checks, sessions, pings | Leak guards | Verdict |
|---|---|---|---|---|
| 1 ([diff](changes/attempt-1-open-filters.diff)) | "The prefix lists block the new block": removes the three prefix-list matches | all pass | 4 fail: upstream routes and the default leak to the peer, peer routes leak to the upstream | `FAILED` (exit 1), do not apply |
| 2 ([diff](changes/attempt-2-prefix-lists.diff)) | Adds 10.101.0.0/24 to the two prefix lists | all pass | all pass | `PASSED` (exit 0) |

Attempt 1 is the change a hurried engineer or an agent makes: it does what the ticket asked, and a ping or a "sessions are up" test would approve it. Netdryrun rejects it because the network team's guards encode what must never happen. The leaked default route even arrives as received-but-not-selected on the peer; Netdryrun counts it as present.

`demo.sh` exits 0 only if attempt 1 is rejected and attempt 2 accepted; CI runs it on every push. With an MCP client, give an agent `TICKET.md` and this folder (without `changes/` and `demo.sh`) and the `netdryrun mcp` tools, and let it work the ticket.

To see the starting point, run `netdryrun run examples/agent-demo`: the 10 guards pass and the 3 ticket checks fail, because the work isn't done yet.
