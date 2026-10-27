---
title: FAQ
description: Frequently asked questions about Netdryrun. Does it touch production, what a pass proves, how it differs from Batfish, pyATS and netlab, supported network operating systems, Windows, memory needs, CI time and cost, privacy and license.
---

# FAQ

## Does Netdryrun touch my production network?

No. Netdryrun™ only builds labs with containerlab on the machine where it runs, runs read-only commands inside the lab containers (with `docker exec`), and destroys the lab. It has no command, option or MCP tool that connects to a real device or pushes config anywhere. You apply the change to production yourself, with your normal process, after the test passes.

## What does a pass prove?

A pass means every check in your `netdryrun.yml` held in a lab running real routing software: positive checks reached the expected state within the timeout, and negative checks held for the hold time after convergence. It is strong evidence that the change does what you intended at the protocol and policy level.

It does not prove:

- **anything you did not check.** A pass covers the checks that exist. A leak with no negative check for it passes.
- **vendor or version behavior.** FRR, SR Linux, SONiC VS and cEOS are not your production routers or images.
- **scale, hardware or timing.** A lab has a few nodes and small tables, no ASICs, and different convergence times.

See [what a lab cannot prove](trust.md#what-a-lab-cannot-prove). The [verdict corpus](corpus.md) shows where Netdryrun was right and wrong on 30 realistic changes.

<!-- TODO(v0.3): explain the `inconclusive` status here (a run that could not reach a verdict) once ndr/v03 is merged. -->

## How is it different from Batfish, pyATS or netlab?

- **Batfish** models configs without booting anything. It is fast, covers many vendors and large networks, and answers broad questions. Netdryrun runs the real routing software, so it sees what the implementation actually does, on fewer nodes.
- **pyATS / Genie** is a full Python test framework with many parsers, for labs and production devices. Netdryrun is a YAML file of checks and a CLI, aimed at one job: a pass/fail gate in CI.
- **netlab** builds labs from a short topology description and has its own validation tests. Netdryrun takes a containerlab topology you already have, including one netlab generated.

They work together. See [When to use what](when-to-use-what.md) for a longer, neutral comparison.

## Which network operating systems are supported?

<!-- facts:faq_platforms -->FRR, Nokia SR Linux, SONiC (docker-sonic-vs) and Arista EOS (cEOS, bring your own image)<!-- /facts:faq_platforms -->. Labs can mix them: the examples pair each one with FRR. See [drivers](reference/config.md#drivers) for what each driver supports.

## Why not Cisco or Juniper?

Their lab images are licensed. Netdryrun's CI and examples must run for anyone, so every image they use has to be free to pull: FRR, SR Linux and SONiC VS are. Arista cEOS is free to download with an account but can't be redistributed, so its example needs you to import your own image.

Cisco and Juniper images (for example IOS XRd, Cisco 8000 emulator, cRPD, vJunos) need an account, a license or both, and several are virtual machines that containerlab runs through vrnetlab. Drivers for them are on the roadmap, following the same bring-your-own-image model as cEOS. If you need one, say so in an [issue](https://github.com/netdryrun/netdryrun/issues).

## Does it work on Windows?

Yes, through WSL2. containerlab needs Linux, so install Docker and containerlab inside a WSL2 distribution (Ubuntu 22.04 is what we test on) and run Netdryrun there. Keep labs on the Linux filesystem (`~/...`) rather than under `/mnt/c`: it is faster, and SR Linux cannot save its config on a Windows drive. Netdryrun works around the second problem; see [troubleshooting](troubleshooting.md#sr-linux-fails-on-a-windows-drive-mntc). All the outputs in this documentation were produced on WSL2.

## How much memory and CPU does it need?

Memory used per node once the lab is up, measured with `docker stats` on WSL2 (20 cores, 16 GB):

| Node | Image | Memory |
|---|---|---|
| FRR | `quay.io/frrouting/frr:10.4.1` | 23 to 25 MiB |
| SONiC VS | `docker-sonic-vs:latest` | 302 MiB |
| Arista cEOS | `ceos:4.36.3M` | 903 MiB |
| Nokia SR Linux | `ghcr.io/nokia/srlinux:26.7.2` | 1.9 GB (1,947,377,664 bytes, read from the container's cgroup `memory.current`, because `docker stats` shows 0 for SR Linux) |

CPU is busy only while nodes boot. Once up, FRR and SONiC used about 1% of one core or less; cEOS was using about one full core when measured, shortly after boot.

Plan for the sum of your nodes plus a few hundred MB for Docker and containerlab. A small FRR lab runs on any laptop. A lab with several SR Linux or cEOS nodes needs a machine with 8 GB or more. GitHub-hosted `ubuntu-latest` runners have enough memory for every example.

## How long does a run take, and what does CI cost?

On GitHub-hosted `ubuntu-latest` runners, measured from three CI runs on `main` (2026-10-27):

| CI job | What it does | Time |
|---|---|---|
| `e2e (frr-bgp)` | Install containerlab and Netdryrun, pull FRR, run 6 checks and a link-failure scenario | 100 to 107 s |
| `e2e (srl-frr)` | The same with SR Linux and FRR (the SR Linux image is 3.2 GB) | 88 to 107 s |
| `catches-bad-change` | Run `frr-bgp-broken` and expect it to fail | 54 to 66 s |
| `agent-demo` | Replay the agent demo: two full runs | 82 to 94 s |

The whole CI workflow, with these jobs in parallel, took 2 minutes 10 seconds to 2 minutes 38 seconds in the last ten successful runs.

GitHub Actions minutes are free on public repositories with standard GitHub-hosted runners. On private repositories, each job uses minutes from your plan, rounded up to the whole minute, so a job like `e2e (frr-bgp)` uses 2 minutes. See [GitHub's billing page](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions) for current prices. Netdryrun itself is free.

Local runs are faster once images are pulled; see the times on the [examples page](examples.md).

## Does it collect any data?

No. The CLI, the GitHub Action and the MCP server have no telemetry and don't phone home. Reports are written only to the files you ask for. The one exception is opt-in: `cloud: true` on the GitHub Action uploads the JSON report to Netdryrun Cloud. See [privacy](trust.md#privacy) and the [privacy notice](privacy.md).

## What is the license?

Apache-2.0, for the code. "Netdryrun" and the logo are trademarks: forks are welcome under a different name. See [Trust and security](trust.md#license).

## Where do I get help?

Read [Troubleshooting](troubleshooting.md) first. Then [open an issue](https://github.com/netdryrun/netdryrun/issues) with the JSON report attached. See [Support](support.md).
