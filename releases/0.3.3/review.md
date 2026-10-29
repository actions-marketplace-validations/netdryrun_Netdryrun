# Layer 6: independent review, Netdryrun 0.3.3

## Cold code review (fresh agent, no context, the saved prompt; the diff v0.3.2..ndr/agent-runtime, src/, action.yml and templates/netdryrun.yml)

Class: **false-pass** means the finding, if real, could make Netdryrun (or a surface an agent reads) report a pass without testing what it says; under the Layer 6 rule each one is a BLOCKER until it has a failing test and a fix. **other** is everything else. The reviewer found no false pass in the CLI exit code: the job result is still gated on the exit code and the JSON report. Its three false passes were all in the new PR comment / MR note header an agent reads.

| # | Finding | Class | Decision | Commit |
|---|---|---|---|---|
| 1 | A `passed` header from an earlier commit survived a later run that posted nothing (install failed, netdryrun crashed, GitLab's early `exit 2`), and the header named no commit | **false-pass** (agent-facing) | Fixed: the header names the head commit; a run that wrote no report rewrites it as `error`; GitLab writes the note from an EXIT trap, so however the script ends (`test_no_report_still_rewrites_the_header_as_error`, `test_a_job_that_stopped_before_any_report_still_rewrites_the_note_as_error`, `test_a_run_with_no_report_posts_an_error_header_for_the_head_commit`) | `c44a7af` |
| 2 | One marker for every invocation: two labs on one PR overwrote each other's header, the last one winning | **false-pass** (agent-facing) | Fixed: the marker names the lab's `path`, one comment per lab; the guide says every Netdryrun comment must say `passed` (`test_the_body_starts_with_the_lab_marker_then_the_header`, `test_github_updates_only_its_own_comment_for_this_lab`) | `c44a7af` |
| 3 | The comment to update was chosen by body text, not author, so a forged marker comment could stick; GitLab read only the first 100 notes | **false-pass** (agent-facing) | Fixed: only the expected author's comment is updated (Action: `comment-author`, default `github-actions[bot]`; GitLab: the token's own user), every page is read; the docs tell agents to read only the bot's comments (`test_github_creates_a_comment_when_only_others_match`, `test_gitlab_updates_only_the_tokens_own_note_on_any_page`) | `c44a7af` |
| 4 | `tested` is hashed before the deploy, but the agent is free right after `start_run`: a config edited before containerlab reads it was tested yet reported with the old hash | **false-pass** (agent-facing: a verdict tied to the wrong version) | Fixed: after a run that deployed from the files, they are hashed again; a change makes the result `status: error` with `tested.changed_during_run` (MCP and `--verdict`). `check`/`run_checks` don't deploy, which `lab_deployed_by_this_run: false` already says (that sub-point rejected) (`test_a_file_edited_while_the_run_is_in_progress_makes_it_an_error`, `test_a_file_edited_during_the_run_makes_the_agent_result_an_error`) | `35a2089` |
| 5 | `record --guards` swallowed an unreadable interface: no link-subnet guard and no warning | other (coverage dropped) | Fixed: a warning names the node and interface; bridge and host endpoints are skipped (`test_an_unreadable_interface_is_a_warning_not_a_missing_guard`) | `35a2089` |
| 6 | No `::/0` guard when IPv6 unicast runs over IPv4 sessions | other (coverage dropped) | Fixed: IPv6 is also read from the neighbors' address families (`test_ipv6_over_ipv4_sessions_gets_the_ipv6_default_guard`) | `35a2089` |
| 7 | `--verdict` crashed on a topology with a list where a mapping belongs, before any report was written; MCP gave a bare tool error | other (error for the wrong reason) | Fixed: reading the files a run uses never raises; a shape it can't read makes `complete` false (`test_a_malformed_topology_never_crashes_the_agent_result`) | `35a2089` |
| 8 | The client closing stdio during a `start_run` left the lab deployed | other | Fixed: `main()` destroys the active labs when the server stops (`test_the_server_destroys_its_labs_when_the_client_goes_away`) | `35a2089` |
| 9 | Docs and CHANGELOG disagreed with the code: the 50-route cap is per address family; `--min-prefixes` with a count of 0; the your-lab guide still described exact counts; the async result on an internal error; a header `passed` with 0 checks | other (docs) | Fixed, and the header now refuses a pass with no check (`test_a_pass_with_no_check_is_not_a_pass`) | `35a2089`, `c44a7af` |

Each fix was test-first: the tests named above failed on the branch before the fix.

## Multi-vendor AI audit (verdict path)

Three model families got the same brief (`research/briefs/ndr-0.3.3-verdict-audit.md` in HQ). It holds the v0.3.2 diff of src/, `action.yml` and the GitLab component, and none of our conclusions. It asks how this code can:

- report a pass, CHECKS PASSED or a passing PR/MR header without testing what the file or the agent asked;
- escape `NETDRYRUN_MCP_ROOT`;
- turn a failure into a non-failure;
- make a PR/MR's header or outputs lie, or leak the token.

Grok and ChatGPT ran through `research/tools/ask_models.py`. To pass its privacy gate, diff lines are marked `>`/`<`, `index` lines are dropped, and one home path reads `<HOME>`. The open model ran locally (Ollama, qwen3:30b-a3b, 45 minutes). Answers are in HQ `research/model-reviews/release-0.3.3/`. Both API reviews read the code before the cold-review fixes; findings those fixes had already closed are marked so.

| # | Finding | Found by | Class | Decision | Commit |
|---|---|---|---|---|---|
| M1 | Device output in a failed check's evidence can carry a look-alike `<!-- netdryrun-verdict ... passed -->` in the summary | Grok | **false-pass** (agent-facing) | Fixed: the summary can't open an HTML comment (`test_a_lookalike_header_in_the_summary_is_neutralised`) | `36e959b` |
| M2 | Header plus a full summary goes over GitHub's 65,536-character limit, so GitHub rejects the whole comment, header included | Grok | other (verdict lost) | Fixed: the summary is cut so the header stays (`test_the_body_fits_github_with_the_header_first`) | `36e959b` |
| M3 | `start_run`: the lab boots files swapped after the hash, or a topology rewritten to point outside the root | Grok, ChatGPT | **false-pass** | Already fixed by cold review 4: a changed file makes the result an error | `35a2089` |
| M4 | A worker that ends on a `BaseException` leaves the run `running` forever | ChatGPT, Grok | other | Fixed: any end of the worker is a result (`test_a_worker_that_dies_on_a_base_exception_ends_as_error`) | `36e959b` |
| M5 | Truncated run IDs can collide, and every `start_run` shared one evidence file | ChatGPT, Grok | other | Fixed: unique IDs, `netdryrun-report-<run_id>.json` (`test_run_ids_never_collide`, `test_each_async_run_has_its_own_evidence_file`) | `36e959b` |
| M6 | `_tested` listed and walked an outside folder before the root check | ChatGPT | other (confinement) | Fixed: the root check comes first (`test_tested_does_not_list_or_walk_a_folder_outside_the_root`) | `36e959b` |
| M7 | A PR that commits a directory at a report path makes the write fail, so a failed run is published as `error` | Grok | other (exit label) | Fixed: that directory is removed before the run, never the workspace (`test_a_committed_directory_at_a_report_path_is_removed_but_never_the_workspace`). Test-first was not followed: the fix (the removal had to become a loop) was written before its test | `36e959b` |
| M8 | Ranges are now the default, so one leaked default route fits inside a recorded prefix range | Grok | **false-pass** (recorded baselines) | Fixed (coordination decision): `record` writes the guards by default (`--no-guards` to opt out). It writes only guards the recording lab passes, each run with the real check first (`test_guards_are_on_by_default_and_can_be_turned_off`, `test_never_a_guard_the_recording_lab_already_fails`) | `36e959b`, `440f6be` |
| M9 | A failed route read silently dropped that family's link guards, and the link-guard cap was silent | ChatGPT, Grok | other (coverage) | Fixed: each is now an `INCOMPLETE BASELINE` line | `36e959b` |
| M10 | A privileged lab can read the checkout token in `.git/config` | Grok | other (security docs) | Documented: check out with `persist-credentials: false` | `36e959b` |
| M11 | GitLab: the note token is in the job while a privileged lab runs, and the YAML can override `CI_API_V4_URL` | Grok, ChatGPT | other (security scope) | Documented limit (the component is unlisted): anyone who can edit the CI config can read the variable anyway; use `mr-comment` only where MR authors are trusted | `36e959b` |
| M12 | A tampered or stale verdict file with the run's status and plausible counts (GitHub and GitLab), or a forged JSON report for the dotenv | ChatGPT, Qwen | false-pass (claimed) | Rejected: the run deletes these files before it starts and then writes them. Replacing them takes code running in the job after that. A status that disagrees with the checked exit code reads `error` (`test_a_verdict_file_that_disagrees_with_the_run_reads_as_error`) | — |
| M13 | Topology files outside the root (absolute paths, symlinks) are deployed | Grok, ChatGPT | other | Rejected: a documented limit since 0.3.2 (a topology inside the root can still mount host paths) | — |
| M14 | `complete: false` results can still pass; a colon in a bind's host path | ChatGPT | other | Rejected: `complete` is the signal by design, and containerlab's bind syntax splits on the colon too | — |
| M15 | The 50-route cap, and `record`'s headroom lets counts grow | ChatGPT, Grok | other | By design, and both are stated (`INCOMPLETE BASELINE`). The ranges are the documented trade-off; the guards cover the default route | — |
| Q1 | `pr_comment_header` would show a pass with `failed: 1` | Qwen3 30B-A3B | false-pass (claimed) | Rejected, not real: a pass with any failure, or with no check run, reads `error` (`test_the_comment_header_never_carries_lab_text_or_a_pass_it_did_not_get`) | — |
| Q2 | Without a root, files anywhere are hashed | Qwen3 30B-A3B | other | Rejected: an unset root means no confinement, by design and documented; the run deploys those files anyway | — |
| Q3 | A config error with `--verdict` exits 0 | Qwen3 30B-A3B | other (claimed) | Rejected, not real: it exits 2 (`test_a_config_error_writes_the_setup_error`) | — |

## Adversarial review (Layer 6 role 2): the mutant arguments in verdict-deciding functions

ChatGPT reviewed in three rounds (briefs `research/briefs/ndr-0.3.3-adversarial-mutants-{1,2}.md`, `-round2.md`, `-round3.md`). It covered the 184 survivors in `VERDICT_FUNCTIONS` (scripts/release_gate.py), each with its diff and a written argument that it can't turn a failure into a pass.

- **Round 1** checked all 184. Every survivor not listed below was agreed. Several lines marked "REJECT" in fact said the argument holds. The others asked how detail text is used, or gave a counterexample.
- **Round 2** rechecked 93, with the code it asked for: a check's verdict is its `ok` flag, and "unready" is `isinstance(detail, Unready)`, never text. Of the 93, 55 were confirmed and 14 were marked REJECT. Of those 14, 10 said in their own words that only a message changes and no verdict. The other four came with counterexamples.
- **Round 3** traced those four through the code, and all four were confirmed:
  - `_ping_37`: the unreachable pattern needs a literal space, so no match spans two entries (shown by running the regex).
  - `_bgp_convergence_gate_92`: `empty` is always set before it is read.
  - `run_round_robin_72/73`: the branch is unreachable, because a passing sample never ends a check below `confirm`. It is dead code, to remove in 0.4.
- **Killed instead of argued:** `_wait_fault_visible_20` (`continue` to `break` after an unreadable node), by `test_the_fault_wait_names_every_session_still_up_even_after_an_unreadable_node`.

Result: 183 survivors are accepted with a reviewed argument (`reviewed` on each entry in `accepted.json`) and 1 is killed. The review found none that can turn a failure into a pass.

## Cross-platform review (Layer 6 role 3): driver and NOS assumptions

Grok reviewed from `research/briefs/ndr-0.3.3-cross-platform.md`: the four drivers in full, `record`, the `next_diagnostic` commands, and how the lab reads interface addresses.

| # | Finding | Class | Decision | Commit |
|---|---|---|---|---|
| X1 | SONiC keeps a link's address on `EthernetN`, not the topology's `ethN`, so no link guard and no warning | **false-pass** (recorded baselines) | Fixed: a link end with no global address where Netdryrun reads it is an `INCOMPLETE BASELINE` line (`test_a_link_with_no_global_address_where_it_is_read_is_loud`) | `1f2cfb9` |
| X2 | SR Linux keeps it on `e1-Y.0` in `srbase-default` | **false-pass** (recorded baselines) | Fixed by the same rule | `1f2cfb9` |
| X3 | `record` snapshots the default VRF only | coverage | Accepted documented limit: stated in the `record` reference with the mitigation (add checks for other VRFs by hand); fix scheduled: 0.4 (a VRF-aware `record`) | this commit |
| X4 | Scoped link-local neighbors (`fe80::1%eth1`, `fe80::1%eth2`) collapse to one key, so an up session can hide a down one | **false-pass** | Fixed, then superseded by D1/D2 below: keeping the down session hid a false pass on negative checks; the key is now ambiguous and not evaluated | `1f2cfb9` |
| X5 | Graceful-restart stale paths count as present and best until the stale timer ends | **false-pass** | FRR: fixed (coordination decision: a cheap fail-closed fix beats a documented limit). FRR marks the path `"stale": true` (bgpd `route_vty_out_detail`), so a `route` or `bgp_route` check that sees one is not settled, never a pass, present or absent (`test_frr_route_with_a_stale_bgp_path_is_not_settled`, `test_frr_bgp_paths_with_a_stale_path_are_not_settled`, `test_a_route_check_never_passes_on_a_stale_frr_path_present_or_absent`). SR Linux, EOS, SONiC: no stale marker known without a live capture, so an accepted documented limit (advisory, config reference, compatibility matrix), mitigation no GR in labs or a `timeout` above the stale timer; fix scheduled: 0.4 (live GR capture) | this commit |
| X6 | The SR Linux prefix count includes routes dropped by BGP loop detection (seen on a live SR Linux 26.7.2) | **false-pass / accepted documented limit** | Stated publicly in the advisory, the config reference and the compatibility matrix. Mitigation: pair the count with `route` checks; fix scheduled: 0.4 (count usable routes only) | `1f2cfb9`, this commit |
| X7 | SR Linux `bgp-evpn` routes didn't match `protocol: bgp`, so a no-default guard passed on an EVPN-learned default | **false-pass** | Fixed: mapped to `bgp`; widened to every `bgp*` route type by D4 (`test_srl_bgp_evpn_route_type_is_bgp`) | `1f2cfb9` |
| X8 | The routing table doesn't list every BGP route, so a guard could fail on the recording lab | other (false fail) | Fixed by the baseline-guard rule: each guard is run on the lab first | `440f6be` |
| X9 | EOS `Idle(Admin)` was read as `idle(admin)`, so `state: idle` failed | other (false fail) | Fixed (`test_eos_admin_idle_reads_as_idle`) | `1f2cfb9` |
| X10 | A missing MED is read as 0 | **false-pass** | First rejected (BGP's default treats a missing MED as 0); reversed after the 2026-10-29 Grok review (G1 below): with `missing-as-worst` a missing MED is the worst, so `med: 0` passing on it is a false pass. Fixed | see G1 |
| X11 | The EOS `BGP Aggregate` route type wouldn't match `protocol: bgp` | other | Rejected: an aggregate is originated locally, not learned, and appears in no capture | — |
| X12 | FRR's local-pref probe errors on an IPv6-only box | other (false fail) | Backlog (0.4): it errors, never passes | — |

Open false-pass findings after Layer 6: none. X5 is fixed on FRR and, with X6, accepted as a documented limit with the mitigation stated and a fix scheduled for 0.4.

## Follow-up review (Grok, 2026-10-29): three items checked test-first before the freeze

| # | Item | Class | Decision | Tests |
|---|---|---|---|---|
| G1 | An omitted MED must be unknown, not 0 | **false-pass** | Fixed on FRR, EOS and SR Linux: their per-prefix output omits the MED field when the path has no MED attribute (seen in the EOS capture of a locally originated path), and the drivers read that as 0. Now `None`: any `med` check fails on it, `MED is not set`. Three older tests that pinned 0 updated | `test_a_missing_med_is_unknown_on_every_driver`, `test_med_zero_never_passes_on_a_path_without_med` (both failed before the fix) |
| G2 | Truncated or exit-0 error output must never become an empty RIB | **false-pass** (claimed) | Holds, now pinned: parsing is strict `json.loads` (a cut-off document, trailing text or error text raises), empty output raises, a non-zero exit or a timeout raises. Pinned for every route, path and session parser of every driver: each real capture cut at 17 points, and 8 exit-0 error texts | `test_cut_off_or_error_output_is_never_an_empty_answer` (13 parsers) |
| G3 | A covering or default route must never satisfy an exact-prefix check | **false-pass** (claimed) | Holds, now pinned: every driver compares the output's prefix with `==` (zebra's longest-match answer included). Pinned with each capture rewritten to `0.0.0.0/0`, a covering /16 and a more-specific /25 | `test_only_the_exact_prefix_counts_on_every_driver`, `test_a_route_check_fails_when_only_a_covering_route_exists` |

## Mutation follow-up after the cross-platform fixes

The driver fixes moved or added 37 surviving mutants in `frr._bgp_paths_raw` and `eos._summary`. One changed behaviour: `eos._summary_69` kept the *last* of two down sessions sharing a link-local key, where FRR and SR Linux keep the first. Killed by `test_eos_two_down_link_locals_keep_the_first_like_frr`. The other 36 are accepted with arguments in `accepted.json`: 27 change only an error message or the command label in one (a one-argument `unexpected` raises a TypeError, which the parser wrapper turns into the same DriverError), and 9 are equivalent (`maxsplit` when only field 0 is used; `established` written over `established`). Five acceptances that no longer survive were removed.

## Layer 6 delta review (fresh Opus agent, 2026-10-29): `git diff 35a2089..d9723aa -- src action.yml templates`

Every change since the cold review, read by a fresh agent with no context, focused on false passes, exit codes and security. It ran the parsers on the inputs it describes.

| # | Finding | Class | Decision | Tests |
|---|---|---|---|---|
| D1 | Two *up* sessions on one link-local key: the last one's count is kept, so `max: 100` passes while the other session accepts 5000 | **false-pass** | Fixed: a key that several sessions share is ambiguous (`BgpNeighbor.ambiguous`); a `bgp_session` or `bgp_prefixes` check on it is not evaluated (never a pass) and says to use a global address. One peer listed in several EOS per-family summaries is not ambiguous | `test_two_up_link_locals_on_one_key_never_pass_a_prefix_check`, `test_one_peer_in_several_eos_summaries_is_not_ambiguous` |
| D2 | One up, one down: keeping the down one (X4's fix) makes `state: down` pass while a session is up | **false-pass** | Fixed by D1 (FRR, SR Linux, EOS); the down state is still what the convergence gate reads | `test_one_up_one_down_on_one_key_never_pass_a_session_check` |
| D3 | `record`: a guard whose one sample errors (a vtysh timeout, a stale path) was dropped as "the baseline already fails it", without an `INCOMPLETE BASELINE` line | **false-pass** (recorded baselines) | Fixed: an erroring sample is retried (3 samples); a guard that never gets a real answer is left out with an `INCOMPLETE BASELINE` line; only a real failing sample means the lab fails it. An ambiguous neighbor is left out of the baseline the same way | `test_a_guard_sample_that_errors_is_retried_then_loud`, `test_an_ambiguous_neighbor_is_not_recorded_and_says_so` |
| D4 | SR Linux `bgp-vpn` and `bgp-label` routes still didn't match `protocol: bgp` | **false-pass** | Fixed: every `bgp*` route type is BGP | `test_srl_every_bgp_route_type_is_bgp` |
| D5 | `record --guards` was removed (scripts using it break) | other | Rejected: `--guards` never shipped (not in v0.3.2; added and replaced within 0.3.3) | — |

Areas checked with nothing found: the PR comment and MR note header (escaping, cut, status held to the exit code), the report-path removal loops (workspace and parents refused, symlinks unlinked), MED, FRR stale paths, `_tested`, run IDs and evidence files, exit codes, `run_id` in file names.

All four fixes were test-first: each test failed before its fix.
