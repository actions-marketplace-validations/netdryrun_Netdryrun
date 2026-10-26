# NetDryRun

**Test network changes before they touch production.**

NetDryRun boots your topology as a real virtual network ([containerlab](https://containerlab.dev)), applies your configs, and checks how the network actually *behaves*: BGP sessions, prefix counts, routes, reachability. It catches mistakes like route leaks before they reach production, and leaves evidence a reviewer can trust.

```text
$ netdryrun run examples/frr-bgp-broken
Deploying lab ndr-frr-broken (3 nodes)...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (6.3s)
  [PASS] r1: prefixes from 10.0.12.2 >= 1 and <= 10 -- 3 ipv4-unicast prefixes accepted (0.1s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (2.3s)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

That run caught a leaked default route that was *received but not selected*. A ping test or a config linter would have missed it.

> Status: **v0.1, early.** Works today with FRR and Nokia SR Linux on Linux and WSL2. Feedback and issues are very welcome.

## Why

- **It tests behavior, not syntax.** Linters and config diffs can't tell you whether BGP will come up or whether a prefix leaks. A real control plane can.
- **It's built for CI.** One GitHub Action, a pass/fail exit code, a Markdown summary in the job, JUnit XML, and a JSON evidence file with every command and raw output.
- **It doesn't lie about convergence.** Positive checks wait for the network to converge. Negative checks ("this route must be absent") run only after convergence and must hold for a time window, so they can't pass just because BGP hasn't come up yet.

## Quick start

Requirements: Linux or WSL2, Docker, [containerlab](https://containerlab.dev/install/), Python 3.10+.

```bash
pip install git+https://github.com/netdryrun/netdryrun
git clone https://github.com/netdryrun/netdryrun && cd netdryrun
netdryrun run examples/frr-bgp          # 3 FRR routers, should pass
netdryrun run examples/srl-frr          # SR Linux + FRR, should pass
netdryrun run examples/frr-bgp-broken   # a bad change, should fail
```

## netdryrun.yml

```yaml
lab: topology.clab.yml      # your containerlab topology
timeout: 90                 # seconds a positive check may wait for convergence

checks:
  - type: bgp_session       # session reaches a state (default: established)
    node: r1
    neighbor: 10.0.12.2
  - type: bgp_prefixes      # accepted prefix count within a range
    node: r1
    neighbor: 10.0.12.2
    min: 1
    max: 10
  - type: route             # route present (or absent), optionally via a protocol
    node: r1
    prefix: 192.168.3.0/24
    protocol: bgp
  - type: ping              # reachability, optionally from a source address
    node: r1
    source: 192.168.1.1
    target: 192.168.3.1
  - type: route             # negative check: must stay absent after convergence
    node: r1
    prefix: 0.0.0.0/0
    protocol: bgp
    present: false
```

Every check also accepts `name`, `timeout` and `vrf`. Ping accepts `expect: failure` and `count`. Drivers are detected from the topology; override them with `nodes: {r1: {driver: frr}}`.

| Check | FRR | SR Linux |
|---|---|---|
| `bgp_session` | ✅ | ✅ |
| `bgp_prefixes` (accepted = received minus rejected by policy) | ✅ | ✅ |
| `route` present / absent | ✅ | ✅ |
| `ping` success / failure | ✅ | ✅ |

## Commands

| Command | What it does |
|---|---|
| `netdryrun run [path]` | Deploy the lab, run the checks, destroy the lab. Add `--keep` to leave it up for debugging |
| `netdryrun check [path]` | Run the checks against a lab that is already running |
| `netdryrun validate [path]` | Validate `netdryrun.yml` without running anything |

Reports: `--json FILE` (full evidence), `--markdown FILE`, `--junit FILE`. Under GitHub Actions, a summary is appended to the job page automatically. Exit codes: `0` passed, `1` a check failed, `2` config or lab error.

## GitHub Action

```yaml
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@main
        with:
          path: network/        # folder containing netdryrun.yml
```

The action installs containerlab, runs the checks, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails. Outputs: `status`, `passed`, `failed`.

## For AI agents (MCP)

AI agents are starting to change networks. NetDryRun gives them a safety gate: an [MCP](https://modelcontextprotocol.io) server that lets an agent dry-run its change in a real lab and proceed only if every check passes.

```bash
pip install "netdryrun[mcp] @ git+https://github.com/netdryrun/netdryrun"
```

Add it to your MCP client (for example Claude Code):

```bash
claude mcp add netdryrun -- netdryrun-mcp
```

Tools: `dry_run` (deploy, check, destroy, verdict), `run_checks` (against a running lab), `validate`, `check_types`. Each result carries a separate `verdict` field: `SAFE TO PROCEED` or `DO NOT APPLY THIS CHANGE`.

Safety model:
- The server **never touches production**. It has no tool that pushes config anywhere; it only builds and tests labs.
- Tool results contain normalized check results, not raw device output, so text inside a lab (a banner, a route description) can't inject instructions into the agent. Raw evidence goes to the JSON report file.
- A lab is code: containerlab runs privileged containers. Only point the server at topologies you trust, on a machine you'd let run Docker.

## How it compares

NetDryRun complements these tools; it doesn't replace them.

| Tool | What it does best | Where NetDryRun fits |
|---|---|---|
| [Batfish](https://batfish.org) | Static analysis of configs, without booting anything; fast and broad | NetDryRun runs the real control plane, so it sees runtime behavior: convergence, timers, what actually lands in the RIB |
| [netlab](https://netlab.tools) | Builds labs from a high-level topology, with built-in validation | Use netlab to build the lab and NetDryRun for convergence-aware CI gates and evidence reports |
| [pyATS / Genie](https://developer.cisco.com/pyats/) | A full test framework with deep Cisco parsers | NetDryRun is a small declarative YAML file plus one GitHub Action, with no test code to write |
| [containerlab](https://containerlab.dev) | Runs the lab | NetDryRun drives containerlab; it doesn't replace it |

What NetDryRun adds: positive checks wait for convergence, negative checks run only after convergence and must hold, received-but-not-selected routes count as present, and every run produces one pass/fail plus an evidence file.

## Honest limits

- Open-source routers are not your vendor's routers. FRR and SR Linux pass/fail is strong evidence for protocol logic and policy intent, but not proof of vendor-specific behavior. Running your own licensed vendor images is on the roadmap.
- v0.1 covers IPv4/IPv6 unicast BGP, routes and ping. More checks are coming: OSPF/IS-IS adjacencies, path/traceroute, policy, failure scenarios.

## Roadmap

- **Outage replays:** famous real-world outages (route leaks, mass withdrawals) rebuilt as runnable labs and check packs. Would your change have caused one?
- Failure scenarios (link down, node down), more check types (OSPF/IS-IS, policy attributes, traceroute) and drivers
- PR comments with diffs, and signed evidence for change tickets

## License

Apache-2.0
