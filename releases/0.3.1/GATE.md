# Release gate: Netdryrun 0.3.1

Written by `scripts/release_gate.py` (see [RELEASING.md](../../RELEASING.md)). Do not edit by hand: rerun a layer, or record a decision in `accepted.json` or `review.md`.

**READY TO PUBLISH**: every layer before publishing ran on the same clean commit; no BLOCKER failed or was skipped; every MAJOR passed or was accepted. Tag it, then run `after-publish` to clear it.

**Layers not run yet:**

- Layer 7: after-publish proof

| Layer | Commit | Ran | Time | Result |
|---|---|---|---|---|
| [Layer 1: static](#layer-1-static) | `9b728e8be0` | 2026-10-27 23:03:52 UTC | 1.0 s | 13 PASS |
| [Layer 2: unit tests on every supported Python](#layer-2-unit-tests-on-every-supported-python) | `9b728e8be0` | 2026-10-27 23:03:53 UTC | 3.1 min | 7 PASS |
| [Layer 4: mutation testing](#layer-4-mutation-testing) | `9b728e8be0` | 2026-10-27 23:07:05 UTC | 19.6 min | 4 PASS |
| [Layer 5: live matrix on the built package](#layer-5-live-matrix-on-the-built-package) | `9b728e8be0` | 2026-10-27 23:27:19 UTC | 142.9 min | 2 ACCEPTED, 46 PASS |
| Layer 7: after-publish proof | | not run | | |

## Layer 1: static

Commit `9b728e8be022ee7dd63e8ab28b0d500ce149d68e` on `ndr/release-0.3.1`; 2026-10-27 23:03:52 UTC; 1.0 s; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: actionlint 1.7.7; ruff 0.17.3; shellcheck 0.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| ruff (config in pyproject.toml) | BLOCKER | **PASS** | 0.0 s | All checks passed! |
| actionlint on every workflow (with shellcheck) | BLOCKER | **PASS** | 0.1 s | clean |
| shellcheck, error level, 18 scripts | BLOCKER | **PASS** | 0.1 s | clean |
| shellcheck, warning level, 18 scripts | MAJOR | **PASS** | 0.1 s | clean |
| no empty ${{ }} in action.yml or workflows | BLOCKER | **PASS** | 0.0 s | none |
| public facts match the source (sync_facts.py --check) | BLOCKER | **PASS** | 0.1 s | facts: in sync (version 0.3.1, 0 problem(s)) |
| every version reference says 0.3.1 | BLOCKER | **PASS** | 0.0 s | 32 references agree |
| pyproject.toml declares Python 3.10 to 3.14, the versions tested | MAJOR | **PASS** | 0.0 s | requires-python and classifiers agree |
| every example has a documented expected result and exit code | MAJOR | **PASS** | 0.0 s | 8 examples |
| every topology we ship is named ndr-* | BLOCKER | **PASS** | 0.0 s | 80 topologies |
| CHANGELOG has no Unreleased entries left (all under 0.3.1) | BLOCKER | **PASS** | 0.0 s | cut |
| tag v0.3.1 does not exist yet | BLOCKER | **PASS** | 0.0 s | unused |
| PyPI has no netdryrun 0.3.1 yet | BLOCKER | **PASS** | 0.0 s | HTTP 404 |

## Layer 2: unit tests on every supported Python

Commit `9b728e8be022ee7dd63e8ab28b0d500ce149d68e` on `ndr/release-0.3.1`; 2026-10-27 23:03:53 UTC; 3.1 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: docker 29.9.2; uv 0.13.6 (x86_64-unknown-linux-gnu).

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| unit tests on Python 3.10.12 | BLOCKER | **PASS** | 34.5 s | 1686 passed, 27 skipped |
| unit tests on Python 3.11.18 | BLOCKER | **PASS** | 25.2 s | 1686 passed, 27 skipped |
| unit tests on Python 3.12.16 (with coverage) | BLOCKER | **PASS** | 43.1 s | 1686 passed, 27 skipped |
| coverage of the verdict modules at or above the floors | MAJOR | **PASS** | 0.0 s | all at or above their floors |
| unit tests on Python 3.13.18 | BLOCKER | **PASS** | 22.4 s | 1686 passed, 27 skipped |
| unit tests on Python 3.14.10 | BLOCKER | **PASS** | 22.6 s | 1686 passed, 27 skipped |
| unit tests in a plain python:3.12-slim container (no containerlab, no Docker) | BLOCKER | **PASS** | 38.5 s | 1686 passed, 27 skipped |

**Coverage of the verdict modules** (lines and branches, Python 3.12):

| Module | Lines | Branches | Covered | Floor |
|---|---|---|---|---|
| `src/netdryrun/checks.py` | 283/284 | 121/122 | 99.5% | 99% |
| `src/netdryrun/config.py` | 441/444 | 257/260 | 99.1% | 99% |
| `src/netdryrun/runner.py` | 516/523 | 203/208 | 98.4% | 98% |
| `src/netdryrun/drivers/` | 687/687 | 240/240 | 100.0% | 99% |

## Layer 4: mutation testing

Commit `9b728e8be022ee7dd63e8ab28b0d500ce149d68e` on `ndr/release-0.3.1`; 2026-10-27 23:07:05 UTC; 19.6 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: mutmut python -m mutmut, version 3.8.0.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| no surviving mutants in src/netdryrun/checks.py | BLOCKER | **PASS** | 18.9 min | 1104/1193 mutants caught (92.5%); not caught: 89 survived the tests, 0 in code no test runs, 89 accepted |
| no surviving mutants in src/netdryrun/config.py | BLOCKER | **PASS** | 0.0 s | 1191/1437 mutants caught (82.9%); not caught: 246 survived the tests, 0 in code no test runs, 246 accepted |
| no surviving mutants in src/netdryrun/runner.py | BLOCKER | **PASS** | 0.0 s | 1017/1189 mutants caught (85.5%); not caught: 172 survived the tests, 0 in code no test runs, 172 accepted |
| no surviving mutants in src/netdryrun/drivers/ | BLOCKER | **PASS** | 0.0 s | 1430/1626 mutants caught (87.9%); not caught: 196 survived the tests, 0 in code no test runs, 196 accepted |

**Accepted entries that no longer survive** (1; remove them from accepted.json): `netdryrun.drivers.x_detect__mutmut_33`

**Surviving mutants by function** (703 in all; every diff is in [mutants.md](mutants.md)):

| Function | Survivors |
|---|---|
| `config._describe` | 91 |
| `runner._bgp_convergence_gate` | 57 |
| `config._validate_check` | 48 |
| `runner.run` | 37 |
| `config._validate_scenario` | 30 |
| `checks._ping` | 23 |
| `drivers.eos._summary` | 21 |
| `checks._route` | 20 |
| `drivers.frr._route_table` | 18 |
| `config.load` | 17 |
| `config.load_yaml` | 15 |
| `drivers.eos._bgp_entries` | 15 |
| `runner._yaml_problem` | 15 |
| `config._StrictLoader.construct_mapping` | 13 |
| `drivers.eos._vrf` | 12 |
| `drivers.frr._bgp_paths_raw` | 12 |
| `runner._wait_fault_visible` | 12 |
| `runner.run_scenario` | 12 |
| `checks._describe_path` | 11 |
| `config._validate_bgp_route` | 11 |
| `runner._link_sessions` | 11 |
| `drivers.srlinux._rib_rows` | 10 |
| `checks._bgp_route` | 9 |
| `drivers.srlinux.SrlDriver._read_path` | 9 |
| `runner._shape_problem` | 9 |
| `runner.load_config` | 8 |
| `config._reject_unknown` | 7 |
| `drivers.base.unexpected` | 7 |
| `drivers.frr._bgp_json` | 7 |
| `checks.is_post_convergence` | 6 |
| `drivers.base.Driver._exec` | 6 |
| `drivers.base.as_int` | 6 |
| `drivers.base.load_json` | 6 |
| `drivers.eos._learned` | 6 |
| `drivers.frr._learned` | 6 |
| `drivers.srlinux._list` | 6 |
| `config._suggest` | 5 |
| `drivers.base.network` | 5 |
| `drivers.srlinux._json` | 5 |
| `runner._reach_then_hold` | 5 |
| `runner.preflight` | 5 |
| `checks._evaluate_all` | 4 |
| `drivers.eos._json` | 4 |
| `drivers.eos._table` | 4 |
| `drivers.frr.FrrDriver._confirm_vrf` | 4 |
| `checks._opt` | 3 |
| `checks.run_round_robin` | 3 |
| `config.Fault.describe` | 3 |
| `config.normalize_as_path` | 3 |
| `drivers.base.Driver.all_routes` | 3 |
| `drivers.check_supported` | 3 |
| `drivers.for_node` | 3 |
| `checks._not_configured` | 2 |
| `checks._reach_view` | 2 |
| `checks.inconclusive_reason` | 2 |
| `config._validate_nodes` | 2 |
| `drivers.base.Driver.bgp_neighbors` | 2 |
| `drivers.base.Driver.bgp_paths` | 2 |
| `drivers.base.Driver.ping` | 2 |
| `drivers.base.Driver.routes` | 2 |
| `drivers.base.check_vrf_name` | 2 |
| `drivers.frr._bgp_paths_for_route_check` | 2 |
| `drivers.srlinux.parse_instance_state` | 2 |
| `checks._bgp_prefixes` | 1 |
| `checks._bgp_session` | 1 |
| `checks._evaluate` | 1 |
| `checks.converge_then_hold` | 1 |
| `config.parse_community` | 1 |
| `drivers.eos.EosDriver.all_routes` | 1 |
| `drivers.frr.FrrDriver.all_routes` | 1 |
| `drivers.srlinux.SrlDriver.all_routes` | 1 |
| `drivers.srlinux._bgp_learned` | 1 |
| `runner._sessions_over_links` | 1 |

## Layer 5: live matrix on the built package

Commit `9b728e8be022ee7dd63e8ab28b0d500ce149d68e` on `ndr/release-0.3.1`; 2026-10-27 23:27:19 UTC; 142.9 min; Linux 6.18.54.1-microsoft-standard-WSL2 (x86_64); Python 3.10.12; --strict.

Tools: containerlab ⣴⡾⠛⠛⠖ ⢠⣶⠟⠛⢷⣦ ⢸⣿⣧ ⣿ ⠘⠛⢻⡟⠛⠛ ⣾⣿⡀ ⣿⡇ ⣿⣿⡄ ⢸⡇ ⣿⡟⠛⠛⠃⢸⣿⠛⠛⣷⡄ [38;2;0;201;255m⣿⡇[0m ; docker 29.9.2.

| Check | Severity | Result | Time | Notes |
|---|---|---|---|---|
| build the wheel | BLOCKER | **PASS** | 0.4 s | netdryrun-0.3.1-py3-none-any.whl |
| install netdryrun-0.3.1-py3-none-any.whl in a fresh venv | BLOCKER | **PASS** | 0.4 s |  |
| runs the installed package, not the source tree | BLOCKER | **PASS** | 0.0 s | /tmp/ndr-gate-live-dvf4l1ar/venv/lib/python3.12/site-packages/netdryrun/__init__.py |
| netdryrun --version says 0.3.1 | BLOCKER | **PASS** | 0.0 s | netdryrun 0.3.1 |
| example agent-demo: `Demo OK`, exit 0 | BLOCKER | **PASS** | 69.8 s | exit 0: Demo OK: attempt 1 rejected by 5 leak guards with every other check passing; attempt 2 passed every check. |
| example agent-demo: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example arista-frr: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.6 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example arista-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example batfish-pipeline: `PASSED: 10 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 10 passed, 0 failed (10 checks) |
| example batfish-pipeline: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp: `PASSED: 11 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.7 min | exit 0: PASSED: 11 passed, 0 failed (11 checks) |
| example frr-bgp: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example frr-bgp-broken: `FAILED: 5 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 38.6 s | exit 1: FAILED: 5 passed, 1 failed (6 checks) |
| example frr-bgp-broken: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example sonic-frr: `PASSED: 8 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 1.5 min | exit 0: PASSED: 8 passed, 0 failed (8 checks) |
| example sonic-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-frr: `PASSED: 7 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 59.4 s | exit 0: PASSED: 7 passed, 0 failed (7 checks) |
| example srl-frr: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak: `PASSED: 9 passed, 0 failed`, exit 0 | BLOCKER | **PASS** | 59.5 s | exit 0: PASSED: 9 passed, 0 failed (9 checks) |
| example srl-hidden-leak: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/frr1.conf: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 58.6 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/frr1.conf: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example srl-hidden-leak with leaks/srl1.cli: `FAILED: 8 passed, 1 failed`, exit 1 | BLOCKER | **PASS** | 59.8 s | exit 1: FAILED: 8 passed, 1 failed (9 checks) |
| example srl-hidden-leak with leaks/srl1.cli: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| example times match the docs (within 2x) | MAJOR | **PASS** | 0.0 s | all within 2x |
| Verdict Corpus v1: every verdict matches the committed results.json | BLOCKER | **PASS** | 64.1 min | all verdicts match |
| Verdict Corpus v1: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Verdict Corpus v2: every verdict matches the committed results.json | BLOCKER | **PASS** | 60.2 min | all verdicts match |
| Verdict Corpus v2: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| MCP handshake against the installed wheel | BLOCKER | **PASS** | 1.1 s | MCP handshake OK |
| check pack verification | MAJOR | **ACCEPTED** | 0.0 s | no --pack script given (accepted: No check pack is sold yet: pack verification is paused by the roadmap until the 45-day demand test; it runs with --pack before any pack ships.) |
| 20-node scale test | MAJOR | **ACCEPTED** | 0.0 s | not scripted in the repository yet: run it by hand (accepted: Not scripted yet. A 20-node lab was run by hand in pre-launch testing (it found the PR-comment size limit, fixed in 0.3.1); scripting it is a 0.4.1 item.) |
| SIGINT during deploy: exit 130, a clear message | BLOCKER | **PASS** | 5.0 s | exit 130 |
| SIGINT during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGINT during checks: exit 130, a clear message | BLOCKER | **PASS** | 17.9 s | exit 130 |
| SIGINT during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during deploy: exit 143, a clear message | BLOCKER | **PASS** | 6.5 s | exit 143 |
| SIGTERM during deploy: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| SIGTERM during checks: exit 143, a clear message | BLOCKER | **PASS** | 17.7 s | exit 143 |
| SIGTERM during checks: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node's image does not exist: exit 2 with a clear error | BLOCKER | **PASS** | 0.4 s | exit 2:   wrote json report: /tmp/ndr-gate-live-dvf4l1ar/reports/frr-bgp-missing-image.json |
| a node's image does not exist: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| a node cannot be created (a bind source does not exist): exit 2 with a clear error | BLOCKER | **PASS** | 0.3 s | exit 2:   wrote json report: /tmp/ndr-gate-live-dvf4l1ar/reports/frr-bgp-deploy-fails.json |
| a node cannot be created (a bind source does not exist): no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| two runs of the same lab at once: no false verdict, no crash | BLOCKER | **PASS** | 1.7 min | exit codes 2 and 0 |
| two runs at once: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |
| Docker restarts mid-run: never passed, a clear message | BLOCKER | **PASS** | 3.9 min | exit 2 |
| Docker restart: no lab left running | BLOCKER | **PASS** | 0.0 s | none left |

## Layer 6: independent review

# Layer 6: independent review, Netdryrun 0.3.1

## Pre-launch audit (before the release branch)
Six false-pass paths in 0.3.0, plus docs describing unreleased behavior. All are fixed on this branch with tests that fail on 0.3.0. The config-level paths are reproduced against the real 0.3.0 from PyPI in `advisories/0.3.0-false-pass/` and kept honest by `tests/test_advisory_fixtures.py`.

## Cold code review (fresh agent, no context, the diff v0.3.0..release)
| # | Finding | Severity | Decision | Commit |
|---|---|---|---|---|
| 1 | Positive `bgp_route` attribute checks passed on a temporary best path | False pass | Attribute checks are post-convergence: gated, settled, held | `ded995d` |
| 2 | The BGP gate released at once on a node reporting no neighbors | False pass | `{}` is not converged; released at the cap with a warning in each check's result; the remaining limit is documented | `14f46ae` |
| 3 | `afi: evpn` on SR Linux read 0 | False pass | Refused before deploy, like EOS | `ee24700` |
| 4 | Unreadable state at scenario snapshot disabled the fault-visible wait | Possible false pass | Exit 2 naming the node; "none" only when the state was read | `2ef93a5` |
| 5 | Range-check docs disagreed with the code | Docs | Docs follow the code | `e0f0983` |
| 6 | A report write failure after a verdict exited 2 as "internal error" | Wrong exit | One clear line per failure, exit 2, documented | `71b229b` |
| 7 | `inject_routes` scenarios: no proof the routes reached the node under test | Possible false pass | Scenario post-convergence checks use the BGP gate; the advertisement-interval limit is documented | `f846518` |

Each fix was test-first. The mutation layer then found 214 survivors in the changed functions: 19 killed with new tests (each kill proved by hand), 195 accepted from their diffs with fingerprints (`accepted.json`).

**Lesson recorded in RELEASE-GATE.md:** the cold review is mandatory. It found missing behavior that the invariants and a clean mutation run could not see.

## Outside models (Grok, ChatGPT, through `research/tools/ask_models.py`)
The answers are in HQ `research/model-reviews/release-0.3.1/20261028-004522-*`. Decisions:
- **Absolute claims removed:** "every way … these fixes close them" and "the one bug a change-testing tool can't have" became the found-and-fixed wording. **The remaining limits** (no-neighbor timeout, slow peers, EVPN per driver) are stated in the advisory and linked from the changelog.
- **Corpus numbers labeled historical** (builds before 0.3.1), with the full v1 split (harmful approved, safe blocked) and v2 comparators explicit. They are replaced by the 0.3.1 rerun from the live layer before release.
- **An upgrade box comes first in the changelog:** pins, `validate`, configs that now exit 2, verdicts that change without a config edit, exit codes, an already-running lab, report cleanup in the Action.
- **Security scope** stated for the Action, where the pull request supplies `netdryrun.yml`, and for MCP, which is unconfined until `NETDRYRUN_MCP_ROOT` is set.
- **README:** "did anything break?" became "re-run the checks in netdryrun.yml"; the `record` limits are stated; the convergence paragraph matches the code and gives the exit-code meanings; "evidence a reviewer can trust" became "commands and raw output for a reviewer to inspect".
- **Python versions claim** made precise: CI runs 3.10, 3.12 and 3.13; the gate runs 3.10 to 3.14 and a plain container.
- **Rejected:** none; every point was a fair reading of the shipping text. The "(unreleased)" heading and "yanked" wording become consistent at release time: the changelog heading gets its date, and the yank happens before the advisory is linked.

## Fresh-user replay
The synthetic stranger (HQ `.github/workflows/stranger.yml`) followed this branch's README word for word on a clean GitHub runner: install, examples, and a recorded baseline on a hidden lab with 4 must-fail and 2 must-pass changes. All green (status branch `stranger-status`, 2026-10-27). It found, before release, that `pip install` fails on Ubuntu 24.04; fixed with pipx in `34ea9cf`.
