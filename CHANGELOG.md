# Changelog

## 0.3.1 (unreleased)

Upgrade if you use 0.3.0 or the `netdryrun/netdryrun@v0.3.0` Action: this release closes the injection paths listed under Security, found by a security review after 0.3.0 was tagged.

### Security

- **Names that reach a device command are checked.** `vrf` names are restricted to letters, digits and `. _ : -` (at most 64 characters), and `link_down` interface names to Linux interface names (at most 15 letters, digits and `. _ @ -`), before they go into `vtysh -c`, `sr_cli`, `Cli -c` or `ip link`. Before, a `netdryrun.yml` with a newline or a pipe in one of these names could run a second command inside a lab node. Configs that used other characters now fail validation (exit code `2`).
- **SR Linux:** the `attr-id` and the neighbor address read from device output are checked before they go back into a CLI command, so output from a lab node can't add to that command.
- **Markdown summary and PR comment are inert.** HTML, links, images, `@mentions` and `#123` references from configs or device output are escaped, and code blocks are sized so device output can't close them. Before, text from a lab could forge content in a PR comment or ping people.
- **`netdryrun record`:** warnings that quote device output stay on one YAML comment line, so device output can't add keys to the recorded baseline.
- **MCP server:** a new optional `NETDRYRUN_MCP_ROOT` confines the configs, the labs they point to, topologies and report reads to the listed folders (0.3.0 had no such setting and ignores the variable). `detail` and `error` in tool results are flattened to one line and capped (300 and 1,000 characters). The evidence file is never written through a planted symlink. `record_baseline`'s `wait_seconds` is bounded (0 to 600).
- **GitHub Action:** report files already in the workspace (committed in the PR, or left by an earlier run on a self-hosted runner) are deleted before the run, and the `status` output is `error` unless the report matches the run's own exit code, so a PR can't fake a pass with a committed report. The `inconclusive-reason` output is one line without quotes, backslashes, `$` or backticks.

Impact: the inputs are your own `netdryrun.yml` and the output of your lab nodes, and the lab already runs privileged containers, so the realistic risk on 0.3.0 is a forged or noisy PR comment, a second command inside a lab node, or an MCP client reaching labs outside the folder you meant.

### Fixes

- **`present: false` on SR Linux no longer fails on the router's own routes.** SR Linux lists its own static and interface routes in its BGP RIB as locally originated paths (neighbor `0.0.0.0`), whether or not an export policy advertises them; this was seen live on SR Linux 26.7.2. So on a router with a static default, `bgp_route` with `present: false` and `route` with `protocol: bgp, present: false` for `0.0.0.0/0` failed even when no peer sent a default. Those rows no longer count for `present: false`, and the `route` check no longer reports them as BGP routes. Best-path checks (`bgp_route` with attributes) still read them, so asserting `as_path: ""` on a router's own route works as before. Found while building the new `examples/srl-hidden-leak` lab.
- **The Markdown summary and PR comment of a big lab.** A GitHub comment holds at most 65,536 characters, and the summary listed every check (about 90 characters each), so above roughly 700 checks (a recorded 20-node lab gets there) the Action's `pr-comment` was rejected with a misleading permissions warning. The table now stops before the limit, failures first, and says how many checks it left out; the JSON and JUnit reports still have every check. Found by a 20-node scale test.
- Pre-launch audit fixes: (filled in by the main session)

### Added

- **New example `examples/srl-hidden-leak`** ("The route leak ping can't see"): SR Linux and FRR each receive a leaked default route that loses to their own static, so sessions, ping and the routing table all look fine. The README shows how to see it by hand on each NOS; the checks catch each leak with one `bgp_route` `present: false` guard.
- **Agent evaluation** (`examples/agent-eval/`): ten pre-registered tickets on the example labs, each with a hidden grader, worked by fresh headless Claude Code agents that had only `AGENTS.md`, the AI agents page and the MCP tools. Results, misses included: [RESULTS.md](examples/agent-eval/RESULTS.md).
- **JSON Schema for the report**: `website/docs/schemas/report-v1.json`, published at https://netdryrun.com/schemas/report-v1.json (draft 2020-12). Tests validate reports from real lab runs against it.
- **MCP: Windows paths work when the server runs in WSL.** With Claude Code on Windows and `netdryrun mcp` in WSL (the documented Windows setup), the tools now accept `C:\...` as well as `/mnt/c/...`, so an agent can pass the one path its file tools use. In the agent evaluation, Claude Haiku 4.5 used the WSL path with its Windows file tools and was refused on every ticket; that ended 5 of its 7 failures (T06 and T09 failed for other reasons).
- `AGENTS.md`: for a change that must not change behavior, record a baseline first (a `passed` covers only the checks that exist); on Windows, which path to pass.
- **MCP: `"unready": true` on a failed check that never got usable state** from its node (the command failed, or BGP had no neighbors at all). The inconclusive rule is conservative, so a lab with `bgpd` off on every router still comes back `failed` when other nodes' route and ping checks read cleanly; the flag and `AGENTS.md` now help an agent tell that from a bad change. Found by the agent evaluation's broken-lab ticket.
- **`inject_routes` failure fault** (FRR nodes): a scenario makes a node announce extra routes (`prefixes`, or `count` consecutive ones from `from`, optional `as_path` prepend), then removes them. Use it to test that a max-prefix limit or an import filter holds when a customer or peer misbehaves. Prefixes the node already has configured, and non-FRR nodes, are refused before anything changes.
- **Verdict Corpus v2** (`corpus/v2/`, `python corpus/run.py --corpus v2`): its own base lab, intent spec and 18 pre-registered cases that re-express the v1 misses (unexpected routes, latent risks, rigid prefix counts, a vendor-default label) and add new changes. v1 results are unchanged.
- New `Published release` workflow: the released Action by its tag on `frr-bgp` (must pass) and `frr-bgp-broken` (must fail), and every documented install line from PyPI (`pip install`, `uvx netdryrun`, an MCP handshake over `uvx netdryrun mcp`) on Python 3.10 to 3.15. Runs on pushes to `main` and weekly.
- Python 3.11 and 3.14 are listed in the package classifiers. The published-release workflow installs and runs Netdryrun from PyPI on 3.10 to 3.15; the unit tests run on 3.10, 3.12 and 3.13.
- The source distribution no longer includes the website's demo video and its copies of the demo GIFs.

## 0.3.0 (2026-10-27)

- **Friendlier long waits:** the deploy line says it usually takes 30-90 s (longer when images are pulled), and Ctrl+C prints "Interrupted: no verdict" with exit code 130 instead of a Python traceback. The lab is still cleaned up. Found on the first real Codespaces run.
- **New check type `bgp_route`: attributes of the BGP best path.** `communities` (must carry all; standard, large and well-known names), `without_communities` (must carry none), `as_path` (exact) and `as_path_regex`, `local_pref`, `med` and `next_hop`, plus `present: false` (no path at all in the BGP table). Many real policy bugs are attribute-level: a route that is still there but lost its community, got the wrong local preference, or now goes the long way. Works on FRR, SR Linux, Arista EOS and SONiC; every parser is tested against output captured from live labs, and the examples gained `bgp_route` checks. A key a driver can't read stops the run before deploying with "not supported on `<driver>`" (today every driver reads every key). `netdryrun record --attributes` (and `record_baseline(attributes=true)`) also pins each BGP route's AS path, local preference and communities.
- **New status `inconclusive` (exit code `3`)**: checks failed, but the lab never reached a testable state, so the run says nothing about the change. The rules are conservative: nothing passed on any sample anywhere in the run, and every failing node never returned usable BGP state (its CLI never answered, or BGP had no neighbors at all). A configured session that is down is always `failed`, because an ASN typo looks the same as a slow lab. The JSON report gains `inconclusive_reason` and `"unready": true` on such samples; the Markdown summary and PR comment say so; JUnit reports those checks as errors, not failures; the MCP verdict is `INCONCLUSIVE: the lab did not reach a testable state; this says nothing about your change. Do not apply it until a run passes.`; the GitHub Action reports `status: inconclusive` and a new `inconclusive-reason` output, and still fails the job. Rules: [CLI and reports](https://netdryrun.com/reference/cli/#when-a-run-is-inconclusive).
- **Report schema `netdryrun.report/v1` stays v1**: this release only adds things (the `inconclusive` status value and the `inconclusive_reason` field, plus `unready` in history samples). A consumer that only knows `passed`, `failed` and `error` should treat any other status as not passed.
- A `bgp_session` or `bgp_prefixes` check on a node with no BGP neighbors at all now says so ("no BGP neighbors at all on this node") instead of "seen: none".
- **`netdryrun feedback`** opens a short GitHub feedback form, prefilled with only the version and platform; nothing is sent until you submit it. After an interactive run (not in CI), one line points to it. New **design partners** page: free help testing one real change, in exchange for feedback.
- **Try it in your browser:** a devcontainer (`.devcontainer/`, containerlab's Docker-in-Docker image with containerlab 0.81.1, Netdryrun installed from the checkout, FRR image pre-pulled) and an "Open in GitHub Codespaces" badge, so the agent demo runs with nothing installed.
- **Agent demo** (`examples/agent-demo`): a ticket, a tempting change that passes the ticket checks but leaks routes (rejected), and the proper fix (accepted). `demo.sh` replays it and checks that attempt 1 fails only on the leak guards; CI runs it on pushes to `main` and on pull requests.
- MCP server reports its version and website in `serverInfo`.

## 0.2.0 (2026-10-27)

- **Fix: a change that breaks a baseline check no longer turns a scenario run into `error`.** The recovery check after a scenario now only requires the checks that passed before it; a network that really doesn't recover is reported as failed `[after <scenario>] recovers: ...` checks (exit 1), not a lab error (exit 2). Found by running the edge-guard pack against the Verdict Corpus.
- **SONiC driver** (docker-sonic-vs): sessions, prefix counts, routes, ping, record, failure scenarios. New `nodes.<node>.setup` key runs post-boot configuration commands (retried until the NOS is ready). New example: `examples/sonic-frr`.
- **Arista EOS driver** (cEOS-lab, bring your own image): sessions, prefix counts, routes (routing table + BGP table), ping, record, failure scenarios. New example: `examples/arista-frr`.
- **Leak detection fixed on SR Linux and Arista**: a leaked BGP route that is received but not installed (it lost to a static or local route) only appears in the BGP table on those platforms. Both drivers now read it, so `present: false` fails as it should. Found by live leak tests; regression tests use real captured output.
- **`netdryrun record`**: snapshot a known-good running lab into a `netdryrun.yml` baseline (BGP sessions, exact prefix counts, BGP routes), so you don't write checks by hand.
- **Failure scenarios**: `scenarios:` with `link_down` and `node_isolated` faults. Links are always restored, and the network settles before the next scenario.
- **Faster runs**: positive checks are polled together against one shared convergence window, and post-convergence checks hold together. A badly broken change now costs about one timeout instead of one per failing check (the corpus runs 2-3x faster).
- **GitHub Action `pr-comment: true`**: one pull-request comment with the verdict and the evidence for each failed check, updated in place on every push.
- **PR-ready evidence**: the Markdown summary now includes the exact command and the relevant raw output for each failed check.
- **`state: down`** for `bgp_session`: any state except established.
- **`active: false`** for present routes: accept a route that is in the table but not selected.
- **MCP built in**: `netdryrun mcp` starts the server (no extra install). New `record_baseline` tool. Listed in the official MCP Registry metadata (`server.json`).
- **Network Change Verdict Corpus**: 30 pre-registered cases comparing ping-only, session-only and Netdryrun checks, with losses published.

## 0.1.0 (2026-10-27)

First release: FRR and Nokia SR Linux drivers; `bgp_session`, `bgp_prefixes`, `route`, `ping` checks; convergence-aware positive and post-convergence checks; JSON, Markdown and JUnit reports; GitHub Action; MCP server.
