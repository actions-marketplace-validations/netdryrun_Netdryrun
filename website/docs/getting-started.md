---
title: Getting started
description: Install netdryrun, check the requirements (Linux or WSL2, Docker, containerlab, Python 3.10+), and run the three bundled examples with their expected results.
---

# Getting started

## Requirements

| Requirement | Notes |
|---|---|
| Linux or WSL2 | containerlab runs on Linux. On Windows, use WSL2. |
| Docker | The lab nodes are containers. |
| [containerlab](https://containerlab.dev/install/) | netdryrun drives the `containerlab` CLI; it must be on `PATH`. |
| Python 3.10+ | |

containerlab needs root (or a user in the right groups) to create the lab. Run netdryrun the same way you run containerlab on that machine.

!!! note "WSL2 and /mnt/c"
    If your topology lives under `/mnt/...` (a Windows drive), netdryrun keeps containerlab's lab directory on the Linux filesystem (`~/.cache/netdryrun/labs`) unless you set `CLAB_LABDIR_BASE` yourself. SR Linux cannot save its config on a Windows drive.

## Install

```bash
pip install netdryrun
netdryrun --version
```

For the MCP server used by AI agents, install the extra: `pip install "netdryrun[mcp]"`. See [AI agents](ai-agents.md).

## Run the examples

The repository ships three example labs.

```bash
git clone https://github.com/netdryrun/netdryrun && cd netdryrun
netdryrun run examples/frr-bgp          # 3 FRR routers, should pass
netdryrun run examples/srl-frr          # SR Linux + FRR, should pass
netdryrun run examples/frr-bgp-broken   # a bad change, should fail
```

Each run deploys the lab, runs the checks, prints one line per check and destroys the lab. Images are pulled on first use, so the first run takes longer.

### Expected results

| Example | Topology | Checks | Expected | Exit code |
|---|---|---|---|---|
| `examples/frr-bgp` | Triangle of three FRR routers (r1, r2, r3), eBGP | 2 sessions, prefix count 1 to 10, route present via BGP, ping, default route absent | `PASSED: 6 passed, 0 failed` | `0` |
| `examples/srl-frr` | Nokia SR Linux (`srl1`) peering eBGP with FRR (`frr1`) | 2 sessions, a BGP route on each side, a ping in each direction | `PASSED: 6 passed, 0 failed` | `0` |
| `examples/frr-bgp-broken` | Same triangle, but r2 adds `default-originate` toward r1 | Same 6 checks as `frr-bgp` | `FAILED: 5 passed, 1 failed`; the default route check fails | `1` |

The broken example is the one shown on the [home page](index.md#a-failing-run). r1 receives the leaked default route but does not select it, so the ping still works. The route check catches it because a received-but-not-selected route counts as present.

SR Linux takes longer to boot, so `examples/srl-frr` sets `timeout: 120`.

## Write checks for your own lab

Put a `netdryrun.yml` next to your containerlab topology:

```yaml title="netdryrun.yml"
lab: topology.clab.yml      # your containerlab topology
timeout: 90                 # seconds a positive check may wait for convergence

checks:
  - type: bgp_session
    node: r1
    neighbor: 10.0.12.2
  - type: route
    node: r1
    prefix: 192.168.3.0/24
    protocol: bgp
  - type: ping
    node: r1
    source: 192.168.1.1
    target: 192.168.3.1
```

Check the file without starting anything, then run it:

```bash
netdryrun validate .
netdryrun run .
```

To debug a failing run, keep the lab up with `--keep` (or `--keep-on-failure`), inspect the routers, and rerun the checks against the running lab with `netdryrun check .`. Destroy it afterwards with `containerlab destroy -t topology.clab.yml --cleanup`.

Next: the [netdryrun.yml reference](reference/config.md) and the [CLI reference](reference/cli.md).
