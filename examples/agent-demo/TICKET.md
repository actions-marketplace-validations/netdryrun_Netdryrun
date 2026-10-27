# Ticket NET-1042: announce the customer's new block

Customer **cust1** (AS 65100) has a new address block, **10.101.0.0/24**, and is already announcing it to us over BGP. Make sure our upstream (**up1**) and our peer (**peer1**) receive it, so the internet can reach it.

Rules for whoever works this ticket, human or AI agent:

- Change only `configs/edge1.conf` (our edge router, AS 65000).
- Don't edit `netdryrun.yml`. It holds the ticket's acceptance checks and the standing guards the network team requires for every change.
- Before proposing the change, run Netdryrun on this folder (`netdryrun run <folder>`, or the `dry_run` MCP tool) and include the verdict. Propose it only if the status is `passed`.
