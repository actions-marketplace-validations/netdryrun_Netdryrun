---
title: GitHub Action
description: Run netdryrun in GitHub Actions with netdryrun/netdryrun@v0.1.0. Inputs, outputs, example workflows, and security notes for running privileged containerlab labs in CI.
---

# GitHub Action

The action installs containerlab, installs netdryrun, runs your checks, writes a summary to the job page, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails.

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.1.0
        with:
          path: network/        # folder containing netdryrun.yml
```

It needs a Linux runner with Docker. GitHub-hosted `ubuntu-latest` runners work.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `path` | `.` | `netdryrun.yml` or the folder containing it |
| `containerlab-version` | `0.81.1` | containerlab version to install, pinned for reproducible runs. Empty means latest. If containerlab is already installed, it is used as is, with a warning if the version differs. |
| `json-report` | `netdryrun-report.json` | Path for the JSON evidence report |
| `junit-report` | `netdryrun-junit.xml` | Path for the JUnit XML report |
| `upload-artifact` | `true` | Upload the reports as a workflow artifact |
| `artifact-name` | `netdryrun-report` | Name of the uploaded artifact |
| `settle` | `10` | Seconds to wait before post-convergence checks |
| `hold` | `10` | Seconds a post-convergence check must hold |

## Outputs

| Output | Meaning |
|---|---|
| `status` | `passed`, `failed` or `error` |
| `passed` | Number of passed checks |
| `failed` | Number of failed checks |

## Examples

### Only run when network files change

```yaml
name: Network dry run
on:
  pull_request:
    paths:
      - "network/**"
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.1.0
        with:
          path: network/
```

### Use the outputs in a later step

```yaml
      - uses: netdryrun/netdryrun@v0.1.0
        id: ndr
        with:
          path: network/
      - if: always()
        run: echo "netdryrun ${{ steps.ndr.outputs.status }}: ${{ steps.ndr.outputs.passed }} passed, ${{ steps.ndr.outputs.failed }} failed"
```

### Several labs

```yaml
jobs:
  dryrun:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        lab: [network/core, network/edge]
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.1.0
        with:
          path: ${{ matrix.lab }}
          artifact-name: netdryrun-${{ strategy.job-index }}
```

Give each matrix job its own `artifact-name`; artifact names must be unique within a workflow run.

## Security notes

- **The lab runs privileged containers.** containerlab needs root on the runner, and the containers it starts are privileged. Treat the topology and router configs as code that runs with root on the runner.
- **Secrets are not passed to the lab.** The action runs netdryrun with a cleared environment (`sudo env -i`), passing only `PATH`, `HOME` and `GITHUB_STEP_SUMMARY`. The job's `GITHUB_TOKEN` and your secrets are not in that environment.
- **Use it on trusted branches.** A pull request can change the topology, the configs or the images it runs. Prefer the `pull_request` trigger (which gives forks a read-only token and no secrets) over `pull_request_target`, and do not run untrusted fork code on self-hosted runners.
- **Artifacts are kept for 14 days.** The reports include raw device output from the lab (configs, routes, command output). They are uploaded with `retention-days: 14`. Set `upload-artifact: false` if that is too long or not wanted.
- **Pin the version.** Use a release tag (`@v0.1.0`) or a commit SHA, not a branch.
