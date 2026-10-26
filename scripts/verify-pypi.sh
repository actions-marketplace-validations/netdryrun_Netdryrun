#!/usr/bin/env bash
# Install netdryrun from PyPI into a throwaway venv and smoke-test the CLI and MCP entry points.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
uv venv -q "$tmp/venv"
VIRTUAL_ENV="$tmp/venv" uv pip install -q --refresh "netdryrun[mcp]==${1:-0.1.0}"
"$tmp/venv/bin/netdryrun" --version
"$tmp/venv/bin/netdryrun" validate examples/frr-bgp
"$tmp/venv/bin/python" -c "import netdryrun.mcp_server as m; print('mcp server import ok:', m.mcp.name)"
rm -rf "$tmp"
