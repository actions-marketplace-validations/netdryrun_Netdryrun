# Security policy

Report vulnerabilities privately to **security@netdryrun.com**, or through GitHub's private vulnerability reporting on this repository. Please don't open public issues for security problems.

We aim to acknowledge reports within 3 days and to fix confirmed issues in the next release.

## What Netdryrun does and doesn't do

- It **never connects to production devices.** It only builds and tests containerlab labs on the machine it runs on.
- **A lab is code.** containerlab starts privileged containers, so only run topologies you trust, on a machine you'd let run Docker.
- The GitHub Action runs the lab as root on the runner. It passes Netdryrun a minimal environment (no job tokens, not the runner user's home), but that is **not a security boundary**: a lab runs privileged containers and could read the runner. **Run labs from untrusted pull requests only in jobs that hold no secrets**, with a read-only `GITHUB_TOKEN`, and never with `pull_request_target`.
- MCP tool results contain normalized check results, not raw device output, to limit prompt-injection through lab content.
- Evidence reports contain raw command output from the lab. Treat them like logs: don't upload them publicly if your configs contain secrets.
