# Corpus network intent

The corpus network is a small provider, AS65000, with routers `pe1` and `pe2`. It connects to:

| Neighbor | AS | Relationship | Announces |
|---|---|---|---|
| `ce1` | 65100 | Customer (pays us) | 10.100.0.0/24 |
| `up1` | 65200 | Upstream transit (we pay them) | 203.0.113.0/24 and a default route |
| `peer1` | 65300 | Settlement-free peer | 198.51.100.0/24 |

We originate our own aggregate 192.0.2.0/24.

The written intent, which the NetDryRun checks in `specs/intent.yml` encode:

- **I1:** All four BGP sessions are established.
- **I2:** The customer route and our aggregate reach both the upstream and the peer.
- **I3:** The customer receives the upstream route, the peer route and a default, and can reach both networks.
- **I4:** No route leaks. Routes learned from the upstream or the peer are never announced to the other (and the default never goes to the peer). This is the "valley-free" rule.
- **I5:** We announce exactly two prefixes (the customer's and our aggregate) to the upstream and to the peer.

## How expected verdicts are decided

Each case's expected verdict is recorded **before anything runs**, by engineering judgment: *would an experienced operator reject this change in review because it causes harm?* It is **not** derived from the intent list above.

So a harmful change that the intent doesn't cover (for example, one that silently shifts traffic to a more expensive path) is still expected **unsafe**. If NetDryRun passes it, that is a published **loss**, with a note on which check would have caught it. The results never quietly claim more coverage than the checks have.
