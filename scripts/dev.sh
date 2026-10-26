#!/usr/bin/env bash
# Dev helper for WSL: ./scripts/dev.sh <netdryrun args...>
# Creates a venv on the Linux filesystem with an editable install, then runs the CLI.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
here="$(cd "$(dirname "$0")/.." && pwd)"
venv="$HOME/.venvs/netdryrun"
if [ ! -x "$venv/bin/netdryrun" ]; then
  uv venv -q "$venv"
  VIRTUAL_ENV="$venv" uv pip install -q -e "$here[dev]"
fi
cd "$here"
exec "$venv/bin/${NDR_BIN:-netdryrun}" "$@"
