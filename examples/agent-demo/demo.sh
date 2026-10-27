#!/usr/bin/env bash
# Scripted replay of how an agent might work TICKET.md: a tempting first attempt, Netdryrun's
# verdict, then the fix. Runs on a scratch copy; nothing in this folder is modified.
# Exits 0 only if attempt 1 fails on exactly the leak guards (everything else passing) and
# attempt 2 passes every check.
#   Usage: examples/agent-demo/demo.sh     NDR=<netdryrun binary>  OUT=<folder for the JSON reports>
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
ndr="${NDR:-netdryrun}"
command -v "$ndr" >/dev/null || { echo "netdryrun not found (install it, or set NDR=/path/to/netdryrun)"; exit 2; }
command -v patch >/dev/null || { echo "the patch tool is required (apt install patch)"; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required"; exit 2; }
work="$(mktemp -d)" || { echo "mktemp failed"; exit 2; }
[ -n "$work" ] && [ -d "$work" ] || { echo "mktemp failed"; exit 2; }
trap 'rm -rf "$work"' EXIT
cp -r "$here/netdryrun.yml" "$here/topology.clab.yml" "$here/configs" "$work"/
out="${OUT:-$work/reports}"
mkdir -p "$out"

attempt() {  # attempt <n> <patch> <description>
  echo; echo "=== Attempt $1: $3"
  cp "$here/configs/edge1.conf" "$work/configs/edge1.conf"
  patch -s -p1 -d "$work" < "$here/changes/$2" || { echo "patch $2 did not apply"; exit 2; }
  sed -n '/^[-+][^-+]/p' "$here/changes/$2"
  echo
  "$ndr" run "$work" --json "$out/attempt-$1.report.json"
}

# Prints the names of the failed checks in a report, one per line.
failed_checks() {
  python3 -c 'import json,sys; [print(c["name"]) for c in json.load(open(sys.argv[1]))["checks"] if not c["passed"]]' "$1"
}

attempt 1 attempt-1-open-filters.diff "the prefix lists block the new block, so remove the filters"
rc1=$?
attempt 2 attempt-2-prefix-lists.diff "add the new block to the two prefix lists instead"
rc2=$?

echo
problems=()
[ "$rc1" -eq 1 ] || problems+=("attempt 1 exited $rc1, expected 1 (failed)")
[ "$rc2" -eq 0 ] || problems+=("attempt 2 exited $rc2, expected 0 (passed)")
if [ -f "$out/attempt-1.report.json" ]; then
  not_leaks="$(failed_checks "$out/attempt-1.report.json" | grep -v '^LEAK GUARD ' || true)"
  leaks="$(failed_checks "$out/attempt-1.report.json" | grep -c '^LEAK GUARD ' || true)"
  [ -z "$not_leaks" ] || problems+=("attempt 1 failed checks other than the leak guards: $(echo "$not_leaks" | paste -sd ';')")
  [ "$leaks" -ge 1 ] || problems+=("attempt 1 failed no leak guard")
else
  problems+=("attempt 1 wrote no report")
fi
if [ ${#problems[@]} -eq 0 ]; then
  echo "Demo OK: attempt 1 rejected by $leaks leak guards with every other check passing; attempt 2 passed every check."
else
  printf 'Demo FAILED: %s\n' "${problems[@]}"; exit 1
fi
