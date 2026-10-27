#!/usr/bin/env bash
# Replay of an AI agent working TICKET.md: a tempting first attempt, Netdryrun's verdict, then the fix.
# Runs on a scratch copy, so this folder is never modified. Exits 0 only if Netdryrun rejects
# attempt 1 and accepts attempt 2.   Usage: examples/agent-demo/demo.sh   (NDR=... to pick the binary)
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
ndr="${NDR:-netdryrun}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -r "$here"/. "$work"/

attempt() {  # attempt <n> <patch> <description>
  echo; echo "=== Attempt $1: $3"
  cp "$here/configs/edge1.conf" "$work/configs/edge1.conf"
  patch -s -p1 -d "$work" < "$here/changes/$2" || { echo "patch $2 did not apply"; exit 2; }
  sed -n '/^[-+][^-+]/p' "$here/changes/$2"
  echo
  "$ndr" run "$work" --json "$here/attempt-$1.report.json"
}

attempt 1 attempt-1-open-filters.diff "the prefix lists block the new block, so remove the filters"
rc1=$?
attempt 2 attempt-2-prefix-lists.diff "add the new block to the two prefix lists instead"
rc2=$?

echo
if [ "$rc1" -eq 1 ] && [ "$rc2" -eq 0 ]; then
  echo "Demo OK: attempt 1 rejected (exit $rc1), attempt 2 passed (exit $rc2)."
else
  echo "Demo FAILED: expected exit 1 then 0, got $rc1 then $rc2."; exit 1
fi
