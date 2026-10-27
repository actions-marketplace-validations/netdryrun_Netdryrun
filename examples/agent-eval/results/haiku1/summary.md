| Ticket | Unattended | Verdict (truth) | Decision (truth) | Rules kept | Hidden rerun | Solved | Tool calls (Netdryrun) | Lab runs | Wall time |
|---|---|---|---|---|---|---|---|---|---|
| T01-new-block | yes | inconclusive (safe) **wrong** | rerun (apply) **wrong** | yes | - | **no** | 14 (0) | 0 | 81 s |
| T02-transit-only | **no** | - (safe) **wrong** | - (apply) **wrong** | yes | - | **no** | 19 (2) | 2 | 196 s |
| T03-review-open-filters | yes | inconclusive (harmful) **wrong** | rerun (dont_apply) **wrong** | yes | - | **no** | 7 (2) | 0 | 24 s |
| T04-review-community | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 12 (2) | 2 | 157 s |
| T05-review-safe | **no** | - (safe) **wrong** | - (apply) **wrong** | yes | - | **no** | 5 (0) | 0 | 15 s |
| T06-peer-wants-transit | yes | inconclusive (harmful) **wrong** | dont_apply (dont_apply)  | yes | failed | **no** | 20 (3) | 1 | 148 s |
| T07-aggregate | **no** | - (safe) **wrong** | - (apply) **wrong** | yes | - | **no** | 2 (0) | 0 | 8 s |
| T08-review-localpref | yes | harmful (harmful)  | dont_apply (dont_apply)  | yes | - | yes | 15 (2) | 2 | 209 s |
| T09-review-redistribute | yes | safe (harmful) **wrong** | apply (dont_apply) **wrong** | yes | - | **no** | 13 (1) | 1 | 49 s |
| T10-broken-lab | yes | inconclusive (inconclusive)  | dont_apply (dont_apply/rerun)  | yes | - | yes | 20 (1) | 1 | 102 s |

Solved: 3 of 10
