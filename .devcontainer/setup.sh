#!/usr/bin/env bash
# Runs once when the devcontainer is created: installs Netdryrun from this checkout and pulls
# the FRR image the examples use, so the first demo run doesn't wait for a download.
set -euo pipefail
cd "$(dirname "$0")/.."

pip install --no-cache-dir -e .
netdryrun --version

# The Docker-in-Docker daemon starts with the container; give it a moment.
for _ in $(seq 60); do docker info >/dev/null 2>&1 && break; sleep 1; done
docker pull quay.io/frrouting/frr:10.4.1

containerlab version | grep -i version
echo
echo "Ready. Try: bash examples/agent-demo/demo.sh"
