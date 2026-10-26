---
title: Trust and security
description: netdryrun license (Apache-2.0), how releases are published with PyPI Trusted Publishing, security contact, what a lab cannot prove, and privacy (no telemetry).
---

# Trust and security

## License

netdryrun is open source under the [Apache License 2.0](https://github.com/netdryrun/netdryrun/blob/main/LICENSE). The source is at [github.com/netdryrun/netdryrun](https://github.com/netdryrun/netdryrun).

## How releases are published

- Releases are built and published by a GitHub Actions workflow when a version tag (`v*`) is pushed. The workflow checks that the tag matches the package version before building.
- Packages are uploaded to [PyPI](https://pypi.org/project/netdryrun/) with **Trusted Publishing** (OpenID Connect). No PyPI token or password is stored in the repository or its secrets; PyPI accepts the upload because it comes from that workflow in that repository.
- The same workflow creates a GitHub release with the built files attached.
- The GitHub Action (`netdryrun/netdryrun@v0.1.0`) installs netdryrun from the action's own source at the tag you reference. Pin a tag or a commit SHA.

## Reporting a security issue

Email **[security@netdryrun.com](mailto:security@netdryrun.com)**. Please do not open a public issue for a vulnerability. Include the version, what you found, and how to reproduce it.

## What a lab cannot prove

A netdryrun pass means the change behaved correctly in a lab. The lab runs real routing software, so a pass is strong evidence for protocol logic and policy intent: sessions come up, the intended prefixes are accepted, routes land in the routing table, traffic gets through, and unwanted routes stay out. It does not prove:

- **Vendor-specific behavior.** FRR and SR Linux are not your vendor's routers. Defaults, policy evaluation and bugs differ between implementations. Running your own licensed vendor images is on the roadmap.
- **Scale.** A lab has a handful of nodes and small tables, not full Internet tables or hundreds of peers.
- **Hardware and ASIC behavior.** Containers have no forwarding hardware, so TCAM limits, hardware programming and line-rate effects are not tested.
- **Timing at scale.** Convergence time in a small lab says little about convergence time in a large production network.

Version 0.1.0 also covers only BGP (IPv4/IPv6 unicast), routes and ping. OSPF/IS-IS adjacencies, path checks, policy attributes and failure scenarios are not covered yet.

## Running untrusted labs

containerlab runs privileged containers, so a topology and its configs are code that runs with root on the host. Only run labs you trust. In CI, see the [GitHub Action security notes](github-action.md#security-notes). For AI agents, see the [MCP safety model](ai-agents.md#safety-model).

## Privacy

netdryrun has no telemetry. It does not phone home or send usage data anywhere. Reports are written only to the files you ask for (and to the GitHub Actions step summary when running in Actions). containerlab and Docker may pull images from registries named in your topology, as they normally would.
