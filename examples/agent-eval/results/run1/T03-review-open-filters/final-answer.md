Netdryrun returned `status: failed` with 5 leak-guard failures. The change is unsafe.

## Review: CHG-3103 — DO NOT APPLY

**Verdict:** harmful — the change creates four distinct route leaks.

**What the diff does:** removes three prefix-list `match` statements entirely:
- `CUSTOMER-IN` route-map (inbound from cust1): removes `match ip address prefix-list CUSTOMER-IN`
- `TO-UPSTREAM` route-map (outbound to up1): removes `match ip address prefix-list OUR-ROUTES`
- `TO-PEER` route-map (outbound to peer1): removes `match ip address prefix-list OUR-ROUTES`

**What Netdryrun observed (5 failed checks):**
- `LEAK GUARD peer1 must not get upstream routes` → `203.0.113.0/24` now leaks from up1 to peer1
- `LEAK GUARD peer1 must not get the upstream's default route` → `0.0.0.0/0` from upstream now reaches peer1
- `LEAK GUARD up1 must not get peer routes` → `198.51.100.0/24` from peer1 now leaks to up1
- `LEAK GUARD peer1 gets at most our 3 prefixes` → peer1 receives 6 prefixes instead of 3
- `LEAK GUARD edge1 rejects prefixes the customer doesn't own` → `8.8.8.0/24` (which cust1 does not own) is now accepted from the customer

The ticket's three positive checks all pass only because the filters have been removed — so the new block flows, but so does everything else.

**Correct fix (for the author):** keep the three `match` statements and instead add the new block to the prefix lists, e.g.:
- `ip prefix-list CUSTOMER-IN seq 20 permit 10.101.0.0/24`
- `ip prefix-list OUR-ROUTES seq 30 permit 10.101.0.0/24`

That gets 10.101.0.0/24 announced to up1 and peer1 while preserving the customer-prefix filter and the leak barriers.

**Changed files:** none by me — I only reviewed. The ticket says don't rewrite the change.

```json
{"verdict": "harmful", "decision": "dont_apply", "netdryrun_status": "failed", "changed_files": [], "reason": "Removing the three prefix-list matches opens four leaks (upstream->peer, peer->upstream, upstream default, unowned 8.8.8.0/24 from customer); Netdryrun's five LEAK GUARD checks fail. The author should add 10.101.0.0/24 to CUSTOMER-IN and OUR-ROUTES instead of removing the matches."}
```