---
title: netdryrun.yml reference
description: Reference for netdryrun.yml. Top-level keys, every check type and key (bgp_session, bgp_prefixes, route, bgp_route, ping), convergence semantics, drivers and protocol names.
---

# netdryrun.yml reference

`netdryrun.yml` describes one lab and the behavior you expect from it. Commands accept either the file or the folder that contains it (`netdryrun run network/` reads `network/netdryrun.yml`).

```yaml title="netdryrun.yml"
lab: topology.clab.yml
timeout: 90
nodes:
  r1:
    driver: frr
checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - type: route
    node: r1
    prefix: 0.0.0.0/0
    protocol: bgp
    present: false
```

Validation is strict: unknown keys inside a check, missing required keys, bad IP addresses and bad values are errors (exit code `2`). Run `netdryrun validate` to check a file without starting a lab.

## Top-level keys

| Key | Required | Default | Meaning |
|---|---|---|---|
| `lab` | yes | | Path to the containerlab topology file, relative to `netdryrun.yml`. The topology must have a `name`. |
| `timeout` | no | `120` | Seconds a positive check may wait for convergence. Each check can override it. |
| `checks` | yes | | List of checks. At least one is required. |
| `nodes.<node>.driver` | no | detected | Force the driver for a node: `frr`, `srlinux`, `eos` or `sonic`. See [drivers](#drivers). |
| `nodes.<node>.setup` | no | | Shell commands run inside the node after deploy, before any check. Each is retried every 5 s until it succeeds (the NOS may still be booting), within a shared 300 s budget. For NOSes that are configured after boot, such as SONiC. |

## Keys every check accepts

| Key | Default | Meaning |
|---|---|---|
| `type` | required | `bgp_session`, `bgp_prefixes`, `route`, `bgp_route` or `ping` |
| `node` | required | Node name from the topology (for example `r1`) |
| `name` | generated | Label used in reports. The default describes the check, for example `r1: BGP session to 10.0.12.2 is established`. |
| `timeout` | top-level `timeout` | Seconds this check may wait to pass. Positive number. |
| `hold` | `--hold` (10) | Seconds a [post-convergence check](#convergence-semantics) must hold. Positive number. |
| `vrf` | `default` | VRF (FRR) or network-instance (SR Linux) to look in. Letters, digits and `. _ : -`, at most 64 characters: the name goes into the device's CLI command, so anything else is refused (0.3.1 and later; 0.3.0 did not check it). |

IP addresses and prefixes are normalized, so `2001:db8:0::1` in YAML matches `2001:db8::1` on the device. Prefixes with host bits set are reduced to the network (`10.0.0.1/24` becomes `10.0.0.0/24`).

## Check types

### bgp_session

A BGP session reaches a state.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `neighbor` | yes | | Neighbor IP address as configured on `node` |
| `state` | no | `established` | One of `idle`, `connect`, `active`, `opensent`, `openconfirm`, `established`, or `down` (any state except established). Case-insensitive |

The check fails if the neighbor is not configured. A `state` other than `established` makes it a post-convergence check.

```yaml
- type: bgp_session
  node: r1
  neighbor: 10.0.12.2
```

### bgp_prefixes

The number of prefixes accepted from a neighbor is within a range. Accepted means received minus rejected by import policy.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `neighbor` | yes | | Neighbor IP address |
| `min` | one of `min`, `max`, `exact` | | Lower bound, inclusive |
| `max` | one of `min`, `max`, `exact` | | Upper bound, inclusive |
| `exact` | one of `min`, `max`, `exact` | | Exact count |
| `afi` | no | `ipv4-unicast` | Address family: `ipv4-unicast`, `ipv6-unicast` or `evpn` |

Rules:

- At least one of `min`, `max` or `exact` is required.
- `exact` cannot be combined with `min` or `max`.
- `min` must not be greater than `max`.
- All three are non-negative integers.
- The session must be `established`. Counters reset to 0 when a session drops, so a count from a down session would satisfy `max` by accident; Netdryrun fails the check instead.
- If the session is established but the address family reports nothing, the count is 0.
- A check with `max` or `exact` is a post-convergence check. A check with only `min` is a positive check.

```yaml
- type: bgp_prefixes
  node: r1
  neighbor: 10.0.12.2
  min: 1
  max: 10          # guards against a route leak flooding r1
```

### route

A route is present in (or absent from) the routing table.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `prefix` | yes | | IPv4 or IPv6 prefix |
| `present` | no | `true` | `false` means the route must be absent |
| `protocol` | no | any | Only count routes from this protocol. See [protocol names](#protocol-names). |
| `vrf` | no | `default` | VRF or network-instance |
| `active` | no | `true` | With `present: true`: `false` also accepts a route that is in the table but not selected (for example a BGP default losing to a local one) |

- **Present** means an *active* route matches: selected and installed on FRR, `active` on SR Linux.
- **Absent** means no matching route at all, active or not. A route that was received but not selected (for example a leaked default losing to a local one) still counts as present, so `present: false` fails. This is how the [failing example](../index.md#a-failing-run) is caught.
- `present: false` makes it a post-convergence check.

```yaml
- type: route
  node: r1
  prefix: 192.168.3.0/24
  protocol: bgp
```

### bgp_route

Attributes of the BGP **best path** for a prefix: communities, AS path, local preference, MED, next hop. Many real policy bugs live here: a route that is still present but lost its community, got the wrong local preference, or now goes the long way. `route` reads the routing table; `bgp_route` reads the BGP table.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `prefix` | yes | | IPv4 or IPv6 prefix, matched exactly |
| `communities` | no | | The best path must carry **all** of these. Standard (`'65000:100'`), large (`'65000:1:2'`) or well-known names (`no-export`, `no-advertise`, `no-peer`, `blackhole`, `graceful-shutdown`, `accept-own`, `llgr-stale`, `no-llgr`, `no-export-subconfed`) |
| `without_communities` | no | | The best path must carry **none** of these. Same forms as `communities` |
| `as_path` | no | | Exact AS path, ASNs separated by spaces: `"65002 65003"`. `""` is the empty path of a locally originated route. AS sets are written `{65004,65005}` |
| `as_path_regex` | no | | Python regular expression searched in the AS path string, for example `"^65002 "` (learned from 65002) or `"(^| )65666( |$)"` (passes through 65666). It runs with no time limit, so avoid nested repeats such as `(\d+ ?)+$` that can backtrack for minutes |
| `local_pref` | no | | Exact local preference |
| `med` | no | | Exact MED. A path without MED counts as `0`, as best-path selection treats it by default |
| `next_hop` | no | | Exact next hop address |
| `present` | no | `true` | `false` means no path at all for the prefix in the BGP table, best or not |
| `vrf` | no | `default` | VRF or network-instance |

Rules:

- Without attribute keys, the check passes when a best path exists.
- **Quote communities.** YAML reads some unquoted values as numbers (`65000:10` is a base-60 number to YAML 1.1), so an unquoted community that YAML turns into a number is a config error.
- A community can't be in both `communities` and `without_communities`.
- `present: false` can't be combined with attribute keys. To forbid a community on the best path, use `without_communities`.
- The check fails if there is no path, or no best path (for example when the next hop is unreachable). The failure detail shows what the best path actually carries.
- **Local preference** is the effective value: a path without a LOCAL_PREF attribute (eBGP-learned or local) gets the device's default (FRR and SONiC: `bgp default local-preference`; SR Linux: the neighbor's `local-preference`; Arista EOS reports it directly). The exception is a locally originated path on Arista EOS, which reports no local preference; asserting `local_pref` on it fails with "not set".
- **Next hop** is the address the device reports. For an IPv6 path FRR may list only the link-local next hop.
- `present: false` and `without_communities` make it a post-convergence check: a "must not carry" check could pass on a transient best path before the real one arrives, so it must hold instead.

```yaml
- type: bgp_route         # customer routes are tagged and preferred
  node: r1
  prefix: 192.168.20.0/24
  communities: ["65000:100", no-export]
  local_pref: 200
  as_path: "65020"

- type: bgp_route         # the internal tag must never reach the peer
  node: peer1
  prefix: 192.168.20.0/24
  without_communities: ["65000:666"]
```

### ping

Reachability from a node.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `target` | yes | | Destination IP address |
| `source` | no | | Source IP address (passed as `ping -I`) |
| `expect` | no | `success` | `success` or `failure` |
| `count` | no | `3` | Packets to send. Non-negative integer. |
| `min_replies` | no | `count - 1`, at least 1 | Replies needed for `expect: success`. One lost packet is tolerated by default (first-packet ARP). |
| `vrf` | no | `default` | Runs in the VRF (`ip vrf exec` on FRR) or network-instance namespace (`srbase-<name>` on SR Linux) |

- `expect: failure` passes only with 0 replies, and is a post-convergence check.
- If ping did not run at all (bad source address, missing VRF), the check fails with an error. It never counts as a successful "failure".

```yaml
- type: ping
  node: r1
  source: 192.168.1.1
  target: 192.168.3.1
```

## Failure scenarios

`scenarios:` runs extra checks while something is wrong, then puts it right. Use it to prove the network survives a failure, for example that traffic reroutes when an uplink dies, or that your max-prefix limit and import filters hold when a neighbor misbehaves.

```yaml
scenarios:
  - name: r1-r2 link fails
    link_down: {node: r1, interface: eth1}   # or a list of links
    checks:
      - {type: route, node: r1, prefix: 192.168.2.0/24, protocol: bgp}   # rerouted via r3
      - {type: ping, node: r1, source: 192.168.1.1, target: 192.168.2.1}
      - {type: bgp_session, node: r1, neighbor: 10.0.12.2, state: down}

  - node_isolated: r2          # all of r2's lab links down
    checks:
      - {type: route, node: r1, prefix: 192.168.2.0/24, present: false}

  - name: customer floods us
    inject_routes: {node: ce1, count: 200, from: 10.100.16.0/24}   # ce1 announces 200 extra /24s
    checks:
      - {type: bgp_prefixes, node: up1, neighbor: 10.0.2.1, max: 51}   # the max-prefix limit holds

  - name: peer announces what it does not own
    inject_routes: {node: peer1, prefixes: [10.100.0.0/25, 8.8.8.0/24], as_path: [65400]}
    checks:
      - {type: bgp_prefixes, node: pe2, neighbor: 10.0.4.2, max: 1}   # the import filter holds
      - {type: route, node: ce1, prefix: 10.100.0.0/25, protocol: bgp, present: false}
```

| Key | Meaning |
|---|---|
| `name` | Label shown before each check (default: generated from the faults) |
| `link_down` | `{node, interface}` or a list of them. Interface names as seen inside the node (for example `eth1` on FRR): a Linux interface name of at most 15 letters, digits and `. _ @ -` (checked from 0.3.1). SR Linux links can't be failed yet; fail the FRR or Linux side instead |
| `node_isolated` | A node name (or list): every lab link of that node goes down |
| `inject_routes` | `{node, prefixes}` or `{node, count}` (or a list of them): the node announces extra routes. 0.3.1 and later. See below |
| `checks` | Same check types as the top level, with the same convergence rules |

Scenarios run after the main checks, one at a time. Links and injected routes are always restored afterwards, even if a check fails, and Netdryrun waits for the network to settle before the next scenario. If the network does not recover, the checks that passed before the scenario are reported as failed `[after <scenario>] recovers: ...` checks.

### Injecting routes

New in 0.3.1: Netdryrun 0.3.0 rejects the key as unknown.

`inject_routes` makes a node announce routes it normally doesn't, so you can test what the rest of the network does with them: a customer leaking more-specifics, a peer announcing someone else's prefix, a flood that should trip a max-prefix limit.

| Key | Required | Meaning |
|---|---|---|
| `node` | yes | The node that announces the routes. It must be an FRR node with `router bgp` in the default VRF |
| `prefixes` | one of | A prefix or list of prefixes, IPv4 or IPv6 |
| `count` | one of | Announce this many consecutive prefixes (1 to 10000), starting at `from` |
| `from` | no | First prefix for `count`; its length is used for all of them. Default `100.64.0.0/24` |
| `as_path` | no | List of AS numbers prepended to the injected routes, so they look learned from those networks |

On the node, Netdryrun adds a blackhole static route and a BGP `network` statement per prefix (with `as_path`, through a route-map named `NDR-INJECT`). It applies them with `vtysh -f` and waits until every prefix is in the node's own BGP table before running the scenario's checks. Afterwards it removes exactly what it added and waits until the prefixes are gone. What the node's neighbors do with the routes is up to the policy under test: an outbound filter on the node itself can still stop them.

Limits: only FRR nodes are supported. Any other node is refused before the lab deploys; inject the routes from an FRR neighbor instead. A prefix that is already a `network` statement or a static route on the node is refused, because removing it afterwards would delete real config. IPv6 prefixes need the BGP sessions to carry IPv6 unicast.

## Convergence semantics

Networks need time to converge, and some checks are trivially true before they do. Netdryrun splits checks into two groups.

**Positive checks** (session `established`, prefix count with only `min`, route present, ping expected to succeed):

- Polled every 3 seconds until they pass on **2 consecutive samples**, or until `timeout` expires.
- A single lucky sample is not enough. If the last sample passed but the streak was too short, the result says "not stable". If the check passed some samples but not consistently, the result says "flapping".

**Post-convergence checks** are the ones that would pass on a network that has not come up yet:

- routes that must be absent (`present: false` on `route` or `bgp_route`)
- best paths that must not carry a community (`without_communities`)
- pings that must fail (`expect: failure`)
- sessions expected in a state other than `established`
- prefix counts with an upper bound (`max` or `exact`), since 0 prefixes satisfies `max: 10` while BGP is still starting

They run after every positive check has finished plus a settle delay (`--settle`, default 10 seconds; at least 30 seconds if the file has no positive checks, because nothing else has shown that the network converged). Each one must then hold for the hold window (`--hold` or the check's `hold`, default 10 seconds), sampled every 3 seconds. A violation at any sample fails the check immediately.

Prefix counts with an upper bound first wait (up to `timeout`) for the count to enter the range, because counters ramp up, and then must hold.

Results are reported in the order the checks appear in the file.

## Drivers

A driver turns device state into a common shape. Netdryrun detects it from the topology:

- `kind: nokia_srlinux` or `kind: srl` uses `srlinux`
- `kind: arista_ceos` or `kind: ceos` uses `eos`
- `kind: sonic-vs`, or an image whose name contains `sonic`, uses `sonic`
- an image whose name contains `frr` uses `frr`
- anything else is an error unless you set `nodes.<node>.driver`

| Check | FRR | SR Linux | Arista EOS | SONiC |
|---|---|---|---|---|
| `bgp_session` | yes | yes | yes | yes |
| `bgp_prefixes` (accepted = received minus rejected by policy) | yes | yes | yes | yes |
| `route` present / absent | yes | yes | yes | yes |
| `bgp_route`: communities (standard, large, well-known), AS path, local preference, MED, next hop, absent | yes | yes | yes | yes |
| `ping` success / failure | yes | yes | yes | yes |
| Failure scenarios on the node's own links | yes | not yet (fail the FRR/Linux side instead) | yes | yes |
| `inject_routes` on the node | yes | not yet (inject from an FRR neighbor) | not yet | not yet |
| Tested on a live lab in CI | yes, on every push | yes, on every push | no: parsers tested against output captured from live labs | no: parsers tested against output captured from live labs |

**Received-but-not-selected routes:** on SR Linux and Arista EOS, a BGP route that lost to a static or local route lives only in the BGP table, not the routing table. Both drivers read the BGP table too, so such a route still counts as present for `present: false`.

**SONiC:** `docker-sonic-vs` routes with FRR inside the container, so the `sonic` driver reads state through `vtysh` like the FRR driver. The image boots unconfigured; put interface IPs (`config interface ip add ...`) and BGP (`vtysh -c ...`) in `nodes.<node>.setup`. See `examples/sonic-frr`.

**Arista EOS:** cEOS-lab is free from arista.com (account required) and can't be redistributed. Download it yourself, then `docker import cEOS-lab-<version>.tar ceos:<version>`, and use `kind: arista_ceos` with that image.

| Driver | Source of state |
|---|---|
| FRR | `vtysh -c "show ... json"`; accepted prefixes from `acceptedPrefixCounter`; `bgp_route` from `show bgp <afi> unicast <prefix> json` |
| SR Linux | `sr_cli --output-format json "info from state ..."`; accepted = `received-routes` minus `rejected-routes`; `bgp_route` from the `bgp-rib` local RIB and its `attr-sets` |
| Arista EOS | `Cli -c "show ... \| json"`; `bgp_route` from `show ip bgp <prefix> vrf <vrf>` (the best path is the `active` one) |
| SONiC | the FRR commands, through `vtysh` inside the container |

If a driver can't read a `bgp_route` attribute, the run stops before deploying with "`<key>` is not supported on `<driver>`" (exit code `2`) instead of guessing. Today every driver reads every attribute.

Every command and its raw output is kept in the [JSON report](cli.md#json).

## Protocol names

`protocol` on a route check is compared in lower case with the protocol the device reports, after normalization:

| Use | FRR reports | SR Linux reports |
|---|---|---|
| `bgp` | `bgp` | `bgp` |
| `static` | `static` | `static` |
| `connected` | `connected` | `local` |
| `local` | `local` | `host` |
| `ospf` | `ospf` | `ospfv2` |
| `ospf6` | `ospf6` | `ospfv3` |
| `isis` | `isis` | `isis` |

Other protocol names are passed through in lower case as the device reports them. The failure detail lists the protocols that were seen, which helps when a name does not match.
