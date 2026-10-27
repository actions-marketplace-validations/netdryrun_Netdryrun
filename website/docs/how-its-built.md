---
title: How Netdryrun is built and checked
description: AI agents write most of Netdryrun. This page lists how its results are checked, with a link to the evidence for each point, and what the project does not claim.
---

# How Netdryrun is built and checked

## Who writes the code

AI agents do most of the development: code, tests, docs and this website. One person directs the work, decides what ships and pushes the commits. The project is new, its first commit is from October 2026, and it has no outside contributors yet. The [commit history](https://github.com/netdryrun/netdryrun/commits/main) is the record of every change.

Because of that, claims about Netdryrun should be checked against something other than the code's author. The rest of this page lists what there is to check.

## Every result can be rerun

- **The corpus is public and reruns with one command.** The [Verdict Corpus](corpus.md) is a set of BGP changes, each with [its own page](corpus.md#every-case), plus the runner ([`corpus/run.py`](https://github.com/netdryrun/netdryrun/blob/main/corpus/run.py)) and the raw output ([`results.json`](https://github.com/netdryrun/netdryrun/blob/main/corpus/results/results.json)).
- **It also reruns on GitHub's machines.** The [Reproduce corpus](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/reproduce-corpus.yml) workflow runs every case on a GitHub-hosted runner from your own fork and lists every verdict that differs from the committed results.

## The corpus verdicts were written before the runs

- **The expected verdicts were committed first.** All 30 cases, with their expected verdicts, were added in one commit, [`b4df0b0`](https://github.com/netdryrun/netdryrun/commit/b4df0b0). The results came later, in [`7576298`](https://github.com/netdryrun/netdryrun/commit/7576298). The [history of `corpus/cases/`](https://github.com/netdryrun/netdryrun/commits/main/corpus/cases) has no other commit: no verdict was changed after a run.
- **Limit of this evidence:** git commit dates are set by the author's machine. The history shows the order of the commits and that the cases were not edited. It is not an independent timestamp.

## Losses are published

<!-- facts:built_losses -->
- **Netdryrun is wrong on 6 of 30 cases**: it approved 5 harmful changes and blocked 1 safe one ([RESULTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/RESULTS.md)). They are shown in the same table as the catches.
    - Approved although harmful: [`12` send-community removed on the pe1 to pe2 iBGP session](corpus/12-ibgp-send-community-dropped.md), [`18` redistribute connected added on pe1](corpus/18-redistribute-connected.md), [`21` Customer maximum-prefix safety limit removed](corpus/21-customer-max-prefix-removed.md), [`23` pe1 accidentally originates 8.8.8.0/24](corpus/23-fat-finger-third-party-origin.md) and [`30` Peer inbound filter replaced with permit-all](corpus/30-peer-import-filter-removed.md).
    - Blocked although safe: [`06` Customer announces a second allowed /24](corpus/06-customer-adds-prefix.md).
<!-- /facts:built_losses -->
- **One of our own labels was wrong.** [Case 12](corpus/12-ibgp-send-community-dropped.md) expected a change to be harmful; on FRR it is a no-op. The label stays as committed and the scores were not corrected upward; the finding and a script that reproduces it are in [AMENDMENTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/AMENDMENTS.md).
- **The misses are explained**, not removed: two are gaps in the intent spec ([18](corpus/18-redistribute-connected.md), [23](corpus/23-fat-finger-third-party-origin.md)) and two are risks no steady-state check can see ([21](corpus/21-customer-max-prefix-removed.md), [30](corpus/30-peer-import-filter-removed.md); [AMENDMENTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/AMENDMENTS.md)).

## Live labs run in CI

Every push to `main` and every pull request runs [`ci.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/ci.yml) ([runs](https://github.com/netdryrun/netdryrun/actions/workflows/ci.yml)). Besides unit tests on Python 3.10, 3.12 and 3.13, three jobs boot real containerlab labs:

- **`e2e`** runs the GitHub Action against [`examples/frr-bgp`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp) and [`examples/srl-frr`](https://github.com/netdryrun/netdryrun/tree/main/examples/srl-frr) (FRR and Nokia SR Linux). Both must pass.
- **`catches-bad-change`** runs [`examples/frr-bgp-broken`](https://github.com/netdryrun/netdryrun/tree/main/examples/frr-bgp-broken), a change that leaks a default route. This job passes only if Netdryrun reports `failed` with at least one failed check.
- **`agent-demo`** replays [`examples/agent-demo`](https://github.com/netdryrun/netdryrun/tree/main/examples/agent-demo): a change that leaks routes must fail on exactly the leak guards, and the proper fix must pass ([`demo.sh`](https://github.com/netdryrun/netdryrun/blob/main/examples/agent-demo/demo.sh)).

The SONiC and Arista EOS drivers are not in CI yet (cEOS is an image each user downloads from Arista). Their unit tests parse output captured from real lab runs ([`tests/fixtures`](https://github.com/netdryrun/netdryrun/tree/main/tests/fixtures)).

## Other models review the work

Before releases, the code is reviewed by AI models from other vendors (OpenAI GPT and xAI Grok) and by separate agent sessions that start without the author's context. The review transcripts are not published. The fixes they led to are: [`ec23379`](https://github.com/netdryrun/netdryrun/commit/ec23379) (v0.2.0 review fixes) and [`6495759`](https://github.com/netdryrun/netdryrun/commit/6495759) (agent demo review fixes).

These reviewers are AI models, not network engineers. No independent human audit of the code has been done.

## Bugs our own testing found

Each of these was found by running Netdryrun against live labs or the corpus. The first two are in the [0.2.0 changelog](https://github.com/netdryrun/netdryrun/blob/main/CHANGELOG.md#020-2026-10-27).

- **False passes on SR Linux and Arista.** A leaked route that was received but not installed was invisible, so a `present: false` check passed when it should have failed. Found by live leak tests; fixed in [`77f43d6`](https://github.com/netdryrun/netdryrun/commit/77f43d6); regression tests use captured output ([`test_drivers.py`](https://github.com/netdryrun/netdryrun/blob/main/tests/test_drivers.py)).
- **Wrong status after a failure scenario.** A change that broke a baseline check ended a scenario run as `error` instead of `failed`. Found by running a check pack against the corpus ([`scripts/pack_verify.sh`](https://github.com/netdryrun/netdryrun/blob/main/scripts/pack_verify.sh)); fixed in [`f6ea560`](https://github.com/netdryrun/netdryrun/commit/f6ea560). There is no unit test for this fix yet.
- **A mislabeled corpus case.** [Case 12](corpus/12-ibgp-send-community-dropped.md), above ([AMENDMENTS.md](https://github.com/netdryrun/netdryrun/blob/main/corpus/AMENDMENTS.md)).

## Supply-chain checks

- **Releases** go to PyPI through Trusted Publishing, with no stored tokens ([`release.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/release.yml)).
- **OpenSSF Scorecard** scores the repository's practices every week and on every push to `main` ([`scorecard.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/scorecard.yml), [current score](https://scorecard.dev/viewer/?uri=github.com/netdryrun/netdryrun)). The score includes the checks this project does poorly on.
- **CodeQL** scans the Python code and the workflows ([`codeql.yml`](https://github.com/netdryrun/netdryrun/blob/main/.github/workflows/codeql.yml)).
- **Every third-party GitHub Action is pinned to a commit**, in the workflows and in [`action.yml`](https://github.com/netdryrun/netdryrun/blob/main/action.yml).

## What we do not claim

- **Not production safety.** A pass means the change behaved correctly in a small lab running open-source or lab images of network operating systems. It does not prove the change is safe on your network ([what a lab cannot prove](trust.md#what-a-lab-cannot-prove)).
- **Not scale.** The labs have a handful of nodes and small routing tables. Nothing here is tested at full Internet table size or with hundreds of peers.
- **Not vendor parity.** FRR, SR Linux, SONiC and cEOS behave differently from each other and from hardware routers. The corpus runs only on FRR, one topology and one intent spec, all written by the Netdryrun maintainers.
- **Not adoption.** Nothing on this site claims who uses Netdryrun.
