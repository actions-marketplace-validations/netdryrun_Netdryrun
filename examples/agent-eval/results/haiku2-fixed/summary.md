| Ticket | Unattended | Verdict (truth) | Decision (truth) | Rules kept | Hidden rerun | Solved | Tool calls (Netdryrun) | Lab runs | Wall time |
|---|---|---|---|---|---|---|---|---|---|
| T01-new-block | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 12 (2) | 2 | 198 s |
| T02-transit-only | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 15 (2) | 2 | 207 s |
| T03-review-open-filters | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 6 (1) | 1 | 58 s |
| T04-review-community | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 9 (1) | 1 | 169 s |
| T05-review-safe | yes | safe (safe)  | apply (apply)  | yes | - | yes | 9 (1) | 1 | 64 s |
| T06-peer-wants-transit | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 13 (1) | 1 | 120 s |
| T07-aggregate | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 11 (2) | 2 | 293 s |
| T08-review-localpref | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 7 (1) | 1 | 193 s |
| T09-review-redistribute | yes | safe (harmful) **wrong** | apply (dont_apply) **wrong** | yes | - | **no** | 7 (1) | 1 | 48 s |
| T10-broken-lab | yes | inconclusive (inconclusive)  | dont_apply (dont_apply/rerun)  | yes | failed | yes | 21 (2) | 2 | 630 s |

Solved: 9 of 10
