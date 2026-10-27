I've identified the necessary changes to edge1.conf, but I'm unable to apply them due to tool restrictions. Both the Read and Write tools require that I first read the file using the Read tool, but Read access is currently blocked in "don't ask mode."

I've used Grep to fully review the file content (line-by-line), and I know exactly what changes are needed:

**Changes to make to configs/edge1.conf:**
1. Add `ip prefix-list CUSTOMER-IN seq 20 permit 10.101.0.0/24` to accept the new prefix from the customer
2. Replace the single `OUR-ROUTES` prefix-list with two separate lists:
   - `UPSTREAM-ROUTES` (includes 192.0.2.0/24, 10.100.0.0/24, and 10.101.0.0/24)
   - `PEER-ROUTES` (includes 192.0.2.0/24 and 10.100.0.0/24 only - not the transit-only 10.101.0.0/24)
3. Update the `TO-UPSTREAM` and `TO-PEER` route-maps to use their respective prefix-lists

This implements the transit-only policy: the customer's new 10.101.0.0/24 block will only be announced to upstream (up1), not to the peer (peer1).

**To proceed, I need:**
- Permission to use the Read tool so I can then use Write to apply the changes
- Or access to another tool that can modify the file

Would you like to grant Read/Write permissions so I can apply these changes and verify them with Netdryrun?