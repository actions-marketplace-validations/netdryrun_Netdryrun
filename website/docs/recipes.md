---
title: Guard recipes and scenarios
description: Copy-paste netdryrun.yml fragments for frequent BGP mistakes (a default route leaked, a prefix flood, link subnets in BGP, a max-prefix limit, communities dropped) and a catalog of failure scenarios (link down, node isolated, a peer sends extra prefixes).
---

# Guard recipes and scenarios

`netdryrun record` writes down what exists. These fragments add what must **never** happen, plus failures the network must survive. Paste them under `checks:` or `scenarios:` in your `netdryrun.yml`, then change the node names, neighbors and prefixes to your lab's.

The node names and addresses are those of the [`frr-bgp` example](examples.md#frr-bgp): three FRR routers in a triangle, r1 (AS 65001, `10.0.12.1` to r2, `10.0.13.1` to r3), r2 (AS 65002) and r3 (AS 65003), each announcing one LAN, `192.168.<n>.0/24`. Every fragment on this page passes `netdryrun validate` when added to [`examples/frr-bgp/netdryrun.yml`](https://github.com/netdryrun/netdryrun/blob/main/examples/frr-bgp/netdryrun.yml). Check yours the same way, without starting a lab:

```bash
netdryrun validate my-lab
```

!!! note "Checked for syntax, not yet for behavior"
    Each fragment passes `validate`. Lab tests that run each guard against a change it must catch are scheduled; until they land, run a guard against a known-bad change in your own lab before you trust it.

Every key used here is in the [netdryrun.yml reference](reference/config.md), which also explains when each check runs. Most guards are [post-convergence checks](reference/config.md#convergence-semantics): they wait until every configured BGP session on their node is up, then must hold for 10 seconds, so they can't pass just because BGP hasn't come up yet.

## Guard recipes

### No default route via BGP

The most common leak: someone adds `default-originate`, or an export filter that matches the static default. The router may not even use the leaked route (it loses to its own default), so sessions, ping and the forwarding path all look unchanged. `route` with `present: false` fails on a BGP path that was received, selected or not.

```yaml title="checks:"
- type: route          # nobody sends r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
```

For IPv6, add the same check for `::/0`. The [`frr-bgp-broken`](examples.md#frr-bgp-broken) example is this check catching a leaked default, and [Ping and "BGP up" passed](posts/ping-missed-the-leak.md) walks through it.

### A prefix-count ceiling

One check per neighbor that catches a leak of *any* prefix, including ones nobody thought to list: a full table, a peer's routes passed to another peer, a redistribution that pulls in more than it should. Set `max` with room for normal growth.

```yaml title="checks:"
- type: bgp_prefixes   # r2 sends r1 between 1 and 10 prefixes
  node: r1
  neighbor: 10.0.12.2
  min: 1
  max: 10
```

The count is of *accepted* prefixes (received minus rejected by import policy), so this also shows a filter that suddenly drops everything (`min`). `record --min-prefixes` writes the `min` side for every neighbor; add `max` by hand.

### No infrastructure or link routes at the edge

`redistribute connected` announces every connected subnet, including the point-to-point links between routers. The LAN arrives and the ping passes, but the link subnets leak too. List the infrastructure prefixes that must stay out of BGP: one check per prefix, because a check matches the prefix you give.

```yaml title="checks:"
- type: route          # the r2-r3 link subnet stays out of BGP
  node: r1
  prefix: 10.0.23.0/30
  protocol: bgp
  present: false
```

The [tutorial](tutorial.md#5-make-a-change-and-run-it) shows this check failing on a `redistribute connected` change while every session, the ping and the prefix-count range pass. Loopbacks and management ranges work the same way.

### Communities preserved, internal tags stripped

A route can arrive with the right prefix and the wrong attributes: a route-map rewrite that drops a customer community, or an internal tag that leaks to a peer. `bgp_route` checks the BGP best path's attributes. Quote communities: YAML reads some unquoted values as numbers.

```yaml title="checks:"
- type: bgp_route      # r2's LAN keeps its community on the way to r1
  node: r1
  prefix: 192.168.2.0/24
  communities: ["65002:100"]

- type: bgp_route      # and never carries the internal blackhole tag
  node: r1
  prefix: 192.168.2.0/24
  without_communities: ["65002:666", blackhole]
```

The bundled `frr-bgp` routers don't set communities, so the first check fails there by design: tag the route on r2 (a route-map with `set community 65002:100` on its export) before you rely on it. `bgp_route` also checks `as_path`, `as_path_regex`, `local_pref`, `med` and `next_hop`; see [bgp_route](reference/config.md#bgp_route).

### Max-prefix holds when a neighbor floods you

A ceiling check says what the network *should* accept. This scenario makes a neighbor actually send too much, so the max-prefix limit in your config is exercised, not just written down. `inject_routes` makes an FRR node announce extra routes for the length of the scenario, then removes them.

Here the config under test has `neighbor 10.0.12.2 maximum-prefix 10` on r1, and r2 floods 50 prefixes. FRR's default reaction is to close the session:

```yaml title="scenarios:"
- name: r2 sends more than the max-prefix limit
  inject_routes: {node: r2, count: 50, from: 10.100.0.0/24}
  checks:
    - type: bgp_session    # the limit tripped and closed the session
      node: r1
      neighbor: 10.0.12.2
      state: down
    - type: route          # r2's LAN is still reachable, through r3
      node: r1
      prefix: 192.168.2.0/24
      protocol: bgp
```

In a triangle, r3 passes the flood on to r1 too, unless r1 also limits r3; the topology decides what your guards must cover. After a session closes on `maximum-prefix`, FRR keeps it down until it is cleared, unless the limit has `restart <minutes>`. Netdryrun checks that the network recovers after every scenario: if the session stays down, the checks that passed before the scenario are reported as failed `[after <scenario>] recovers: ...` checks, and later scenarios are skipped. Give the limit a `restart`, and check how long your lab takes to recover, before you rely on this one.

## Route checks for any protocol

`route` reads the routing table, so its checks work for routes from any protocol, not only BGP: set `protocol` to `ospf`, `ospf6`, `isis`, `static`, `connected` and the other names in [protocol names](reference/config.md#protocol-names).

```yaml title="checks:"
- type: route          # r1 learns r2's loopback from OSPF, not from a static
  node: r1
  prefix: 10.255.0.2/32
  protocol: ospf
```

Netdryrun can't check OSPF or IS-IS adjacencies themselves yet: those checks are planned for 0.5. Until then, a route learned from the protocol is the evidence that the adjacency came up.

## Scenario catalog

`scenarios:` runs extra checks while something is wrong, then restores the network. Each scenario needs at least one fault (`link_down`, `node_isolated` or `inject_routes`) and at least one check. Netdryrun waits until a link fault is visible in BGP before judging the checks; see [scenario timing](reference/config.md#scenario-timing).

### A link fails: traffic reroutes

```yaml title="scenarios:"
- name: r1-r2 link fails
  link_down: {node: r1, interface: eth1}
  checks:
    - type: route          # r2's LAN is still reachable, now via r3
      node: r1
      prefix: 192.168.2.0/24
      protocol: bgp
    - type: ping
      node: r1
      source: 192.168.1.1
      target: 192.168.2.1
    - type: bgp_session    # and the session over the failed link is really down
      node: r1
      neighbor: 10.0.12.2
      state: down
```

Interface names are the ones inside the node (`eth1` on FRR). The [`frr-bgp` example](examples.md#frr-bgp) runs this scenario and also checks that the best path now goes through r3.

### A node is isolated: what depended on it goes away cleanly

```yaml title="scenarios:"
- name: r2 isolated
  node_isolated: r2      # every lab link of r2 goes down
  checks:
    - type: route          # r2's LAN is withdrawn, not left behind
      node: r1
      prefix: 192.168.2.0/24
      present: false
    - type: route          # r3's LAN still reaches r1 directly
      node: r1
      prefix: 192.168.3.0/24
      protocol: bgp
```

### A peer sends prefixes it doesn't own

The import filter, exercised: r2 announces someone else's prefix and a more-specific of space it shouldn't send, with an AS path that makes them look learned from AS 65400. A correct import filter on r1 rejects them.

```yaml title="scenarios:"
- name: r2 announces what it does not own
  inject_routes: {node: r2, prefixes: [8.8.8.0/24, 192.168.3.0/25], as_path: [65400]}
  checks:
    - type: route          # the hijacked prefix doesn't reach r1
      node: r1
      prefix: 8.8.8.0/24
      protocol: bgp
      present: false
    - type: route          # nor the more-specific of r3's LAN
      node: r1
      prefix: 192.168.3.0/25
      protocol: bgp
      present: false
    - type: bgp_prefixes   # r1 still accepts only r2's own prefixes
      node: r1
      neighbor: 10.0.12.2
      max: 10
```

The bundled `frr-bgp` routers accept everything (`route-map ALLOW-ALL`), so this scenario fails there: that is the finding it exists for.

### A customer exceeds its max-prefix

The same as [max-prefix holds](#max-prefix-holds-when-a-neighbor-floods-you), seen from what must keep working: the customer's session closes, and the rest of the network carries on.

```yaml title="scenarios:"
- name: customer r3 floods r1
  inject_routes: {node: r3, count: 200, from: 10.200.0.0/24}
  checks:
    - type: bgp_session    # r1's limit on r3 tripped
      node: r1
      neighbor: 10.0.13.2
      state: down
    - type: bgp_session    # the other session is untouched
      node: r1
      neighbor: 10.0.12.2
    - type: ping           # and r2's LAN still answers
      node: r1
      source: 192.168.1.1
      target: 192.168.2.1
```

`inject_routes` runs on FRR nodes only. To flood a vendor router, inject from an FRR neighbor. `count` takes 1 to 10000 prefixes.

## Next

- [Add Netdryrun to the lab you already have](guides/your-lab.md): record a baseline, then add these guards.
- [netdryrun.yml reference](reference/config.md): every key and the convergence rules.
- [Verdict corpus](corpus.md): 30 realistic BGP changes, and which checks caught each.
