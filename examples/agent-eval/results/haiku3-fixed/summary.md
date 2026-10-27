| Ticket | Unattended | Verdict (truth) | Decision (truth) | Rules kept | Hidden rerun | Solved | Tool calls (Netdryrun) | Lab runs | Wall time |
|---|---|---|---|---|---|---|---|---|---|
| T01-new-block | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 12 (2) | 2 | 197 s |
| T02-transit-only | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 14 (1) | 1 | 85 s |
| T03-review-open-filters | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 5 (1) | 1 | 55 s |
| T04-review-community | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 7 (1) | 1 | 162 s |
| T05-review-safe | yes | safe (safe)  | apply (apply)  | yes | - | yes | 7 (1) | 1 | 66 s |
| T06-peer-wants-transit | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 9 (2) | 2 | 156 s |
| T07-aggregate | yes | safe (safe)  | apply (apply)  | yes | passed | yes | 10 (2) | 2 | 285 s |
| T08-review-localpref | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 7 (1) | 1 | 193 s |
| T09-review-redistribute | yes | safe (harmful) **wrong** | apply (dont_apply) **wrong** | yes | - | **no** | 7 (2) | 1 | 37 s |
| T10-broken-lab | yes | safe (inconclusive) **wrong** | apply (dont_apply/rerun) **wrong** | **no** | passed | **no** | 17 (3) | 3 | 697 s |

Solved: 8 of 10
