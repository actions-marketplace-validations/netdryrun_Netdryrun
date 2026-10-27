All 14 checks passed, including the three ticket checks and all standing/leak guards. The verdict is SAFE TO PROCEED.

## Change summary

Edited `configs/edge1.conf` to implement transit-only for cust1's new 10.101.0.0/24:
- Added `10.101.0.0/24` to `CUSTOMER-IN` so edge1 accepts it from cust1.
- Split the single `OUR-ROUTES` outbound list into two:
  - `TO-UPSTREAM-OUT`: 192.0.2.0/24, 10.100.0.0/24, **10.101.0.0/24** (transit path to up1).
  - `TO-PEER-OUT`: 192.0.2.0/24, 10.100.0.0/24 only (peer1 does **not** get 10.101.0.0/24).
- Pointed `TO-UPSTREAM` and `TO-PEER` route-maps at their respective new prefix-lists.

The customer's bogus 8.8.8.0/24 announcement is still rejected (CUSTOMER-IN only lists 10.100/24 and 10.101/24), and all other guards hold.

```json
{"verdict": "safe", "decision": "apply", "netdryrun_status": "passed", "changed_files": ["configs/edge1.conf"], "reason": "Split outbound filter so up1 gets 10.101.0.0/24 (transit) while peer1 does not; Netdryrun passed all 14 checks including ticket, standing guards and leak guards."}
```