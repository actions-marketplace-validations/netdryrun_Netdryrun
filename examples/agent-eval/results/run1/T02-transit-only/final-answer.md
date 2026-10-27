All 14 checks passed. The change achieves transit-only announcement for 10.101.0.0/24: up1 receives it (and cust1 can reach the internet via up1), peer1 does not. All guard checks and leak guards remain intact.

**Summary of changes to `configs/edge1.conf`:**
- Added `10.101.0.0/24` to the `CUSTOMER-IN` prefix-list (so cust1 can announce it to us).
- Replaced the single `OUR-ROUTES` prefix-list with two: `TO-UPSTREAM-PFX` (includes 10.101.0.0/24) and `TO-PEER-PFX` (excludes it).
- Updated `TO-UPSTREAM` and `TO-PEER` route-maps to reference the new prefix-lists.

Netdryrun verdict: **SAFE TO PROCEED** (14/14 passed).

```json
{"verdict": "safe", "decision": "apply", "netdryrun_status": "passed", "changed_files": ["configs/edge1.conf"], "reason": "Added 10.101.0.0/24 to CUSTOMER-IN and split OUR-ROUTES into TO-UPSTREAM-PFX (with 10.101.0.0/24) and TO-PEER-PFX (without it). Netdryrun run passed all 14 checks: the new block reaches up1 and the internet, peer1 does not receive it, and all guards/leak-guards hold."}
```