---
title: GitHub Action
description: Run Netdryrun in GitHub Actions with netdryrun/netdryrun@v0.2.0. Inputs, outputs, example workflows, and security notes for running privileged containerlab labs in CI.
---

# GitHub Action

The action installs containerlab, installs Netdryrun™, runs your checks, writes a summary to the job page, uploads the JSON and JUnit reports as an artifact, and fails the job if any check fails.

```yaml title=".github/workflows/network-dryrun.yml"
name: Network dry run
on: pull_request
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.2.0
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
| `pr-comment` | `false` | On pull requests, post one comment with the verdict, failures first, and the evidence for each failed check. Updated in place on every push. Needs `permissions: pull-requests: write` |
| `github-token` | `${{ github.token }}` | Token used for the PR comment |
| `cloud` | `false` | Upload the evidence to Netdryrun Cloud (beta). Needs `permissions: id-token: write`; no secrets are configured |
| `cloud-url` | `https://cloud.netdryrun.com` | Netdryrun Cloud address |

## Outputs

| Output | Meaning |
|---|---|
| `status` | `passed`, `failed`, `error` or `inconclusive` (the lab never reached a testable state, so the run says nothing about the change; the job still fails) |
| `inconclusive-reason` | Why the run was inconclusive; empty otherwise |
| `passed` | Number of passed checks |
| `failed` | Number of failed checks |
| `evidence-url` | Link to the evidence page, when `cloud` is `true` |

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
      - uses: netdryrun/netdryrun@v0.2.0
        with:
          path: network/
```

### Use the outputs in a later step

```yaml
      - uses: netdryrun/netdryrun@v0.2.0
        id: ndr
        with:
          path: network/
      - if: always()
        run: echo "Netdryrun ${{ steps.ndr.outputs.status }}: ${{ steps.ndr.outputs.passed }} passed, ${{ steps.ndr.outputs.failed }} failed"
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
      - uses: netdryrun/netdryrun@v0.2.0
        with:
          path: ${{ matrix.lab }}
          artifact-name: netdryrun-${{ strategy.job-index }}
```

Give each matrix job its own `artifact-name`; artifact names must be unique within a workflow run.

### Comment the verdict on every pull request

```yaml
name: Network dry run
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  dryrun:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: netdryrun/netdryrun@v0.2.0
        with:
          path: network/
          pr-comment: true
```

## Security notes

- **A lab is code that runs as root on the runner.** containerlab starts privileged containers with access to the host. Netdryrun passes the lab process a minimal environment (no job tokens, not the runner user's home directory), but that only narrows exposure; it is not a security boundary.
- **Run labs from untrusted pull requests (forks) only in jobs with no secrets**, a read-only `GITHUB_TOKEN`, and without `id-token: write`. Never run them under `pull_request_target`.
- `pr-comment` needs `pull-requests: write`; `cloud` needs `id-token: write`. Grant each only when you use it.
- Uploaded report artifacts contain raw command output from the lab and are kept for 14 days. Don't put real secrets in lab configs.
