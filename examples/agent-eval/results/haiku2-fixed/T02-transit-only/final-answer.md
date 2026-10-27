Excellent! All checks pass. The configuration successfully implements the transit-only announcement:

**Summary of Changes:**
1. ✅ **TICKET requirement 1**: up1 receives 10.101.0.0/24 via BGP (active)
2. ✅ **TICKET requirement 2**: New block reaches internet via up1 (3/3 pings)
3. ✅ **TICKET requirement 3**: peer1 does NOT receive 10.101.0.0/24 (transit-only enforced)
4. ✅ **All guard checks pass**: Existing routes, BGP sessions, and leak guards remain intact

**What was changed in edge1.conf:**
- Added 10.101.0.0/24 to CUSTOMER-IN prefix-list (accept from customer)
- Created new TRANSIT-ONLY prefix-list with 10.101.0.0/24
- Extended TO-UPSTREAM route-map with second permit block to also match TRANSIT-ONLY prefixes
- TO-PEER route-map remains unchanged (only announces OUR-ROUTES, not transit-only)

```json
{
  "verdict": "safe",
  "decision": "apply",
  "netdryrun_status": "passed",
  "changed_files": ["configs/edge1.conf"],
  "reason": "Configuration adds transit-only announcement of 10.101.0.0/24 to upstream only, blocking it from peer. All 14 checks passed including ticket requirements and standing guards."
}
```