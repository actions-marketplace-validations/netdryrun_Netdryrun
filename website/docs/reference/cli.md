---
title: CLI and reports
description: netdryrun command-line reference. The run, check and validate commands, every flag, exit codes, and the JSON (netdryrun.report/v1), Markdown and JUnit report formats.
---

# CLI and reports

```text
netdryrun run      [path] [options]   deploy the lab, run checks, destroy the lab
netdryrun check    [path] [options]   run checks against an already running lab
netdryrun validate [path]             validate netdryrun.yml without running anything
netdryrun --version
```

`path` is `netdryrun.yml` or the folder containing it. Default: the current folder.

## Commands

### run

Deploys the containerlab topology (`containerlab deploy --reconfigure`), runs every check, writes reports, and destroys the lab (`containerlab destroy --cleanup`). The lab is destroyed even when checks fail, unless you ask to keep it.

### check

Runs the checks against a lab that is already up, for example one left running with `--keep`. It does not deploy or destroy anything. It fails with an error if any of the lab's containers are not running.

### validate

Loads and validates `netdryrun.yml` and prints the parsed checks. It does not need Docker or containerlab to be running.

```text
$ netdryrun validate examples/frr-bgp
OK: examples/frr-bgp/netdryrun.yml (6 checks, lab .../examples/frr-bgp/topology.clab.yml)
  - [bgp_session] r1: BGP session to 10.0.12.2 is established
  ...
```

## Options

`run` and `check`:

| Option | Default | Meaning |
|---|---|---|
| `--json FILE` | | Write the full evidence report as JSON |
| `--markdown FILE` | | Write a Markdown summary (for PR comments) |
| `--junit FILE` | | Write JUnit XML (for CI test reporting) |
| `--settle SECONDS` | `10` | Wait before post-convergence checks |
| `--hold SECONDS` | `10` | How long a post-convergence check must hold (a check's own `hold` key overrides it) |
| `--no-step-summary` | | Do not append the Markdown summary to `$GITHUB_STEP_SUMMARY` |

`run` only:

| Option | Meaning |
|---|---|
| `--keep` | Leave the lab running afterwards, for debugging |
| `--keep-on-failure` | Leave the lab running only if the run did not pass |

When a lab is kept, netdryrun prints the command to destroy it. See [convergence semantics](config.md#convergence-semantics) for what `--settle` and `--hold` control.

## Exit codes

| Code | Status | Meaning |
|---|---|---|
| `0` | `passed` | Every check passed |
| `1` | `failed` | At least one check failed |
| `2` | `error` | Config error, or the lab could not be deployed or reached (containerlab or Docker missing, deploy failed, containers not running, unknown driver) |

## GitHub Actions step summary

When the `GITHUB_STEP_SUMMARY` environment variable is set (it is in GitHub Actions), the Markdown summary is appended to the job page automatically. Use `--no-step-summary` to turn this off.

## Report formats

### Console

One line per check as it finishes, then a summary line:

```text
  [FAIL] r1: route 0.0.0.0/0 via bgp is absent -- unexpectedly present via bgp (not selected) (0.1s)
FAILED: 5 passed, 1 failed (6 checks)
```

### JSON

`--json FILE` writes the full evidence. Schema identifier: `netdryrun.report/v1`.

| Field | Type | Meaning |
|---|---|---|
| `schema` | string | Always `netdryrun.report/v1` |
| `status` | string | `passed`, `failed` or `error` |
| `lab` | string | containerlab lab name |
| `config` | string | Path of the `netdryrun.yml` that was run |
| `started`, `finished` | string | UTC timestamps (ISO 8601) |
| `error` | string or null | Lab or driver error, if the run could not complete |
| `environment` | object | `netdryrun`, `containerlab` and `python` versions, `host` platform, and `nodes` (each with `kind` and `image`) |
| `summary` | object | `passed`, `failed`, `total` |
| `checks` | array | One object per check, in file order (below) |

Each entry in `checks`:

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Check name |
| `type` | string | Check type |
| `params` | object | The check's parameters after normalization |
| `passed` | boolean | Result |
| `detail` | string | Human-readable result, for example `3 ipv4-unicast prefixes accepted` |
| `attempts` | integer | Number of samples taken |
| `duration_s` | number | Seconds spent on the check |
| `started` | string | UTC timestamp |
| `history` | array | Every sample (last 50): `t` (seconds since start), `passed`, `detail` |
| `evidence` | array | Raw commands from the final sample: `node`, `cmd`, `rc`, `output`, `stderr` |

Long outputs are truncated (the last 20,000 characters of command output are kept).

### Markdown

`--markdown FILE` writes a short summary: a heading (passed, failed, or could not run), the pass/fail counts and lab name, a table of checks with failures first, and a footer with the netdryrun and containerlab versions. This is the same text appended to the GitHub Actions step summary.

### JUnit XML

`--junit FILE` writes one `<testsuite name="netdryrun">` with one `<testcase>` per check:

- `classname` is `netdryrun.<type>`, for example `netdryrun.route`
- a failed check has a `<failure>` whose `message` is the detail and whose body is the evidence as JSON
- a lab error adds a testcase named `lab` with an `<error>` element
