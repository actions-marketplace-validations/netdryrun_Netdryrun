# Verdict Corpus v2 results

Generated 2026-10-27T04:02:42+00:00 with netdryrun 0.2.0, containerlab 0.81.1, FRR quay.io/frrouting/frr:10.4.1, commit `unknown`. Rerun everything with `python corpus/run.py --corpus v2`.

**Conflict of interest:** the Netdryrun maintainers wrote this corpus and the runner. Expected verdicts were committed before any run (see the git history of `corpus/v2/cases/`). Losses are kept and shown at the same size as the catches.

## Summary (18 cases: 11 harmful, 7 safe)

| Strategy | Correct | Harmful changes caught | Approved a bad change | Blocked a good change | Errors |
|---|---|---|---|---|---|
| Ping only | **9/18** | 2/11 | 9 | 0 | 0 |
| All BGP sessions up | **7/18** | 0/11 | 11 | 0 | 0 |
| Netdryrun intent checks | **16/18** | 9/11 | 2 | 0 | 0 |

## Every case

| Case | Category | Expected | Ping only | Sessions up | Netdryrun | What Netdryrun flagged |
|---|---|---|---|---|---|---|
| `01-no-change` [No change (control)](cases/01-no-change.yml) | control | safe | ✅ | ✅ | ✅ | nothing |
| `02-redistribute-connected-pe2` [redistribute connected added on pe2](cases/02-redistribute-connected-pe2.yml) | hygiene | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I6 customer has no BGP route for link 10.0.3.0/30; I6 customer has no BGP route for link 10.0.4.0/30; I6 customer has no BGP route for pe2 loopback |
| `03-test-prefix-left-in-config` [pe1 originates 1.1.1.0/24 left over from a lab test](cases/03-test-prefix-left-in-config.yml) | hijack | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I7 customer has no route for 1.1.1.0/24 |
| `04-redundant-aggregate-typo` [Aggregate added on pe2 for redundancy, mistyped as 192.0.12.0/24](cases/04-redundant-aggregate-typo.yml) | hijack | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |
| `05-customer-max-prefix-removed` [Customer maximum-prefix safety limit removed](cases/05-customer-max-prefix-removed.yml) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | [customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes; [customer floods 200 prefixes] I8 peer still receives at most 51 prefixes |
| `06-peer-import-filter-permit-all` [Peer inbound filter replaced with permit-all](cases/06-peer-import-filter-permit-all.yml) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | [peer announces routes it does not own] I9 pe2 accepts only the peer's own prefix; [peer announces routes it does not own] I9 customer gets no hijacking more-specific; [peer announces routes it does not own] I9 pe1 has no third-party route from the peer |
| `07-customer-adds-prefixes` [Customer announces two more /24s from its /16](cases/07-customer-adds-prefixes.yml) | customer-growth | safe | ✅ | ✅ | ✅ | nothing |
| `08-customer-announces-aggregate` [Customer also announces its covering /16](cases/08-customer-announces-aggregate.yml) | customer-growth | safe | ✅ | ✅ | ✅ | nothing |
| `09-ibgp-send-community-line-removed` [Explicit send-community line removed on the pe1 to pe2 iBGP session](cases/09-ibgp-send-community-line-removed.yml) | vendor-default | safe | ✅ | ✅ | ✅ | nothing |
| `10-ibgp-standard-communities-disabled` [Standard communities explicitly disabled on the pe1 to pe2 iBGP session](cases/10-ibgp-standard-communities-disabled.yml) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I2 peer has customer route; I3 customer reaches peer; I5 peer receives 2 to 51 prefixes from us |
| `11-customer-max-prefix-warning-only` [Customer maximum-prefix changed to warning-only](cases/11-customer-max-prefix-warning-only.yml) | latent-risk | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | [customer floods 200 prefixes] I8 upstream still receives at most 51 prefixes; [customer floods 200 prefixes] I8 peer still receives at most 51 prefixes |
| `12-customer-max-prefix-raised` [Customer maximum-prefix raised from 50 to 100](cases/12-customer-max-prefix-raised.yml) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `13-upstream-routes-tagged-as-customer` [Upstream import policy tags routes with the customer community (copy-paste error)](cases/13-upstream-routes-tagged-as-customer.yml) | route-leak | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I4 no upstream route leaked to peer; I4 no default leaked to peer |
| `14-customer-gets-default-only` [Customer export policy restricted to the default route](cases/14-customer-gets-default-only.yml) | policy-bug | unsafe | ✅ | ❌ approved a bad change | ✅ | I3 customer has upstream route; I3 customer has peer route; I3 customer reaches upstream; I3 customer reaches peer |
| `15-upstream-default-filtered` [Default route from the upstream filtered on import](cases/15-upstream-default-filtered.yml) | policy-bug | unsafe | ❌ approved a bad change | ❌ approved a bad change | ✅ | I3 customer has default |
| `16-customer-session-peer-group` [Customer session moved into a CUSTOMERS peer-group](cases/16-customer-session-peer-group.yml) | refactor | safe | ✅ | ✅ | ✅ | nothing |
| `17-customer-region-community` [Add an informational region community to customer routes](cases/17-customer-region-community.yml) | hygiene | safe | ✅ | ✅ | ✅ | nothing |
| `18-aggregate-discard-route-removed` [Discard route for our aggregate deleted as unused](cases/18-aggregate-discard-route-removed.yml) | hygiene | unsafe | ❌ approved a bad change | ❌ approved a bad change | ❌ approved a bad change | nothing |

## Netdryrun's losses

- **`04-redundant-aggregate-typo` Aggregate added on pe2 for redundancy, mistyped as 192.0.12.0/24** (false pass). Expected to be missed. I7 only spot-checks a few well-known prefixes, and nothing bounds what the customer receives.
- **`18-aggregate-discard-route-removed` Discard route for our aggregate deleted as unused** (false pass). The blackhole static for 192.0.2.0/24 looks unused and is cleaned up. Either the aggregate stops being announced (if BGP requires a matching route), or it is still announced with nothing to absorb traffic for unused addresses in it: that traffic follows the upstream's default straight back to the upstream, a routing loop. Both are harmful.

## Findings after the run

These findings came after the v2 run. The table above is left exactly as pre-registered in commit `322cc4e`; nothing in `corpus/v2/cases/` was edited.

**Run provenance.** `results.json` records the commit as `unknown`: the run used git inside WSL on a Windows git worktree, and that git could not read the worktree. The run started at 04:02:42 UTC, 16 seconds after the pre-registration commit `322cc4e`. `src/` and `corpus/run.py` were not changed during the run. The renderer, the docs and the unit tests were edited during the run, and none of them affect verdicts.

**Case 04 is a real miss, as predicted.** pe2 announced the mistyped 192.0.12.0/24 to pe1 and on to the customer, and no check looked for it. I7 only spot-checks a few well-known prefixes, and nothing bounds what the customer receives. Catching this class needs a check that the customer receives only routes from known origins, or only expected prefixes from our own AS. No such check type exists yet.

**Case 18 is a real miss.** With the discard route deleted, FRR (traditional defaults, no `bgp network import-check`) kept announcing 192.0.2.0/24, so I2 passed. The harm is the routing loop for unused addresses inside the aggregate, which no check probes. A `ping` with `expect: failure` to an unused address in 192.0.2.0/24 from the upstream would not show the loop either, because ping fails both with and without it. Catching it needs a path or traceroute check (TTL exceeded versus a clean discard).

**Ping only's catch of case 14 is partly a lab artifact.** In the lab, the customer's BGP default is not active, because containerlab's management default route outranks it (the spec checks the default with `active: false` for this reason). Once the customer lost its specific routes, its pings had no path at all. A real customer with a working default would still ping, and the ping baseline would pass the change. The result stays as measured.
