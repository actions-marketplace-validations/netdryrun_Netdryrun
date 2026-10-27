---
title: Network Change Verdict Corpus
description: 30 realistic BGP changes with expected verdicts committed before any run, tested with ping-only checks, session-only checks and Netdryrun intent checks in a real containerlab lab. Losses published.
---

# Network Change Verdict Corpus

How much does a typical "ping after the change" test miss? This corpus answers that with data anyone can rerun.

## Method

- **The network:** a small provider (AS65000, two routers) with a customer, an upstream transit and a settlement-free peer, running FRR in containerlab. Its written intent is in [INTENT.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/INTENT.md).
- **The changes:** 30 realistic edits ([cases](https://github.com/netdryrun/netdryrun/tree/main/corpus/cases)): route leaks, filter typos, mass withdrawals, fat-fingered ASNs, latent risks, and safe changes that must not be blocked.
- **Pre-registered verdicts:** each case's expected verdict (would an experienced operator reject it?) was **committed to git before any run**. Verdicts are never edited afterwards; findings after the run are listed separately below.
- **Three strategies, same running lab per case:**
    1. **Ping only:** the customer pings the upstream and the peer.
    2. **All BGP sessions up:** every session established.
    3. **Netdryrun™ intent checks:** one [intent spec](https://github.com/netdryrun/netdryrun/blob/main/corpus/specs/intent.yml), written once and used unchanged for every case, so it can't be tuned to win.
- **Rerun it:** `python corpus/run.py` on any Linux or WSL2 machine with Docker and containerlab.
- **Rerun it on GitHub's machines:** fork the repository, then run the [Reproduce corpus](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/reproduce-corpus.yml) workflow from your fork's Actions tab. It installs containerlab 0.81.1 and Netdryrun on a GitHub-hosted runner, runs every case, uploads `results.json`, `RESULTS.md` and the run log as artifacts, and lists every verdict that differs from the committed [`results.json`](https://github.com/netdryrun/netdryrun/blob/main/corpus/results/results.json) in the run summary.

## Results

<!-- RESULTS -->

Generated 2026-10-26T21:43:03+00:00 with netdryrun 0.2.0, containerlab 0.81.1, FRR quay.io/frrouting/frr:10.4.1, commit `ec23379`. Rerun everything with `python corpus/run.py`.

**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. Expected verdicts were committed before any run (see the git history of [`corpus/cases/`](https://github.com/netdryrun/netdryrun/tree/main/corpus/cases)). Losses are kept and shown at the same size as the catches.

## Summary (30 cases: 19 harmful, 11 safe)

| Strategy | Correct | Harmful changes caught | Approved a bad change | Blocked a good change | Errors |
|---|---|---|---|---|---|
| Ping only | **20/30** | 9/19 | 10 | 0 | 0 |
| All BGP sessions up | **15/30** | 4/19 | 15 | 0 | 0 |
| Netdryrun intent checks | **24/30** | 14/19 | 5 | 1 | 0 |

## Every case

| Case | Category | Expected | Ping only | Sessions up | Netdryrun | What Netdryrun flagged |
|---|---|---|---|---|---|---|
| `01-no-change` [No change (control)](corpus/01-no-change.md) | control | safe | ✅ | ✅ | ✅ | nothing |
| `02-med-to-upstream` [Set MED on routes sent to the upstream](corpus/02-med-to-upstream.md) | traffic-engineering | safe | ✅ | ✅ | ✅ | nothing |
| `03-prepend-to-peer` [Prepend our AS twice toward the peer](corpus/03-prepend-to-peer.md) | traffic-engineering | safe | ✅ | ✅ | ✅ | nothing |
| `04-tag-community-upstream` [Tag our aggregate with an informational community toward the upstream](corpus/04-tag-community-upstream.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `05-description-only` [Change an interface description](corpus/05-description-only.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `06-customer-adds-prefix` [Customer announces a second allowed /24](corpus/06-customer-adds-prefix.md) | customer-growth | safe | ✅ | ✅ | ⚠️ blocked a good change | I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `07-tighten-max-prefix` [Lower the customer maximum-prefix from 100 to 50](corpus/07-tighten-max-prefix.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `08-upstream-timers` [Shorten BGP timers toward the upstream](corpus/08-upstream-timers.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `09-customer-localpref` [Lower customer local-preference from 300 to 250](corpus/09-customer-localpref.md) | traffic-engineering | safe | ✅ | ✅ | ✅ | nothing |
| `10-transit-export-filter-removed` [Upstream export filter replaced with permit-all](corpus/10-transit-export-filter-removed.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no peer route leaked to upstream; I5 upstream receives exactly our 2 prefixes |
| `11-peer-export-filter-removed` [Peer export filter replaced with permit-all](corpus/11-peer-export-filter-removed.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no upstream route leaked to peer; I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `12-ibgp-send-community-dropped` [send-community removed on the pe1 to pe2 iBGP session](corpus/12-ibgp-send-community-dropped.md) | policy-bug | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `13-upstream-asn-typo` [Typo in the upstream's ASN (65020 instead of 65200)](corpus/13-upstream-asn-typo.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe1-up1 session up; I2 upstream has customer route; I2 upstream has our aggregate; I3 customer has upstream route; I3 customer has default; I3 customer reaches upstream; I5 upstream receives exactly our 2 prefixes |
| `14-peer-session-shutdown` [Peer session administratively shut down](corpus/14-peer-session-shutdown.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe2-peer1 session up; I2 peer has customer route; I2 peer has our aggregate; I3 customer has peer route; I3 customer reaches peer; I5 peer receives exactly our 2 prefixes |
| `15-customer-filter-too-strict` [Customer prefix-list typo rejects the customer's /24](corpus/15-customer-filter-too-strict.md) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 upstream has customer route; I2 peer has customer route; I3 customer reaches upstream; I3 customer reaches peer; I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `16-mass-withdrawal` [Upstream export policy denies everything](corpus/16-mass-withdrawal.md) | withdrawal | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 upstream has customer route; I2 upstream has our aggregate; I3 customer reaches upstream; I5 upstream receives exactly our 2 prefixes |
| `17-default-leaked-to-peer` [default-originate configured toward the peer](corpus/17-default-leaked-to-peer.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `18-redistribute-connected` [redistribute connected added on pe1](corpus/18-redistribute-connected.md) | hygiene | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `19-nexthop-self-removed` [next-hop-self removed on pe2 toward pe1](corpus/19-nexthop-self-removed.md) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I3 customer reaches peer |
| `20-ibgp-shutdown` [iBGP session between pe1 and pe2 shut down](corpus/20-ibgp-shutdown.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe1-pe2 iBGP up; I2 peer has customer route; I2 peer has our aggregate; I3 customer has peer route; I3 customer reaches peer; I5 peer receives exactly our 2 prefixes |
| `21-customer-max-prefix-removed` [Customer maximum-prefix safety limit removed](corpus/21-customer-max-prefix-removed.md) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `22-customer-leaks-third-party` [Customer announces someone else's prefix; our filter blocks it](corpus/22-customer-leaks-third-party.md) | filter-works | safe | ✅ | ✅ | ✅ | nothing |
| `23-fat-finger-third-party-origin` [pe1 accidentally originates 8.8.8.0/24](corpus/23-fat-finger-third-party-origin.md) | hijack | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `24-customer-blackholed` [Static discard route for the customer prefix on pe1](corpus/24-customer-blackholed.md) | fat-finger | unsafe | ✅ | ❌ approved a bad change | ✅ | I3 customer reaches upstream; I3 customer reaches peer |
| `25-aggregate-typo` [Aggregate network statement typo (192.0.3.0/24)](corpus/25-aggregate-typo.md) | fat-finger | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I2 upstream has our aggregate; I2 peer has our aggregate; I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `26-route-map-order-bug` [A permit-everything clause inserted before the peer export filter](corpus/26-route-map-order-bug.md) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no upstream route leaked to peer; I4 no default leaked to peer; I5 peer receives exactly our 2 prefixes |
| `27-local-asn-typo` [pe2 configured with the wrong local ASN](corpus/27-local-asn-typo.md) | fat-finger | unsafe | ✅ | ✅ | ✅ | I1 pe1-pe2 iBGP up; I1 pe2-peer1 session up; I2 peer has customer route; I2 peer has our aggregate; I3 customer has peer route; I3 customer reaches peer; I5 peer receives exactly our 2 prefixes |
| `28-customer-import-policy-removed` [Customer inbound route-map removed](corpus/28-customer-import-policy-removed.md) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 upstream has customer route; I2 peer has customer route; I3 customer reaches upstream; I3 customer reaches peer; I5 upstream receives exactly our 2 prefixes; I5 peer receives exactly our 2 prefixes |
| `29-graceful-restart` [Enable BGP graceful restart on pe1](corpus/29-graceful-restart.md) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `30-peer-import-filter-removed` [Peer inbound filter replaced with permit-all](corpus/30-peer-import-filter-removed.md) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |

## Netdryrun's losses

- **`06-customer-adds-prefix` Customer announces a second allowed /24** (false block). Normal customer growth inside the registered range.
- **`12-ibgp-send-community-dropped` send-community removed on the pe1 to pe2 iBGP session** (false pass). A common mistake when rebuilding iBGP sessions.
- **`18-redistribute-connected` redistribute connected added on pe1** (false pass). Not covered by the intent spec, which has no check for infrastructure routes at the customer.
- **`21-customer-max-prefix-removed` Customer maximum-prefix safety limit removed** (false pass). Latent risk: no steady-state check can see it until the customer actually leaks. Catching it needs a failure-injection scenario (the customer sends many prefixes), planned for a later release.
- **`23-fat-finger-third-party-origin` pe1 accidentally originates 8.8.8.0/24** (false pass). Not covered by the intent spec, which has no check for unexpected routes at the customer.
- **`30-peer-import-filter-removed` Peer inbound filter replaced with permit-all** (false pass). Latent risk: invisible in steady state until the peer misbehaves. Needs a failure-injection scenario.

## Findings after the run

These findings came after the run. The table above is left exactly as pre-registered; nothing in [`corpus/cases/`](https://github.com/netdryrun/netdryrun/tree/main/corpus/cases) was edited.

**Case 12 was labeled wrong.** The case expected that removing `neighbor 10.0.3.2 send-community` on pe1 stops pe2 from seeing the customer community. In FRR (verified on 10.4.1) communities are sent to every neighbor by default, so deleting the explicit line is a no-op: `show running-config` no longer shows it, but pe1 still advertises `10.100.0.0/24` to pe2 with community `65000:100`, and pe2 still matches it (`show bgp ipv4 unicast community 65000:100` lists the route). Reproduce with `scripts/corpus_case12_verify.sh`. The change is actually safe, so all three strategies answered case 12 correctly. With that one label corrected the scores would be: ping only 21/30, sessions up 16/30, Netdryrun 25/30. The headline numbers stay at the pre-registered values. The mistake would have been real on platforms that do not send communities by default (Cisco IOS, for example); a vendor-specific version of this case belongs in a future corpus.

**Cases 18, 23, 21 and 30 are real misses.** 18 and 23 are gaps in the intent spec (no check for unexpected routes reaching the customer or the upstream). 21 and 30 are latent risks that no steady-state check can see; they need a failure-injection scenario where the customer or peer actually misbehaves. These stay as losses.
