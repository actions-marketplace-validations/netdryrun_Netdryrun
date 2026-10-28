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
