Netdryrun confirms the behavioral problem. Both ticket checks fail: up1 receives our routes with "communities none" — the extended community route-target isn't the standard BGP community that the upstream requires.

**Summary for the author**

The change does not do what the ticket asks. In FRR, `set extcommunity rt 65200:100` sets a Route Target extended community (used for VPNs/MPLS), not a standard BGP community. The upstream requires the standard community `65200:100`.

Netdryrun run against the proposed `configs/edge1.conf`:
- `status: failed`, 11 passed, 2 failed
- `TICKET up1 gets our block with community 65200:100` — **failed**: best path at up1 has `communities none`
- `TICKET up1 gets the customer's block with community 65200:100` — **failed**: same, `communities none`
- All session, reachability and leak guards still pass

Fix: on `route-map TO-UPSTREAM permit 10`, use `set community 65200:100` instead of `set extcommunity rt 65200:100`. Also ensure `neighbor 10.0.2.2 send-community` is in effect (FRR sends standard communities by default, so no extra line should be needed).

Do not apply this change tonight; return it to the author.

```json
{"verdict": "harmful", "decision": "dont_apply", "netdryrun_status": "failed", "changed_files": [], "reason": "The author used 'set extcommunity rt 65200:100', which sets an extended-community Route Target, not the standard BGP community 65200:100 the upstream requires. Netdryrun confirms up1 receives our prefixes with 'communities none', so both ticket checks fail; author should change it to 'set community 65200:100'."}
```