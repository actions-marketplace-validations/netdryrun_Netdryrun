All 14 checks passed, including the 3 ticket checks (up1/peer1 receive 10.101.0.0/24, cust1 reaches peer from the new block) and all standing guards (sessions up, no leaks, 8.8.8.0/24 still rejected, peer prefix count still 3).

Change made to `configs/edge1.conf`:
- Added `10.101.0.0/24` to `CUSTOMER-IN` (seq 20) so edge1 accepts it from cust1.
- Added `10.101.0.0/24` to `OUR-ROUTES` (seq 30) so it's announced to up1 and peer1.

Netdryrun verdict: `SAFE TO PROCEED` (status `passed`, 14/14).

```json
{"verdict": "safe", "decision": "apply", "netdryrun_status": "passed", "changed_files": ["configs/edge1.conf"], "reason": "Added 10.101.0.0/24 to CUSTOMER-IN and OUR-ROUTES prefix-lists on edge1 so the new customer block is accepted from cust1 and advertised to up1 and peer1. Netdryrun passed all 14 checks (3 ticket + 11 guards), including leak and prefix-count guards."}
```