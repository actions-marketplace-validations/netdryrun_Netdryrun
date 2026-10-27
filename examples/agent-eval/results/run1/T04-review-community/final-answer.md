Netdryrun confirms the change is broken. Both ticket checks fail with "communities none" — the routes arrive at up1 with no community attached.

**Root cause:** the author used `set extcommunity rt 65200:100`, which sets an *extended community* of type route-target. The ticket (and the upstream's requirement) is a **standard BGP community** `65200:100`. These are two different BGP attribute types; the extcommunity goes out on the wire as an RT extended community, not as the community the upstream filters on. The correct line is `set community 65200:100`.

Guards all pass, so nothing is leaking — but the stated goal of the change (get the community onto routes sent to up1) is not achieved. Applying this tonight would ship a config that looks fine but leaves us untagged, and up1 will stop re-announcing our routes next week.

**Recommendation:** do not apply. Author should change `set extcommunity rt 65200:100` to `set community 65200:100` on `route-map TO-UPSTREAM permit 10` in `configs/edge1.conf`, then rerun.

```json
{
  "verdict": "harmful",
  "decision": "dont_apply",
  "netdryrun_status": "failed",
  "changed_files": [],
  "reason": "The diff uses `set extcommunity rt 65200:100` (an extended-community route-target), not the standard BGP community the ticket and upstream require. Netdryrun confirms both routes reach up1 with communities none; the fix is `set community 65200:100`."
}
```