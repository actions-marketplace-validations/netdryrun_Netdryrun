---
title: When to use what
description: A neutral comparison of Batfish, pyATS/Genie, containerlab and Netdryrun for network change testing. What each tool is best at and how they combine.
---

# When to use what

Several good open-source tools help you test network changes. They answer different questions and work well together. This page tries to describe each one fairly; if something here is wrong or out of date, please [open an issue](https://github.com/netdryrun/netdryrun/issues).

## The short version

| Tool | Best at | Runs routers? |
|---|---|---|
| [Batfish](https://batfish.org) | Analyzing configs of many vendors without booting anything: reachability, ACLs and firewall rules, routing, differences between two snapshots | No, it models them |
| [pyATS / Genie](https://developer.cisco.com/pyats/) | A full Python test framework with a large library of device parsers, for testing labs and real (including production) devices, with state snapshots and diffs | Works against any reachable device |
| [containerlab](https://containerlab.dev) | Running container-based network labs from a YAML topology, for many network operating systems | Yes, it is the lab |
| Netdryrun™ | Declarative, convergence-aware checks on a containerlab lab, packaged for CI with a pass/fail verdict and evidence | Yes, through containerlab |

## Batfish

Batfish parses device configs and builds a model of the network's control and data plane. Because nothing has to boot, it is fast, covers large networks, and supports configs from many vendors. It can answer broad questions ("can any host in this subnet reach that server?", "what changed between these two snapshots?") that are hard to test by sending packets.

Use it when you want broad, fast analysis on every commit, especially for ACLs, firewall policy and multi-vendor configs that you cannot run in containers.

A model is not the running software, so behavior that depends on the real implementation (timers, convergence order, bugs) is outside what it sees. That is where a lab helps.

## pyATS / Genie

pyATS is a mature Python test framework from Cisco, and Genie adds a large library of parsers and models that turn CLI output into structured data. It can learn the state of a device, take before and after snapshots, and diff them. It works against lab devices and real ones.

Use it when you need deep, programmable testing, broad parser coverage (especially for Cisco platforms), or pre- and post-change checks on production devices.

Netdryrun is much smaller: a YAML file and a GitHub Action, with no test code to write, and it only runs against labs. If you already have pyATS tests, keep them.

## containerlab

containerlab runs network labs from a YAML topology: container-native network operating systems (such as Nokia SR Linux, Arista cEOS, Juniper cRPD, FRR) and, through vrnetlab, many VM-based ones. It handles wiring, management addresses and lifecycle.

Use it whenever you want a real lab on a laptop or a CI runner. Netdryrun does not replace it; Netdryrun drives it.

## Netdryrun

Netdryrun adds a test layer on top of a containerlab lab:

- positive checks wait for convergence and must pass twice in a row
- negative checks (absent routes, failing pings, prefix upper bounds) run only after convergence and must hold
- a route that was received but not selected counts as present
- every run produces one pass/fail result, a CI-friendly exit code, and a JSON evidence file

<!-- facts:when_status -->
It is early (version 0.3.0). Drivers exist for FRR, Nokia SR Linux, SONiC and Arista EOS (bring your own cEOS image), and checks cover BGP sessions, prefix counts, routes, BGP best-path attributes and ping, with link-down and node-isolation failure scenarios.
<!-- /facts:when_status -->
It does not do static analysis, build labs for you, or test production devices.

## How they combine

A reasonable pipeline uses more than one:

1. **Batfish** on every commit for fast, broad config analysis.
2. A **containerlab** topology that mirrors the change.
3. **Netdryrun** in CI to boot that lab, wait for convergence, and gate the merge on runtime behavior.
4. **pyATS / Genie** (or similar) for pre- and post-change checks on the production devices during the change window.

None of these steps proves the change is safe on its own. Each one removes a different class of mistakes.

[Batfish, then Netdryrun](batfish.md) shows steps 1 and 3 together on a small FRR network, with measured times. In that test, Batfish caught two of three bad changes in seconds, before any lab booted; the third depended on an FRR default that only the running routers showed.
