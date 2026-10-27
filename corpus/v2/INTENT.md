# Corpus v2 network intent

Corpus v2 tests the same small provider as [v1](../INTENT.md): AS65000, with routers `pe1` and `pe2`. The v1 results are frozen and nothing in `corpus/cases/`, `corpus/results/` or `corpus/RESULTS.md` changes. v2 has its own base lab (`v2/base/`, lab name `ndr-corpus-v2`), its own intent spec (`v2/specs/intent.yml`) and its own cases (`v2/cases/`).

| Neighbor | AS | Relationship | Announces |
|---|---|---|---|
| `ce1` | 65100 | Customer (pays us for full routes) | 10.100.0.0/24, from its registered block 10.100.0.0/16 |
| `up1` | 65200 | Upstream transit (we pay them) | 203.0.113.0/24 and a default route |
| `peer1` | 65300 | Settlement-free peer | 198.51.100.0/24 |

We originate our own aggregate 192.0.2.0/24 from a discard (blackhole) route.

## What changed from the v1 base, and why

There are two edits to `pe1.conf`. Both make the customer's safety limit meaningful:

- The customer's registered block is now 10.100.0.0/16, so the import filter is `10.100.0.0/16 le 24` (v1: `10.100.0.0/22 le 24`).
- The customer limit is `maximum-prefix 50 restart 1` (v1: `maximum-prefix 100`).

**Why:** FRR's maximum-prefix counts only the prefixes accepted after the import policy (verified on FRR 10.4.1: 100 routes rejected by the filter did not trip a limit of 50, and 100 accepted routes did). v1's filter could accept at most 7 customer prefixes (a /22, two /23s and four /24s), so its limit of 100 could never trip. In v1, removing the limit (case 21) had no effect the lab could ever show. With a /16 the customer can legitimately announce up to 256 /24s, and the limit is the only thing that stops a flood of them. `restart 1` re-opens the session one minute after a trip, which is how operators run limits in practice; without it, a tripped session stays down until someone clears it.

## The written intent

The Netdryrun checks in `v2/specs/intent.yml` encode this intent:

- **I1:** All four BGP sessions are established.
- **I2:** The customer route and our aggregate reach both the upstream and the peer.
- **I3:** The customer receives the upstream route, the peer route and a default, and can reach both networks.
- **I4:** No route leaks. Routes learned from the upstream or the peer are never announced to the other, and the default never goes to the peer.
- **I5:** We announce at least our aggregate and the customer's route to the upstream and to the peer, and never more than our aggregate plus the customer's limit (1 + 50 = 51). The customer may grow inside its /16 without a config change, so the count is a range, not an exact number (v1 used exactly 2, which blocked the customer's normal growth in case 06).
- **I6:** No infrastructure routes leave the AS or reach the customer. The four link /30s (10.0.1.0/30 to 10.0.4.0/30) and the router loopbacks (10.255.0.1/32 and 10.255.0.2/32) are never BGP routes at `ce1`, `up1` or `peer1`.
- **I7:** We never announce third-party address space. Netdryrun has no "only prefixes inside this range" check, so the spec spot-checks well-known third-party prefixes (the public resolver /24s 1.1.1.0/24, 8.8.8.0/24 and 9.9.9.0/24): none is ever a BGP route at `ce1`, `up1` or `peer1`. This is a sentinel list, not a full guarantee: an unexpected prefix not on the list is not caught. Case 04 exists to show that limit.
- **I8 (customer misbehaves):** If the customer floods us with 200 more-specifics from its own /16 (a misbehaving BGP optimizer, for example), the upstream and the peer never receive more than 51 of our prefixes. A scenario injects the flood on `ce1`.
- **I9 (peer misbehaves):** If the peer announces routes it has no right to (a more-specific of our customer's /24 and a third-party /24, with a foreign AS in the path), we accept only the peer's own /24, and the customer never receives the hijacking more-specific. A scenario injects them on `peer1`.

I8 and I9 use the new `inject_routes` failure fault. They make the v1 latent-risk misses (cases 21 and 30) testable: the risk is turned into behavior by making the neighbor actually misbehave.

## How expected verdicts are decided

As in v1: each case's expected verdict is recorded **before anything runs**, by engineering judgment: *would an experienced operator reject this change in review because it causes harm?* It is **not** derived from the intent list above. A harmful change that the intent does not cover is still expected **unsafe**, and if Netdryrun passes it, that is a published loss.

The case files were committed and pushed before any case was run. Before that commit, the edited configs were only checked offline: each edit must match the base config exactly once (`corpus/tools/check_edits.py --corpus v2`), and the edited configs must parse in FRR (`vtysh --dry-run`) with no lab running. Neither check shows how the network behaves.

## Disclosures

- **Same authors.** The Netdryrun maintainers wrote v1, v2, the runner and the product, and they wrote this spec and the cases knowing v1's results. In particular, the I7 sentinel list includes the kind of prefix v1 case 23 used. Case 03 re-expresses case 23 with a prefix on the list (expected to be caught), and case 04 uses a mistyped prefix that is not on the list (expected to be missed).
- **Case 09 re-expresses v1 case 12 with the corrected label.** v1's post-run finding showed that deleting `neighbor ... send-community` is a no-op in FRR, which sends communities by default. Case 09 is therefore labeled safe from what v1 already measured, not from fresh judgment. Case 10 is the genuinely harmful version of the change.
- **The scenarios add time and state.** I8 makes the max-prefix limit trip in every case where it is intact. Each case then waits for the one-minute restart before the recovery checks pass.
