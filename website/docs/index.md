---
title: Fail CI on routing mistakes before they reach production
description: Test a network change in CI with a containerlab lab. Netdryrun boots the topology, waits for convergence, checks BGP, routes and reachability, and fails the job on mistakes.
---

# Fail CI on routing mistakes before they reach production

To test a network change in CI, keep the changed configs and a containerlab topology in Git, describe the expected behavior in a `netdryrun.yml` file, and run `netdryrun run` (or the GitHub Action) on every pull request. Netdryrun deploys the lab, waits for BGP to converge, checks sessions, prefix counts, routes and pings, then destroys the lab. Any failed check exits non-zero and fails the job, with a JSON evidence file showing every command and its raw output.

!!! abstract "What Netdryrun is"
    Netdryrun is an open-source tool that tests network changes in a real virtual lab before they reach production. It boots the topology with containerlab, waits for convergence, checks BGP sessions, prefixes, routes and reachability, and returns a pass/fail verdict with evidence. It runs locally, in GitHub Actions, or as an MCP server for AI agents.

## A failing run

This is the bundled `frr-bgp-broken` example. Router r2 has a bad change: it sends r1 a default route.

![Netdryrun catching a leaked default route that ping and session checks miss](assets/netdryrun-demo.gif)

```text
$ netdryrun run examples/frr-bgp-broken
Deploying lab ndr-frr-broken (3 nodes)...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (6.3s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (2.3s)
  ... (3 more passing checks trimmed)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

The leaked default route was *received but not selected*: r1 kept its own default, so traffic still flowed and the ping passed. A ping test or a config linter would have missed it. Netdryrun counts a route that is in the routing table but not selected as present, so the "must be absent" check fails.

The check that caught it:

```yaml
- type: route        # nothing should send r1 a default route
  node: r1
  prefix: 0.0.0.0/0
  protocol: bgp
  present: false
```

Checks like this one run only after the network has converged and must hold for a time window, so they cannot pass just because BGP has not come up yet. See [convergence semantics](reference/config.md#convergence-semantics).

## Run it in GitHub Actions

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.1.0
        with:
          path: network/        # folder containing netdryrun.yml
```

The action installs containerlab, runs the checks, writes a summary to the job page, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails. Details: [GitHub Action](github-action.md).

## Run it locally

Fastest start on your own topology: `netdryrun record my-lab/topology.clab.yml --deploy` snapshots today's behavior into checks, then `netdryrun run my-lab` tests every change against it.


```bash
pip install netdryrun
netdryrun run path/to/folder    # the folder containing netdryrun.yml
```

Requirements: Linux or WSL2, Docker, containerlab, Python 3.10+. Walkthrough: [Getting started](getting-started.md).

!!! warning "What a lab cannot prove"
    A pass means the change behaved correctly in a lab built from open-source router images (FRR, Nokia SR Linux). That is strong evidence for protocol logic and policy intent. It is not proof of:

    - vendor-specific behavior on the routers you run in production
    - behavior at production scale (full tables, many peers)
    - hardware and ASIC limits
    - timing and convergence at scale

    More on this in [Trust and security](trust.md#what-a-lab-cannot-prove).

## Status

Version 0.1.0, early. Works with FRR and Nokia SR Linux on Linux and WSL2. It covers IPv4/IPv6 unicast BGP, routes and ping. Issues and feedback: [github.com/netdryrun/netdryrun](https://github.com/netdryrun/netdryrun/issues).
