---
title: netdryrun.yml reference
description: Reference for netdryrun.yml. Top-level keys, every check type and key (bgp_session, bgp_prefixes, route, ping), convergence semantics, drivers and protocol names.
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
| `nodes.<node>.driver` | no | detected | Force the driver for a node: `frr` or `srlinux`. See [drivers](#drivers). |

## Keys every check accepts

| Key | Default | Meaning |
|---|---|---|
| `type` | required | `bgp_session`, `bgp_prefixes`, `route` or `ping` |
| `node` | required | Node name from the topology (for example `r1`) |
| `name` | generated | Label used in reports. The default describes the check, for example `r1: BGP session to 10.0.12.2 is established`. |
| `timeout` | top-level `timeout` | Seconds this check may wait to pass. Positive number. |
| `hold` | `--hold` (10) | Seconds a [post-convergence check](#convergence-semantics) must hold. Positive number. |
| `vrf` | `default` | VRF (FRR) or network-instance (SR Linux) to look in |

IP addresses and prefixes are normalized, so `2001:db8:0::1` in YAML matches `2001:db8::1` on the device. Prefixes with host bits set are reduced to the network (`10.0.0.1/24` becomes `10.0.0.0/24`).

## Check types

### bgp_session

A BGP session reaches a state.

| Key | Required | Default | Meaning |
|---|---|---|---|
| `neighbor` | yes | | Neighbor IP address as configured on `node` |
| `state` | no | `established` | One of `idle`, `connect`, `active`, `opensent`, `openconfirm`, `established` (case-insensitive) |

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
- The session must be `established`. Counters reset to 0 when a session drops, so a count from a down session would satisfy `max` by accident; NetDryRun fails the check instead.
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

- **Present** means an *active* route matches: selected and installed on FRR, `active` on SR Linux.
- **Absent** means no matching route at all, active or not. A route that was received but not selected (for example a leaked default losing to a local one) still counts as present, so `present: false` fails. This is how the [failing example](../index.md#a-failing-run) is caught.
- `present: false` makes it a post-convergence check.

```yaml
- type: route
  node: r1
  prefix: 192.168.3.0/24
  protocol: bgp
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

## Convergence semantics

Networks need time to converge, and some checks are trivially true before they do. NetDryRun splits checks into two groups.

**Positive checks** (session `established`, prefix count with only `min`, route present, ping expected to succeed):

- Polled every 3 seconds until they pass on **2 consecutive samples**, or until `timeout` expires.
- A single lucky sample is not enough. If the last sample passed but the streak was too short, the result says "not stable". If the check passed some samples but not consistently, the result says "flapping".

**Post-convergence checks** are the ones that would pass on a network that has not come up yet:

- routes that must be absent (`present: false`)
- pings that must fail (`expect: failure`)
- sessions expected in a state other than `established`
- prefix counts with an upper bound (`max` or `exact`), since 0 prefixes satisfies `max: 10` while BGP is still starting

They run after every positive check has finished plus a settle delay (`--settle`, default 10 seconds; at least 30 seconds if the file has no positive checks, because nothing else has shown that the network converged). Each one must then hold for the hold window (`--hold` or the check's `hold`, default 10 seconds), sampled every 3 seconds. A violation at any sample fails the check immediately.

Prefix counts with an upper bound first wait (up to `timeout`) for the count to enter the range, because counters ramp up, and then must hold.

Results are reported in the order the checks appear in the file.

## Drivers

A driver turns device state into a common shape. NetDryRun detects it from the topology:

- `kind: nokia_srlinux` or `kind: srl` uses `srlinux`
- an image whose name contains `frr` uses `frr`
- anything else is an error unless you set `nodes.<node>.driver`

| Check | FRR | SR Linux |
|---|---|---|
| `bgp_session` | yes | yes |
| `bgp_prefixes` (accepted = received minus rejected by policy) | yes | yes |
| `route` present / absent | yes | yes |
| `ping` success / failure | yes | yes |

| Driver | Source of state |
|---|---|
| FRR | `vtysh -c "show ... json"`; accepted prefixes from `acceptedPrefixCounter` |
| SR Linux | `sr_cli --output-format json "info from state ..."`; accepted = `received-routes` minus `rejected-routes` |

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
