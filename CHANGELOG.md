# Changelog

## 0.3.0 (2026-10-27)

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
