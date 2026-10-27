---
title: How Netdryrun is built and verified
description: How Netdryrun is engineered, tested and released, with a link to the evidence for every claim, so you can verify it rather than take our word for it.
---

# How Netdryrun is built and verified

A tool that approves network changes has to earn trust with evidence, not claims. Everything on this page links to something you can inspect or rerun yourself: the test corpus, the CI runs, the commit history and the release pipeline.

## At a glance

| | Evidence |
|---|---|
| Accuracy on realistic BGP changes | Verdict Corpus v1: **24/30** (ping only 20/30, sessions up 15/30). v2: **16/18** (ping only 9/18, sessions up 7/18). [Results](corpus.md) |
| Expected verdicts fixed before any run | Committed first, never edited: [`b4df0b0`](https://github.com/netdryrun/netdryrun/commit/b4df0b0) (v1), [`322cc4e`](https://github.com/netdryrun/netdryrun/commit/322cc4e) (v2) |
| Every result reproducible | One command locally, or the [Reproduce corpus](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/reproduce-corpus.yml) workflow from your own fork |
| Real labs on every change | FRR and Nokia SR Linux labs boot in CI on every push and pull request ([runs](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml)) |
| What users install is tested too | The released Action and the PyPI package, on every push and weekly ([`published-action.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/published-action.yml)) |
| Supply chain | PyPI Trusted Publishing, CodeQL, OpenSSF Scorecard, every Action pinned to a commit |
| Losses | Published next to the wins, never removed |

## Engineering process

Netdryrun is developed by its maintainer, Victor Khen, with AI coding agents doing most of the implementation: code, tests, documentation and this website. The maintainer sets the direction, reviews the results, decides what ships and publishes every release. The [commit history](https://github.com/netdryrun/netdryrun/commits/main) records every change.

We state this plainly because it should shape how you judge the tool: not by who or what wrote it, but by whether it holds up under checks you can run yourself. That is why every claim below comes with evidence. The project started in October 2026 and has no outside contributors yet.

## Pre-registered accuracy testing

The [Verdict Corpus](corpus.md) measures Netdryrun on realistic BGP changes, each labelled harmful or safe in advance, and compares it with two common checks: "ping still works" and "all BGP sessions are up".

- **Verdicts are committed before anything runs.** v1: all 30 cases with their expected verdicts in [`b4df0b0`](https://github.com/netdryrun/netdryrun/commit/b4df0b0), results later in [`7576298`](https://github.com/netdryrun/netdryrun/commit/7576298). v2: 18 new cases in [`322cc4e`](https://github.com/netdryrun/netdryrun/commit/322cc4e), results later in [`669b30f`](https://github.com/netdryrun/netdryrun/commit/669b30f). No case was edited after a run ([history of `corpus/cases/`](https://github.com/netdryrun/netdryrun/commits/main/corpus/cases)).
- **v2 is a harder test, not a friendlier one.** Its cases target the kinds of change v1 missed. It was written after seeing v1's results, which is a limitation to keep in mind.
- **Everything reruns.** The runner ([`corpus/run.py`](https://github.com/netdryrun/netdryrun/blob/main/corpus/run.py)), every case and the raw output ([`results.json`](https://github.com/netdryrun/netdryrun/blob/main/corpus/results/results.json)) are public. `python corpus/run.py` reruns v1 and `--corpus v2` reruns v2. The GitHub workflow does the same on a hosted runner and lists any verdict that differs.
- **Limit of this evidence:** git commit dates come from the author's machine. The history proves the order of the commits and that the cases were not changed; it is not an independent timestamp.

## Published losses

<!-- facts:built_losses -->
- **Netdryrun is wrong on 6 of 30 cases**: it approved 5 harmful changes and blocked 1 safe one ([RESULTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/RESULTS.md)). They are shown in the same table as the catches.
    - Approved although harmful: [`12` send-community removed on the pe1 to pe2 iBGP session](corpus/12-ibgp-send-community-dropped.md), [`18` redistribute connected added on pe1](corpus/18-redistribute-connected.md), [`21` Customer maximum-prefix safety limit removed](corpus/21-customer-max-prefix-removed.md), [`23` pe1 accidentally originates 8.8.8.0/24](corpus/23-fat-finger-third-party-origin.md) and [`30` Peer inbound filter replaced with permit-all](corpus/30-peer-import-filter-removed.md).
    - Blocked although safe: [`06` Customer announces a second allowed /24](corpus/06-customer-adds-prefix.md).
<!-- /facts:built_losses -->
- **v2 misses 2 of 18:** case 04, a mistyped aggregate (its case file predicted the miss), and case 18, a deleted discard route that causes a routing loop no check probes ([v2 results](https://github.com/netdryrun/netdryrun/blob/main/corpus/v2/RESULTS.md)).
- **One of our own labels was wrong.** [Case 12](corpus/12-ibgp-send-community-dropped.md) expected a change to be harmful; on FRR it is a no-op. The label stays as committed and the score was not corrected in our favour. The finding and a script that reproduces it are in [AMENDMENTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/AMENDMENTS.md).
- **Every v1 miss is explained:** two were gaps in the intent spec ([18](corpus/18-redistribute-connected.md), [23](corpus/23-fat-finger-third-party-origin.md)) and two were risks no steady-state check can see ([21](corpus/21-customer-max-prefix-removed.md), [30](corpus/30-peer-import-filter-removed.md)). Failure scenarios, added since, catch the v2 versions of those two (v2 cases 05, 06 and 11).

## Continuous integration with live labs

Every push to `main` and every pull request runs [`ci.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/ci.yml) ([runs](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml)): unit tests on Python 3.10, 3.12 and 3.13, plus three jobs that boot real containerlab labs.

- **`e2e`** runs the GitHub Action on [`examples/frr-bgp`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp) and [`examples/srl-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/srl-frr) (FRR and Nokia SR Linux). Both must pass.
- **`catches-bad-change`** runs [`examples/frr-bgp-broken`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp-broken), a change that leaks a default route. The job succeeds only if Netdryrun rejects it.
- **`agent-demo`** replays [`examples/agent-demo`](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo): a route-leaking change must fail on exactly the leak guards, and the proper fix must pass.

A second workflow, [`published-action.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/published-action.yml), tests what users install rather than the code on `main`: the released Action by its tag (it must pass a good change and reject a bad one), and `pip install` and `uvx` from PyPI on every supported Python version, including an MCP handshake.

SONiC and Arista EOS are not in CI yet (cEOS is an image each user downloads from Arista). Their unit tests parse output captured from real lab runs ([`tests/fixtures`](https://github.com/netdryrun/netdryrun/tree/main/tests/fixtures)).

## Performance at scale

On a 20-node leaf-spine fabric (4 spines, 16 leaves, FRR, 64 links), `netdryrun record` produced 560 checks in 11 seconds, and a full `netdryrun run` (deploy, convergence, all checks, destroy) took 65 seconds. A deliberately broken change failed exactly the 83 checks it should have. Full numbers, memory use and limits are in the [FAQ](faq.md#a-20-node-lab).

## Independent review

Before each release, the code is reviewed by AI models from other vendors (OpenAI GPT and xAI Grok) and by separate agent sessions that start without the author's context. Fixes from these reviews: [`ec23379`](https://github.com/netdryrun/netdryrun/commit/ec23379) (v0.2.0), [`6495759`](https://github.com/netdryrun/netdryrun/commit/6495759) (agent demo) and [`90fe0ae`](https://github.com/netdryrun/netdryrun/commit/90fe0ae): a security review of the MCP server, the GitHub Action and every path where lab output reaches a shell, a device CLI or a PR comment, with 7 findings, each fixed with a regression test.

These reviewers are AI models, not human auditors. No independent human security audit has been done yet. If you are qualified and willing to do one, we would welcome it: see the [security policy](https://github.com/netdryrun/netdryrun/security/policy).

## Defects found by our own testing

Each was found by running Netdryrun against live labs or the corpus, and is recorded in the [changelog](https://github.com/netdryrun/netdryrun/blob/main/CHANGELOG.md).

- **False passes on SR Linux and Arista:** a leaked route that was received but not installed was invisible, so a `present: false` check passed when it should have failed. Fixed in [`77f43d6`](https://github.com/netdryrun/netdryrun/commit/77f43d6), with regression tests on captured output ([`test_drivers.py`](https://github.com/netdryrun/netdryrun/blob/main/tests/test_drivers.py)).
- **Wrong status after a failure scenario:** a change that broke a baseline check ended as `error` instead of `failed`. Found with [`scripts/pack_verify.sh`](https://github.com/netdryrun/netdryrun/blob/main/scripts/pack_verify.sh); fixed in [`f6ea560`](https://github.com/netdryrun/netdryrun/commit/f6ea560).
- **PR comments over GitHub's size limit on large labs:** found by the 20-node scale test. The comment now keeps every failure and summarizes the rest.
- **A mislabeled corpus case:** [case 12](corpus/12-ibgp-send-community-dropped.md), above.

## Supply-chain security

- **Releases** are published to PyPI with Trusted Publishing, so no tokens are stored ([`release.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/release.yml)). A release fails if the tag and the package version differ.
- **OpenSSF Scorecard** rates the repository's practices weekly and on every push ([current score](https://scorecard.dev/viewer/?uri=github.com/netdryrun/netdryrun)), including the areas where a young, single-maintainer project scores low.
- **CodeQL** scans the Python code and the workflows ([`codeql.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/codeql.yml)).
- **Every third-party GitHub Action is pinned to a commit**, in the workflows and in [`action.yml`](https://github.com/netdryrun/netdryrun/blob/main/action.yml). Dependabot keeps the pins current.

## What we do not claim

- **Not production safety.** A pass means the change behaved correctly in a lab running open-source or lab images of network operating systems. It does not prove the change is safe on your network ([what a lab cannot prove](trust.md#what-a-lab-cannot-prove)).
- **Not Internet scale.** The largest measured lab has 20 nodes and small routing tables. Nothing here is tested with full Internet tables or hundreds of peers.
- **Not vendor parity.** FRR, SR Linux, SONiC and cEOS behave differently from each other and from hardware routers. The corpus runs only on FRR, with one topology and one intent spec per version, all written by the Netdryrun maintainers.
- **Not adoption.** Nothing on this site claims who uses Netdryrun.
