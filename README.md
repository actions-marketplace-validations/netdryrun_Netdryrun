<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-wordmark-white-tm.svg">
    <img alt="Netdryrun" src="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-wordmark-navy-tm.svg" width="360">
  </picture>
</p>

[![CI](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml/badge.svg)](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/netdryrun/netdryrun/badge)](https://scorecard.dev/viewer/?uri=github.com/netdryrun/netdryrun)

**Test network changes before they touch production.**

Netdryrun™ boots your topology as a real virtual network ([containerlab](https://containerlab.dev)), applies your configs, and checks how the network actually *behaves*: BGP sessions, prefix counts, routes, reachability. It catches mistakes like route leaks before they reach production, and leaves evidence a reviewer can trust.

<p align="center"><img alt="Netdryrun catching a leaked default route that ping and session checks miss" src="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-demo.gif" width="820"></p>

```text
$ netdryrun run examples/frr-bgp-broken
Deploying lab ndr-frr-broken (3 nodes)...
  [PASS] r1: BGP session to 10.0.12.2 is established -- state is established (6.3s)
  [PASS] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 3/3 replies (2.3s)
  ... (3 more passing checks trimmed)
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

That run caught a leaked default route that was *received but not selected*. A ping test or a session check would have missed it: every session is up and every address answers. (A static analyzer such as Batfish also catches this particular leak; the [Batfish page](https://netdryrun.com/batfish/) shows one that it misses and a lab catches.)

<!-- facts:readme_status -->
> Status: **v0.3.1, early.** Works today with FRR, Nokia SR Linux, SONiC (docker-sonic-vs) and Arista EOS (cEOS, bring your own image) on Linux and WSL2. On the [verdict corpus](https://netdryrun.com/corpus/), Netdryrun judged 24/30 realistic BGP changes correctly (ping-only checks 20/30, all-sessions-up checks 15/30) and 16/18 on v2, written after v1 to target its misses (9/18 and 7/18). On v1, Netdryrun approved 5 of the 19 harmful changes; ping-only checks approved 10. Both are small benchmarks the maintainers wrote on one FRR topology, with expected verdicts committed before any run: they compare methods, they are not a production reliability estimate. Provenance: neither ran on a released version. v1 ran on a pre-release build (commit `ec23379`, which called itself 0.2.0; the tagged 0.2.0 added the SONiC and EOS drivers and a scenario-recovery fix, `f6ea560`); v2 on a development build from main after 0.2.0 (it called itself 0.2.0 and recorded no commit) with the then-unreleased `inject_routes` fault (commit `d9da1ad`). A rerun of both on the released 0.3.1 is pending. Feedback and issues are very welcome.
<!-- /facts:readme_status -->

## Why

- **It tests behavior, not syntax.** A config diff shows what changed, not whether BGP comes up or which routes each router ends up with. A real control plane shows what the routing software actually does.
- **It's built for CI.** One GitHub Action, a pass/fail exit code, a Markdown summary in the job, JUnit XML, and a JSON evidence file with every command and raw output.
- **It waits for convergence, with stated rules.** A positive check passes after 2 passing samples taken 3 s apart, within its timeout. Negative checks ("this route must be absent") start only after the positive checks have finished and a 10 s settle, then must hold for 10 s (both configurable), so they don't pass just because BGP hasn't come up yet. The rules are sample-based; see [convergence semantics](https://netdryrun.com/reference/config/#convergence-semantics).

## Quick start

### Try it in your browser (no install)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/netdryrun/netdryrun?quickstart=1)

The codespace comes with Docker, containerlab and Netdryrun already installed. When the terminal shows `Ready`, run:

```bash
bash examples/agent-demo/demo.sh
```

A route-leaking change is rejected, then the fix passes every check. It uses your GitHub account's free Codespaces hours (2-core machine). [Details](https://netdryrun.com/getting-started/#try-it-in-your-browser).

### On your own machine

Requirements: Linux or WSL2, Docker, [containerlab](https://containerlab.dev/install/), Python 3.10+.

```bash
pip install netdryrun
git clone https://github.com/netdryrun/netdryrun && cd netdryrun
netdryrun run examples/frr-bgp          # 3 FRR routers, should pass
netdryrun run examples/srl-frr          # SR Linux + FRR, should pass
netdryrun run examples/frr-bgp-broken   # a bad change, should fail
```

### On your own containerlab topology (3 commands)

```bash
netdryrun record my-lab/topology.clab.yml --deploy   # snapshot today's behavior into my-lab/netdryrun.yml
# ...edit your configs (the change you want to test)...
netdryrun run my-lab                                   # did anything break?
```

`record` writes a baseline of every established BGP session, its exact prefix count and up to 50 BGP routes per node. It trusts the lab as it is today, so review it (remove what is allowed to change, add negative checks), commit it, and every future change is tested against it, locally or in CI.

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

Failure scenarios break something, check the network still behaves, then restore it. They can take links down, or (from 0.3.1) make an FRR neighbor announce routes it shouldn't, to prove a max-prefix limit or an import filter actually holds:

```yaml
scenarios:
  - name: r1-r2 link fails
    link_down: {node: r1, interface: eth1}
    checks:
      - {type: ping, node: r1, source: 192.168.1.1, target: 192.168.2.1}   # rerouted via r3
      - {type: bgp_session, node: r1, neighbor: 10.0.12.2, state: down}
  - name: customer floods 200 prefixes
    inject_routes: {node: ce1, count: 200, from: 10.100.16.0/24}
    checks:
      - {type: bgp_prefixes, node: up1, neighbor: 10.0.2.1, max: 51}   # the limit stops the flood
```

Every check also accepts `name`, `timeout` and `vrf`. Ping accepts `expect: failure` and `count`. Drivers are detected from the topology; override them with `nodes: {r1: {driver: frr}}`. Nodes that are configured after boot (SONiC) take `setup` commands: `nodes: {sonic1: {setup: [...]}}`.

| Check | FRR | SR Linux | Arista EOS (cEOS) | SONiC (VS) |
|---|---|---|---|---|
| `bgp_session` | ✅ | ✅ | ✅ | ✅ |
| `bgp_prefixes` (accepted = received minus rejected by policy) | ✅ | ✅ | ✅ | ✅ |
| `route` present / absent | ✅ | ✅ | ✅ | ✅ |
| `bgp_route` best-path attributes: communities (standard, large, well-known), AS path (exact or regex), local preference, MED, next hop | ✅ | ✅ | ✅ | ✅ |
| `ping` success / failure | ✅ | ✅ | ✅ | ✅ |
| **How it is tested** | Live lab in CI on every push | Live lab in CI on every push | Parsers tested against output captured from live labs; no live lab in CI | Parsers tested against output captured from live labs; no live lab in CI |

## Commands

| Command | What it does |
|---|---|
| `netdryrun run [path]` | Deploy the lab, run the checks, destroy the lab. Add `--keep` to leave it up for debugging |
| `netdryrun check [path]` | Run the checks against a lab that is already running |
| `netdryrun validate [path]` | Validate `netdryrun.yml` without running anything |
| `netdryrun record topology.clab.yml` | Snapshot a known-good lab into a `netdryrun.yml` baseline, so you don't write checks by hand |

Reports: `--json FILE` (full evidence), `--markdown FILE`, `--junit FILE`. Under GitHub Actions, a summary is appended to the job page automatically. Exit codes: `0` passed, `1` a check failed, `2` config or lab error, `3` inconclusive (the lab never reached a testable state, so the run says nothing about the change).

## GitHub Action

```yaml
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.3.1
        with:
          path: network/        # folder containing netdryrun.yml
```

The action installs containerlab, runs the checks, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails. Outputs: `status`, `passed`, `failed`, `inconclusive-reason`.

## For AI agents (MCP)

**AI can propose network changes. Netdryrun verifies the outcome.** Agents: read [AGENTS.md](https://github.com/netdryrun/netdryrun/blob/main/AGENTS.md).

AI agents are starting to change networks. Netdryrun gives them a safety gate: an [MCP](https://modelcontextprotocol.io) server that lets an agent dry-run its change in a real lab and proceed only if every check passes.

```bash
pip install netdryrun
```

Add it to your MCP client (for example Claude Code):

```bash
claude mcp add netdryrun -- netdryrun mcp
```

Tools: `dry_run` (deploy, check, destroy, verdict), `run_checks` (against a running lab), `record_baseline` (snapshot a known-good lab into checks), `validate`, `check_types`. Each result carries a separate `verdict` field: `SAFE TO PROCEED`, `DO NOT APPLY THIS CHANGE`, or `INCONCLUSIVE: the lab did not reach a testable state; ...` when the lab never came up. `SAFE TO PROCEED` means only that every check in the file passed in the lab. A change can break something no check looks at and still get it: in our [agent evaluation](https://netdryrun.com/ai-agents/), an agent's "pure refactor" added `redistribute connected` and passed, because no check covered the extra routes. For a change that must not change behavior, record a baseline first.

**Demo** ([examples/agent-demo](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo)): the ticket says the customer's new block must reach the upstream and the peer. The tempting change passes every ticket check, session and ping, but leaks routes; Netdryrun rejects it. The two-line fix passes the same checks. (A scripted replay of the two attempts; CI runs it.)

<p align="center"><img alt="Attempt 1 passes the ticket checks but fails five leak guards; attempt 2 passes all 14 checks" src="https://raw.githubusercontent.com/netdryrun/netdryrun/main/.github/assets/netdryrun-agent-demo.gif" width="820"></p>

Safety model:
- The server **never touches production**. It has no tool that pushes config anywhere; it only builds and tests labs.
- Tool results contain normalized check results, not raw device output. A check's `detail` can still quote a fragment of lab text (a banner, a route description); from 0.3.1 it is kept to one line and capped in length, and it never changes `status` or `verdict`. Raw evidence goes to the JSON report file.
- A lab is code: containerlab runs privileged containers. Only point the server at topologies you trust, on a machine you'd let run Docker.

## How it compares

Netdryrun complements these tools; it doesn't replace them.

| Tool | What it does best | Where Netdryrun fits |
|---|---|---|
| [Batfish](https://batfish.org) | Static analysis of configs, without booting anything; fast and broad | Netdryrun runs the real control plane, so it sees runtime behavior: convergence, sessions that really come up, what actually lands in the RIB |
| [pyATS / Genie](https://developer.cisco.com/pyats/) | A full test framework with deep Cisco parsers | Netdryrun is a small declarative YAML file plus one GitHub Action, with no test code to write |
| [containerlab](https://containerlab.dev) | Runs the lab | Netdryrun drives containerlab; it doesn't replace it |

What Netdryrun adds: positive checks wait for convergence, negative checks run only after convergence and must hold, received-but-not-selected routes count as present, and every run produces one pass/fail plus an evidence file.

## Honest limits

- Lab routers are not your production routers. A pass on FRR, SR Linux, SONiC VS or Arista cEOS is strong evidence for protocol logic and policy intent, but not proof of hardware, scale or version-specific behavior. For Arista, bring your own licensed cEOS image to test real vendor code.
- Checks cover IPv4/IPv6 unicast BGP (sessions, prefix counts, best-path attributes), routes and ping, with link-down, node-isolation and route-injection (FRR only) failure scenarios. More checks are coming: OSPF/IS-IS adjacencies, path/traceroute.
- No Cisco or Juniper driver yet: their lab images are licensed. See [Why not Cisco or Juniper?](https://netdryrun.com/faq/#why-not-cisco-or-juniper)

How results are checked, and who writes the code (mostly AI agents): [How it's built](https://netdryrun.com/how-its-built/).

## Roadmap

- **Outage replays:** famous real-world outages (route leaks, mass withdrawals) rebuilt as runnable labs and check packs. Would your change have caused one?
- More failure scenarios, more check types (OSPF/IS-IS, traceroute) and drivers
- PR comments with diffs, and signed evidence for change tickets

## License

Apache-2.0. "Netdryrun" and the Netdryrun logo are trademarks; see [TRADEMARKS.md](https://github.com/netdryrun/netdryrun/blob/main/TRADEMARKS.md).

<!-- mcp-name: io.github.netdryrun/netdryrun -->
