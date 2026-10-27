| Ticket | Unattended | Verdict (truth) | Decision (truth) | Rules kept | Hidden rerun | Solved | Tool calls (Netdryrun) | Lab runs | Wall time |
|---|---|---|---|---|---|---|---|---|---|
| T01-new-block | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 11 (1) | 1 | 70 s |
| T02-transit-only | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 13 (1) | 1 | 88 s |
| T03-review-open-filters | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 6 (1) | 1 | 60 s |
| T04-review-community | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 6 (1) | 1 | 146 s |
| T05-review-safe | yes | safe (safe)  | apply (apply)  | yes | - | yes | 6 (1) | 1 | 59 s |
| T06-peer-wants-transit | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 7 (1) | 1 | 85 s |
| T07-aggregate | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 10 (1) | 1 | 121 s |
| T08-review-localpref | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 10 (1) | 1 | 208 s |
| T09-review-redistribute | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 7 (1) | 1 | 56 s |
| T10-broken-lab | yes | inconclusive (inconclusive)  | dont_apply (dont_apply/rerun)  | yes | failed | yes | 13 (1) | 1 | 343 s |

Solved: 10 of 10
