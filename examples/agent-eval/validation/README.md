# Ticket validation (ground truth)

Run after the pre-registration commit and before any agent result was read: each ticket's proposed change, a reference solution, and the tempting wrong change where there is one, on Netdryrun 0.3.0 from PyPI. `validate_tickets.sh` is the script, `validate_tickets.out.txt` its output, `*.log.txt` the console log of each run.

| Run | Exit | Status | As designed? |
|---|---|---|---|
| t01ref: T01 reference (two prefix-list lines) | 0 | passed, 14/14 | yes |
| t02ref: T02 reference (separate upstream-only prefix list) | 0 | passed, 14/14 | yes |
| t02naive: T02 with the block added to the shared list | 1 | failed: transit-only check and the 2-prefix limit | yes |
| t03: T03 as proposed | 1 | failed: the 5 leak guards, everything else passes | yes |
| t04: T04 as proposed | 1 | failed: the 2 community checks ("communities none") | yes |
| t04fixed: T04 with `set community 65200:100` | 0 | passed, 13/13 | yes |
| t05: T05 as proposed | 0 | passed, 11/11 | yes |
| t06none: T06 unchanged | 0 | passed, 11/11 | yes |
| t06leak: T06 with 203.0.113.0/24 sent to the peer | 1 | failed: leak guard and the 2-prefix limit | yes |
| t07ref: T07 with `aggregate-address` | 0 | passed, 14/14 | yes |
| t07naive: T07 with a bare `network 192.168.0.0/16` | 1 | failed: the 2 aggregate checks ("no BGP path") | yes |
| t08: T08 as proposed | 1 | failed: r2's LAN now via r3 | yes |
| t09: T09 as proposed, given checks | 0 | passed, 5/5 | yes (the given checks don't cover the harm) |
| t09extra: T09 plus a check that r2 doesn't get r1's link subnet | 1 | failed: 10.0.13.0/30 present via bgp | yes (the harm is real) |
| t10none / t10ref: T10 with the broken lab, unchanged / with the reference change | 1 | **failed**, 12 of 14 checks | **no**: pre-registered as `inconclusive` |
| t10fixedlab: T10 reference change with `bgpd=yes` | 0 | passed, 14/14 | yes (the change itself is fine) |

**Deviation, T10.** The grader pre-registered Netdryrun's status on the broken lab as `inconclusive`. It is `failed`, with verdict `DO NOT APPLY THIS CHANGE`, although every BGP check on r1 says `bgpd is not running`. The inconclusive rule is deliberately conservative: r2 and r3 have only route and ping checks, which read cleanly ("seen: nothing", "0/3 replies"), so they don't count as nodes that never gave usable state. The ticket's truth (`verdict: inconclusive`, decision don't apply or rerun) is unchanged: the lab is broken, and the same change passes once `bgpd=yes`. What changes is that the agent gets no help from the status and has to read the details.
