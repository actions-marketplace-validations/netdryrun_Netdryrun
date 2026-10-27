---
title: Trust and security
description: Netdryrun license (Apache-2.0), how releases are published with PyPI Trusted Publishing, security contact, what a lab cannot prove, and privacy (no telemetry, opt-in Cloud upload, a website without cookies or third-party requests).
---

# Trust and security

## License

Netdryrun™ is open source under the [Apache License 2.0](https://github.com/netdryrun/netdryrun/blob/main/LICENSE). The source is at [github.com/netdryrun/netdryrun](https://github.com/netdryrun/netdryrun).

## How releases are published

- Releases are built and published by a GitHub Actions workflow when a version tag (`v*`) is pushed. The workflow checks that the tag matches the package version before building.
- Packages are uploaded to [PyPI](https://pypi.org/project/netdryrun/) with **Trusted Publishing** (OpenID Connect). No PyPI token or password is stored in the repository or its secrets; PyPI accepts the upload because it comes from that workflow in that repository.
- The same workflow creates a GitHub release with the built files attached.
- The GitHub Action (`netdryrun/netdryrun@v0.3.0`) installs Netdryrun from the action's own source at the tag you reference. Pin a tag or a commit SHA.

## Reporting a security issue

Email **[security@netdryrun.com](mailto:security@netdryrun.com)**. Please do not open a public issue for a vulnerability. Include the version, what you found, and how to reproduce it.

## What a lab cannot prove

A Netdryrun pass means the change behaved correctly in a lab. The lab runs real routing software, so a pass is strong evidence for protocol logic and policy intent: sessions come up, the intended prefixes are accepted, routes land in the routing table, traffic gets through, and unwanted routes stay out. It does not prove:

- **Vendor-specific behavior.** Open-source and container routers (FRR, SR Linux, SONiC VS) are not your vendor's routers, and even Arista cEOS is not the same as EOS on hardware. Defaults, policy evaluation and bugs differ between implementations and versions. For Arista you can bring your own licensed cEOS image.
- **Scale.** A lab has a handful of nodes and small tables, not full Internet tables or hundreds of peers.
- **Hardware and ASIC behavior.** Containers have no forwarding hardware, so TCAM limits, hardware programming and line-rate effects are not tested.
- **Timing at scale.** Convergence time in a small lab says little about convergence time in a large production network.

<!-- facts:trust_scope -->
Version 0.3.0 also covers only BGP (IPv4/IPv6 unicast), routes, BGP best-path attributes and ping, plus link-down and node-isolation failure scenarios. OSPF/IS-IS adjacencies and path checks are not covered yet.
<!-- /facts:trust_scope -->

## Running untrusted labs

containerlab runs privileged containers, so a topology and its configs are code that runs with root on the host. Only run labs you trust. In CI, see the [GitHub Action security notes](github-action.md#security-notes). For AI agents, see the [MCP safety model](ai-agents.md#safety-model).

What follows from that, by design:

- **`netdryrun.yml` is code too.** `nodes.<node>.setup` commands are shell commands run inside the node, and a `netdryrun.yml` can point at a topology in any folder. Review a `netdryrun.yml` the way you review a topology.
- **Everything else in `netdryrun.yml` is data.** VRF and interface names are restricted to letters, digits and a few punctuation marks before they reach a device CLI, and addresses and prefixes must parse as IP. A check can't run a device command it doesn't name.
- **`as_path_regex` runs with no time limit.** A pathological pattern can stall a run until your CI job's timeout; it can't do anything else. Set `timeout-minutes` on the job.
- **Text from a lab is treated as untrusted** wherever it ends up: escaped in PR comments and step summaries, kept to one comment line in a recorded baseline, and flattened and capped in MCP results.

## Privacy

**The tool has no telemetry.** The CLI, the GitHub Action and the MCP server do not phone home or send usage data anywhere. Reports are written only to the files you ask for (and to the GitHub Actions step summary when running in Actions). containerlab and Docker may pull images from registries named in your topology, as they normally would.

The one exception is opt-in: if you set `cloud: true` on the GitHub Action, the Action uploads the JSON report to Netdryrun Cloud. The report contains raw command output from your lab devices (configs and routing tables), which can reveal your test network's addressing and topology. Leave `cloud` off and nothing is uploaded.

**This website** is static documentation hosted on GitHub Pages. It sets no cookies, has no analytics and no forms, and serves its fonts itself, so your browser contacts no third party. GitHub, as the host, receives your IP address and request details to serve the pages.

## Trademarks

"Netdryrun" and the Netdryrun logos are trademarks of the Netdryrun project. The Apache-2.0 license covers the code, not the name: forks are welcome under a different name. See the [trademark policy](https://github.com/netdryrun/netdryrun/blob/main/TRADEMARKS.md).
