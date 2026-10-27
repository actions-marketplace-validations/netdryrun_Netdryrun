---
title: Batfish, then Netdryrun
description: A two-stage gate for network changes. Batfish analyses FRR configs in seconds on every commit, then Netdryrun boots them in a containerlab lab. Measured results, what each stage caught, and how well Batfish parses FRR.
---

# Batfish, then Netdryrun

[Batfish](https://batfish.org) and Netdryrun™ answer different questions. Batfish reads configs and models the network: nothing has to boot, and in the runs below its stage took 2 to 6 seconds. Netdryrun boots the configs in a containerlab lab and checks what the routing software really does. Run Batfish first on every commit, and boot the lab only when it passes.

This page reports one measured run of that pipeline: four versions of a small FRR network, each tested by both stages. The code is in [`examples/batfish-pipeline`](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline).

## The pipeline

The network is the FRR triangle from [`examples/frr-bgp`](examples.md#frr-bgp): three routers, each in its own AS, each announcing one LAN over eBGP.

1. **Batfish** (`batfish_check.py`, 8 checks): every config parses, no undefined references, all six BGP sessions establish, r1's best paths to the two other LANs, no router learns a default route, a traceroute from r1's LAN to r2's LAN, and the best path after the r1-r2 link fails (a forked snapshot with the interface deactivated).
2. **Netdryrun** (`netdryrun.yml`, 9 checks): r1's two BGP sessions, the prefix count from r2, the route to r2's LAN and its best path, a ping, the same default-route guard, and the same link failure.

The two stages state the same intent, as far as each tool can express it.

```yaml title=".github/workflows/network-gate.yml"
name: network change gate
on: [push, pull_request]
permissions:
  contents: read
jobs:
  batfish:
    runs-on: ubuntu-latest
    services:
      batfish:
        image: batfish/batfish
        ports: ["9996:9996", "9997:9997"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install pybatfish
      - name: Wait for the Batfish service
        run: |
          for _ in $(seq 60); do
            python -c 'from pybatfish.client.session import Session; Session(host="localhost").list_networks()' 2>/dev/null && exit 0
            sleep 2
          done
          exit 1
      - run: python examples/batfish-pipeline/batfish_check.py examples/batfish-pipeline/configs

  netdryrun:
    needs: batfish          # boot the lab only if Batfish passed
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.0
        with:
          path: examples/batfish-pipeline
```

The workflow is an example to copy: this repository's CI does not run it. The measurements below come from the equivalent local script, `pipeline.sh`.

## Results

Measured on 2026-10-27 from a fresh clone, following the example's [README](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline#run-it) word for word, on WSL2 (20 cores, 16 GB) with images already pulled: `batfish/batfish` (Batfish 2026.08.27.3685), pybatfish 2026.9.17.3748, Netdryrun 0.3.0 from PyPI, containerlab 0.81.1, FRR 10.4.1. In a separate measurement, the `batfish/batfish` container answered 3.3 s after `docker run`. The Batfish stage includes loading the snapshot; the lab stage includes deploying and destroying the lab. Each change below replaces r2's config; the last column is the command that reproduces the row.

| Change to r2 | Batfish | Netdryrun lab | Who caught it | Reproduce |
|---|---|---|---|---|
| None (baseline) | pass, 6 s | pass, 69 s | Both pass | `pipeline.sh` |
| Adds `default-originate` toward r1 | **fail**, 2 s | **fail**, 68 s | Both; Batfish first | `BOTH=1 pipeline.sh default-leak` |
| Route-map name typo (`ALLOW-AL`) toward r1 | **fail**, 2 s | **fail**, 177 s | Both; Batfish first, but its route model predicts the wrong outcome | `BOTH=1 pipeline.sh route-map-typo` |
| Switches to `frr defaults traditional` and drops the "allow all" route-maps | pass, 2 s | **fail**, 265 s | **Only the lab** | `BOTH=1 pipeline.sh no-policy` |

### Caught by Batfish first: a leaked default route

r2 starts sending r1 a default route. In a 2-second run, Batfish reports that r1 learns `0.0.0.0/0` from r2 and passes it on to r3. The lab finds the same leak on r1 (received but not selected) after about a minute. Stopping at the Batfish stage saves the lab run.

The route-map typo is also caught first: Batfish's `undefinedReferences` question names the missing `ALLOW-AL` and its line. Its routing model, though, still predicts that r1 uses the direct path to r2. FRR denies everything through a route-map that does not exist, so in the lab r1 receives nothing from r2 and reaches r2's LAN through r3. Ping still works; only the best-path check and the prefix count fail. The gate would fail in both stages, but only the lab shows what the network would really do.

### Seen only by the lab: an FRR default

FRR has enabled `bgp ebgp-requires-policy` by default since 7.4 under the `traditional` profile (it is off under `datacenter`). An eBGP neighbor with no inbound and outbound policy then receives nothing and sends nothing, but the session still comes up. In the lab, r2 shows `(Policy) (Policy)` for both neighbors and 0 prefixes each way, and 6 of the 9 checks fail: r2's LAN is unreachable from r1, even after the link-failure scenario.

Batfish passed this change. It accepted `frr defaults traditional` without modelling what that profile implies, and predicted every route as before. When `bgp ebgp-requires-policy` is written out explicitly, Batfish reports it as an unrecognized line rather than applying it.

### Where they agreed

For the r1-r2 link failure, Batfish's forked snapshot predicted the same failover path (AS path `65003 65002` through r3) that the lab measured. In a topology this small, failover did not show any convergence behavior that the model missed.

## What Batfish does that this test does not show

This test uses a small part of Batfish. It also analyses ACLs and firewall rules, searches every packet that could match a rule rather than the few a ping sends, compares two snapshots to report exactly what a change does, scales to networks far larger than a lab can boot, and supports many vendors whose software cannot run in a container. None of that needs a lab, and Netdryrun does none of it.

## How well Batfish parses FRR

Batfish's FRR support is partial, and the way you feed it configs matters:

- **A bare `frr.conf` is detected as Cisco IOS.** On these configs the status was `PARTIALLY_UNRECOGNIZED`: the `frr defaults` line was not recognized, and interfaces were renamed (`eth1` became `Ethernet1`). The BGP answers happened to be right, but FRR syntax was being read with IOS semantics.
- **Batfish's FRR grammar belongs to its Cumulus Linux support.** Wrapped in the "Cumulus concatenated" layout (a hostname line, an interfaces section, a `ports.conf` marker, then `frr.conf`), the same three configs parse as `CUMULUS_CONCATENATED` with status `PASSED`, no warnings, and the lab's interface names. `batfish_check.py` does this wrapping.
- **What is supported is the subset Cumulus used.** In this test, the defaults profile is accepted but not modelled, and `bgp ebgp-requires-policy` is not recognized at all. Make the gate fail on any file that does not parse cleanly (`fileParseStatus`, `parseWarning`), as the example script does.

The commands that reproduce these findings, and the `(Policy)` output from FRR, are in the example's [README](https://github.com/netdryrun/netdryrun/tree/main/examples/batfish-pipeline#reproduce-the-findings).

These findings cover only BGP with route-maps on three FRR routers. Batfish's support for other vendors (Cisco, Juniper, Arista, Palo Alto and more) is much broader and is not tested here.

## Takeaways

- Put Batfish first. It needs no lab, it failed the bad changes in 2 seconds each, it names the file and line, and here it caught two of the three bad changes before any lab booted.
- Keep the lab stage. The change that passed Batfish broke every route through r2, because of a vendor default that the model does not know about.
- Watch for disagreements, not only for failures. On the route-map typo, both stages failed, but Batfish's prediction of the outcome was wrong.

See also [When to use what](when-to-use-what.md) for how Batfish, pyATS/Genie, containerlab and Netdryrun compare.
