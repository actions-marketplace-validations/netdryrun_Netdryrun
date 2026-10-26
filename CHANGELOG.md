# Changelog

## 0.2.0 (unreleased)

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
