# Netdryrun v0.1 design

## Goal
Test a proposed network change in a real virtual lab before it reaches production, and produce evidence a reviewer can trust. v0.1 targets engineers who keep configs in Git and use containerlab.

## Flow
`netdryrun run [dir]`:
1. Load `netdryrun.yml` (lab path, defaults, checks). Strict validation, clear errors.
2. Deploy the containerlab topology (lab state kept on a Linux filesystem; WSL users on /mnt/c otherwise break SR Linux).
3. Run checks:
   - **Positive checks** (session established, prefix count in range, route present, ping succeeds) are polled until they pass or time out, because networks need time to converge.
   - **Negative checks** (route absent, ping must fail) run only after all positive checks finish plus a settle delay, and must hold across a short window. Otherwise "route absent" passes at second 0 before BGP even converged (a false pass).
4. Report: console summary, JSON evidence file (every command run, raw output, timestamps, tool and image versions), Markdown for the PR / `$GITHUB_STEP_SUMMARY`, JUnit XML for CI.
5. Destroy the lab (unless `--keep`). Exit code: 0 all passed, 1 a check failed, 2 config/lab error, 3 inconclusive (the lab never reached a testable state; rules in checks.inconclusive_reason).

## Drivers (normalize device state)
| Driver | Source of truth | Notes |
|---|---|---|
| FRR | `vtysh -c "... json"` | accepted prefixes = `acceptedPrefixCounter` |
| SR Linux | `sr_cli --output-format json "info from state ..."` | accepted = received - rejected; ping via `ip netns exec srbase-<ni>` |
Driver auto-detected from topology kind/image, overridable per node.

## Check types (v0.1)
`bgp_session`, `bgp_prefixes`, `route` (present/absent, optional protocol), `ping` (success/failure, optional source). Each has optional `vrf`, `timeout`, `name`.

## GitHub Action
Composite action: install containerlab, pip install netdryrun, run, write the Markdown summary, upload the evidence JSON as an artifact, fail the job on failed checks.

## Out of scope for v0.1
Vendor images (bring your own later), config diff-driven test selection, PR comments, hosted runs, the paid tier.
