---
title: verify (0.4, FRR only)
description: netdryrun verify compares a lab before and after a change. You declare what the change is meant to do; every other difference in routing behavior fails. Intent file, snapshot, verdicts and the netdryrun.verify/v1 report.
---

# verify

!!! note "0.4, FRR only"
    `netdryrun verify` is new in 0.4 and is not released yet. It snapshots FRR nodes only; SR Linux, SONiC and Arista EOS follow. A topology with a node of another kind is refused (exit code `2`).

Checks test what someone thought of. `verify` inverts that: **you declare what the change is meant to do, and every other difference in the network's behavior fails.**

```text
netdryrun verify topology.clab.yml --before <dir|git-ref> --after <dir|git-ref> --intent intent.yml [--json report.json]
```

It deploys the lab with the *before* configs, waits for a stable snapshot, destroys the lab, then does the same with the *after* configs (and runs the standing guards on that lab). Then it compares the two snapshots and matches every difference against the intent. Two cold boots: about 2 × 60 to 120 seconds.

## The verdict

| Status | Verdict | Exit code | Meaning |
|---|---|---|---|
| `matched` | `INTENT MATCHED` | `0` | Every difference is declared, and every declaration happened. |
| `no_change` | `NO BEHAVIOR CHANGE` | `0` | The snapshots are identical and the intent declares nothing. |
| `failed` | `UNDECLARED CHANGES: DO NOT APPLY` | `1` | A difference nobody declared, a declared change that didn't happen, or a standing guard that failed (`failed_because` says which). |
| `error` | `ERROR: NO VERDICT` | `2` | A bad intent, a different topology, a side that can't be read, an unreadable snapshot, or a lab problem. "Couldn't read" is never "nothing changed". |
| `inconclusive` | `INCONCLUSIVE` | `3` | A lab's state never stopped moving within `--timeout`. Retry at most once, then escalate: this says nothing about the change. |
| `unhealthy_baseline` | `INCONCLUSIVE: UNHEALTHY BASELINE` | `3` | BGP sessions are down in the *before* lab. Fix the baseline, or pass `--allow-unhealthy-baseline` to compare anyway. |

**Explained is not the same as safe.** The report echoes the declared intent at the top, for a human to review: an intent that declares a leak explains the leak. `verify` never prints `SAFE TO PROCEED`. A verdict covers the observed control-plane state of this lab (sessions, RIB, BGP paths and advertisements), nothing else.

**The intent must come from outside the change**: the ticket, the operator, or the base branch. A pass is never earned by copying the undeclared items into the intent.

## Options

| Option | Default | |
|---|---|---|
| `--before`, `--after` | required | One side each: a git ref or a directory. A **git ref** is the repository's whole tree at that ref, and the topology file in it must be byte-identical to the one given (exit code `2` otherwise: verify compares configs on one topology). A **directory** stands for the folder that holds the topology and every file it binds (for `lab/topo/t.clab.yml` binding `../configs/r1.conf`, a copy of `lab/`, with `configs/r1.conf` in it). A directory wins over a ref of the same name. See [How each side is built](#how-each-side-is-built). |
| `--intent` | required | The intent file. |
| `--json FILE` | | Write the `netdryrun.verify/v1` report. |
| `--guards FILE` | see below | The standing guards (a `netdryrun.yml`), run on the *after* lab; they must pass. Its `nodes:` settings (`driver`, `setup`) apply to both labs. See [Standing guards](#standing-guards). |
| `--config-dir DIR` | | With directory sides: the folder each directory stands for, relative to the topology (for example `configs`), when the directories hold only that folder. Every bind must then resolve inside it. With a git ref, it is only checked to exist in the ref. |
| `--unobserved NODE` | | A node without a routing stack (a host). Repeat for several. A node verify can't classify is an error, never silently skipped. Bridges are never observed. |
| `--settle` | `15` | Seconds between the two snapshots that must be identical. |
| `--timeout` | `300` | Seconds to reach a stable snapshot, per lab. |
| `--hold` | `10` | The standing guards' hold window. |
| `--allow-unhealthy-baseline` | | Compare even when sessions are down in the *before* lab. |
| `--keep` | | Leave the *after* lab running, to run the `next_diagnostic` commands. |

### Standing guards

The standing guards catch what an intent can't: an intent that declares a leak explains the leak, and only a guard from the base branch fails it. They are read from the *before* side, never from the change:

| `--before` | `--guards` | Guards used | `guards_source` |
|---|---|---|---|
| git ref | not given | the `netdryrun.yml` next to the topology in that ref, when one exists | `before-ref` (or `none`) |
| git ref | given | that path, read from the ref (exit code `2` if it isn't there) | `before-ref` |
| directory | not given | none: a `netdryrun.yml` in the directory is not used | `none` |
| directory | given | that path | `explicit` |

With no guards, the report's `warnings` and the verdict line say "no standing guards ran".

### How each side is built

Each side is built in its own temporary folder, never shared with the other side or with your working tree: the whole repository tree at the ref (`git archive`), or the whole directory. Every bind and `startup-config` of the topology is then resolved inside that side's tree, the way containerlab resolves it: relative to the topology's folder, with `${VAR}`, `~`, `..` and symlinks followed.

- **A bind that resolves outside the side's tree is an error** (exit code `2`): an absolute path, `~/...`, a variable pointing elsewhere, or a symlink leading out would be the same file on both sides.
- A bound file missing from a side is an error. With a git ref, a bound file left out of `git archive` by `export-ignore` in `.gitattributes` is an error too, and the message says so.
- **Self-check before booting:** verify hashes every bound file on each side, checks that it holds that side's own bytes, and prints which bound files differ between the sides. If the sides differ in bound files but every bound file hashes the same in the two lab folders, it stops with "both sides resolved to the same configs" (exit code `2`).

## The intent file

One line per prefix or session, so a set of related differences is one line. A line without `vrf:` means the default VRF only.

```yaml
intent:
  - prefix: 10.101.0.0/24              # the customer's new block
    appears_on: [edge1, up1, peer1]
  - prefix: 203.0.113.0/24
    best_path_on: edge1
    to: {local_pref: 200}
  - session: {node: edge1, neighbor: 10.0.9.2}
    goes: down
  - prefix: 192.0.2.128/25
    disappears_from: [cust1]
allow_anywhere: ["10.200.*.0/24"]
```

`intent: []` declares that nothing changes. A file without `intent:`, an unknown key, a wrong type, a prefix with host bits, two lines about the same route on the same node, or a node that is not in the topology is an error (exit code `2`).

### appears_on

The route is absent on each listed node before (no RIB entry, BGP path or received route), and after the change it is **selected and installed in the FIB** (`state: installed`, the default). `state: selected` accepts a selected route that isn't in the FIB; `state: received` expects it received but not selected.

The report shows, per node, where the new route was learned from, its next hop and AS path. `with:` pins any of them:

```yaml
intent:
  - prefix: 10.101.0.0/24
    appears_on: [up1]
    with: {from: 10.0.2.1, next_hop: 10.0.2.1, as_path: "65000 65101", protocol: bgp}
```

`with:` accepts `from`, `next_hop`, `as_path`, `origin`, `local_pref`, `med`, `weight`, `communities`, `ext_communities`, `large_communities`, `cluster_list`, `originator_id`, `protocol`, `distance` and `metric`. Each value must equal exactly; communities are the exact set.

It explains every new item for that prefix on the listed nodes, and every advertisement of the prefix *to* a listed node. An advertisement to any other neighbor, inside or outside the lab, needs its own line (see [advertisement](#advertisement)). Best-path changes on routes that already existed always need their own line.

### disappears_from

The route was **selected** on each listed node before, and after the change it has no RIB entry and no BGP path there. It explains those removals and the withdrawn advertisements to the listed nodes.

A route that was only received (kept by `soft-reconfiguration inbound`, not selected) is a different kind of difference. Removing `soft-reconfiguration inbound` makes those routes vanish, and that is a difference too. Declare it with `including_received_only: true`, which also accepts a route that was received-only before and requires that nothing of it is left.

### best_path_on

```yaml
intent:
  - prefix: 203.0.113.0/24
    best_path_on: edge1
    to: {local_pref: 200}
```

One meaning: **every listed value must equal exactly after the change, and every attribute not listed stays frozen.** If the winner changes to another neighbor's path, `from`, `next_hop` and the AS path change too, and each must be listed. At least one listed value must actually change. `to:` accepts `from`, `next_hop`, `as_path`, `origin`, `local_pref`, `med`, `weight`, `communities`, `ext_communities`, `large_communities`, `cluster_list` and `originator_id`.

It explains, on that node: the best flag moving between paths; changes to the new best path in the listed attributes only, to exactly the declared values (every other path, the old best included, stays frozen apart from its best flag); the BGP RIB entry's next hops (when `next_hop` is listed) or metric (when `med` is); and advertisements of the prefix, by the node or to it, that differ only in listed attributes and carry the new best path's values. A downstream node whose best path changes needs its own line. A lost backup path is never explained by a best-path line.

### session ... goes: down

```yaml
intent:
  - session: {node: edge1, neighbor: 10.0.9.2, afi: ipv4-unicast}
    goes: down
```

The session was established before and isn't after (or is gone). It covers both ends of that one session when both are lab nodes, and **only the routes learned over it**: the paths, received routes and advertisements over the session in its address family, and the RIB entries of prefixes that were learned only over it and are now gone. The report lists them. A failover to a backup path is a best-path change on that node and needs its own line; so does a route disappearing from another node. `afi:` is required when the session carries several address families (one line per family).

### advertisement

What one node advertises to one neighbor, including neighbors outside the lab: an outbound prepend, a `no-export`, a new advertisement toward a transit.

```yaml
intent:
  - prefix: 192.0.2.0/24
    advertisement: {node: edge1, neighbor: 198.51.100.9}
    to: {as_path: "65000 65000"}       # or: goes: added | removed
```

`to:` follows the `best_path_on` rule (listed exact, the rest frozen); `from` can't be set.

`goes: added` has an attribute limit too. **Without `with:`**, the new advertisement must carry the node's own best path for the prefix: no outbound rewrite. Its AS path, origin, MED, communities (standard, extended and large) and, where it is sent, local preference must equal the best path's. **With `with:`**, the listed attributes must equal the given values, and the rest still equal the best path's:

```yaml
intent:
  - prefix: 10.100.0.0/24
    advertisement: {node: edge1, neighbor: 198.51.100.9}
    goes: added
    with: {as_path: "65101 65101 65101", communities: [no-export]}   # an outbound prepend and no-export
```

`with:` accepts the `to:` attributes and goes with `goes: added` only. A node without a BGP best path for the prefix can't satisfy `goes: added`.

### allow_anywhere

```yaml
intent: []
allow_anywhere: ["10.200.*.0/24", {prefix: 10.9.0.0/16, vrf: cust}]
```

Accepts every difference for the listed prefixes, on every node: churn you accept. An entry is an exact prefix, or a glob:

- `*` stands for **one whole octet** (IPv4) or **one whole hextet** (IPv6), never part of one and never across octets. There are no other wildcards.
- **The prefix length is always explicit** and matched exactly: `10.200.*.0/24` matches `10.200.7.0/24`, not `10.200.7.0/25`.
- **At most /16 of wildcard reach for IPv4 and /48 for IPv6:** the first two octets (three hextets) are written literally. `10.200.*.0/24` and `2001:db8:1:*::/64` are accepted; `10.*.0.0/16`, `10.*/*` and `2001:db8:*::/48` are errors (exit code `2`).

It never matches by containment: `10.0.0.0/8` doesn't cover `10.1.0.0/16`. The report lists every route each entry explained (node, VRF and prefix, under `allowed[].routes`) and every item. Sessions are never covered.

`allow_anywhere` weakens the verdict, and every report that uses it carries a warning: a change that adds or widens it should need a second approver (CODEOWNERS). The CLI can't enforce that.

## What is compared: the snapshot

After convergence, for every FRR node, in every VRF:

- **BGP sessions**: (neighbor, VRF) → established or not, ASNs, address families, local address. The raw FSM state (`active`, `connect`, `idle`) is kept in the evidence but never compared: a session going from `active` to `idle` is no change. Prefix counts are derived and never matched on their own.
- **Routes, every protocol** (`kernel`, `connected`, `local`, `static`, `ospf`, `isis`, `bgp` and the rest): (VRF, AFI, SAFI, prefix, protocol) → selected or not, installed in the FIB or not, administrative distance, metric (the OSPF cost, for example), and the next hops with their resolution (recursive next hops keep the next hops that resolve them; IPv6 link-local next hops keep their interface).
- **Every BGP path per prefix**, not only the best: (neighbor or `local`, add-path ID) → best, multipath, valid, origin, AS path, next hops (accessible, IGP metric), local preference, MED, weight, standard, extended and large communities, cluster list, originator ID, atomic aggregate, aggregator.
- **Adj-RIB-Out per session**: what each node advertises to each established neighbor, with the advertised attributes, including neighbors that aren't lab nodes.
- **Received routes before inbound policy**, where `soft-reconfiguration inbound` keeps them.

Normalisation: AS_SEQUENCE order is kept and AS_SET is a sorted set; ASNs are asplain; well-known communities have one form (`no-export` is `65535:65281`); ECMP next-hop sets are compared as sets; absent attributes (MED, local preference) are compared as parsed, never replaced by defaults. Uptimes, timers, counters, table versions and interface indexes are never compared.

Strict reading: verify validates the device output against what it knows. An unknown field, a missing field, a VRF missing from one output, an address family verify doesn't snapshot (EVPN, VPN, labeled unicast) or an unnumbered BGP neighbor is an error (exit code `2`), never a smaller snapshot. The raw output of every command is kept in the report's evidence.

FRR commands: `show vrf`, `show bgp vrf all neighbors json`, `show ip route vrf all json`, `show ipv6 route vrf all json`, `show bgp vrf all ipv4|ipv6 unicast detail json`, and per established session `show bgp [vrf V] ipv4|ipv6 unicast neighbors N advertised-routes detail json` (plus `received-routes` where soft reconfiguration is on).

### Convergence

A snapshot is taken when two full snapshots `--settle` seconds apart are identical: every session established or stably not, prefix counts stable, every route and path unchanged, and every node's RIB populated. A command that fails while daemons start is retried until `--timeout`; then the snapshot is unreadable (exit code `2`). If the snapshots never match within `--timeout`, the result is `inconclusive`, naming what kept moving.

## The report: netdryrun.verify/v1

JSON Schema: [verify-v1.json](https://netdryrun.com/schemas/verify-v1.json).

```json
{"schema": "netdryrun.verify/v1", "verdict": "UNDECLARED CHANGES: DO NOT APPLY", "status": "failed",
 "intent": {"source": "intent.yml", "supplied_by": "cli", "lines": ["10.101.0.0/24 appears on up1, peer1"]},
 "failed_because": ["undeclared"],
 "undeclared": [{"kind": "rib", "node": "edge1", "vrf": "default", "afi": "ipv4", "safi": "unicast",
                 "prefix": "10.101.0.0/24", "protocol": "bgp", "change": "added",
                 "route_before": "absent", "route_after": "selected and in the FIB",
                 "summary": "edge1 10.101.0.0/24 [bgp]: added",
                 "next_diagnostic": "docker exec clab-ndr-agent-demo-edge1 vtysh -c 'show ip route 10.101.0.0/24'"}],
 "not_happened": [], "declared": [], "allowed": [], "guards": null,
 "evidence": {"before": {"schema": "netdryrun.snapshot/v1"}, "after": {"schema": "netdryrun.snapshot/v1"}}}
```

(Abridged: every item also has `fields`, `before` and `after`, and the report has `run_id`, `warnings`, `baseline`, `timings` and more.) Undeclared items come first; each has one `next_diagnostic`, a read-only command for its node (run it on a lab kept with `--keep`). `not_happened` lists every declared change that didn't happen, with the reason. `declared` lists what each line explained.

## Not in 0.4

Topology changes; SR Linux, SONiC and Arista EOS nodes; EVPN, VPN and labeled-unicast address families; unnumbered BGP sessions; the data plane beyond the standing guards' ping checks; the MCP tool and the GitHub Action's `mode: verify` (next).
