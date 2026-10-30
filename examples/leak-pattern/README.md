# A transit leak that ping can't see

A network learns routes from its upstream provider and, after a policy change, announces them to a settlement-free peer. Every BGP session stays up, every ping still works, and the peer now has a free path to the provider through you.

This is the pattern [RFC 7908](https://www.rfc-editor.org/rfc/rfc7908) calls *Type 3: Leak of Transit-Provider Prefixes to Peer*. The lab reproduces the mechanism (a missing outbound filter), not any specific incident.

## The lab

```text
                     prov (AS 65020)  203.0.113.0/24
                        |  10.0.2.0/30
cust (AS 65010)  --  net (AS 65001)  --  peer (AS 65030)
192.0.2.0/24    10.0.1.0/30   |   10.0.3.0/30    198.51.100.0/24
                          172.16.0.0/24
```

`net` is the network under change. Four FRR 10.4.1 routers; the image is `quay.io/frrouting/frr:10.4.1`.

- [`configs/net.conf`](configs/net.conf) is the correct config. It tags each route by where it was learned (community 65001:300 for customer routes). The route-map `TO-PEER` sends the peer only customer routes and `net`'s own prefix.
- [`configs/net-leaky.conf`](configs/net-leaky.conf) is the same file with one line changed: the peer's outbound policy is `ALLOW-ALL`, as if a refactor dropped the match.

```diff
-  neighbor 10.0.3.2 route-map TO-PEER out
+  neighbor 10.0.3.2 route-map ALLOW-ALL out
```

## Run it

```bash
pip install netdryrun
netdryrun run examples/leak-pattern/netdryrun.yml        # the correct config: PASSED, 7 of 7
netdryrun run examples/leak-pattern/netdryrun-leaky.yml  # the leaky change: FAILED, 5 passed, 2 failed
```

Needs Docker, containerlab and a privileged host (or Codespaces). To look around by hand:

```bash
cd examples/leak-pattern
containerlab deploy -t topology-leaky.clab.yml
docker exec -it clab-ndr-leak-pattern-peer vtysh -c "show ip bgp"
containerlab destroy -t topology-leaky.clab.yml --cleanup
```

## What the checks show

The first five checks (sessions up, the peer reaches the customer by BGP, ping works) pass on both configs. The two that fail on the leaky one:

- `peer` accepts 3 prefixes from `net` instead of exactly 2.
- `peer` has a BGP route to `203.0.113.0/24`, the provider's prefix.

A pass covers only the checks written here. This lab doesn't test RPKI, IRR filtering or max-prefix limits, which are the defences an operator should also have.
