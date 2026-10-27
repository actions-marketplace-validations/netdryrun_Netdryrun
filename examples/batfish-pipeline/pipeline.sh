#!/usr/bin/env bash
# Two-stage gate for a config change: Batfish analyses the configs (nothing boots), then
# Netdryrun boots them in a containerlab lab and checks what the routers really do.
# Runs on a scratch copy; nothing in this folder is modified.
#   Usage: examples/batfish-pipeline/pipeline.sh [CHANGE]
#     CHANGE      a file in changes/ (without .conf) that replaces r2.conf; none = the baseline configs
#   Environment:
#     BF_PYTHON   Python with pybatfish (default python3); BATFISH_HOST, BATFISH_PORT (default localhost, 9996)
#     NDR         netdryrun binary (default netdryrun)
#     BOTH=1      run the lab even when Batfish fails (to compare the two stages)
#     OUT         folder for the Netdryrun JSON report (default batfish-pipeline-reports in the current folder)
# Exit codes: 0 both stages passed, 1 a stage failed, 2 setup error, 3 the lab run was inconclusive.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
change="${1:-}"
py="${BF_PYTHON:-python3}"
ndr="${NDR:-netdryrun}"
command -v "$ndr" >/dev/null || { echo "netdryrun not found (install it, or set NDR=/path/to/netdryrun)"; exit 2; }
work="$(mktemp -d)" || { echo "mktemp failed"; exit 2; }
if [ -z "$work" ] || [ ! -d "$work" ]; then echo "mktemp failed"; exit 2; fi
trap 'rm -rf "$work"' EXIT
cp -r "$here/netdryrun.yml" "$here/topology.clab.yml" "$here/configs" "$work"/
if [ -n "$change" ]; then
  [ -f "$here/changes/$change.conf" ] || { echo "no such change: changes/$change.conf"; exit 2; }
  cp "$here/changes/$change.conf" "$work/configs/r2.conf"
fi
out="${OUT:-batfish-pipeline-reports}"
mkdir -p "$out"

echo "=== Stage 1: Batfish (config analysis)${change:+, change: $change}"
t0=$SECONDS
"$py" "$here/batfish_check.py" "$work/configs"
bf=$?
echo "Stage 1 exit $bf after $((SECONDS - t0))s"
[ "$bf" -eq 2 ] && exit 2
if [ "$bf" -ne 0 ] && [ "${BOTH:-0}" != 1 ]; then
  echo "Batfish failed: the lab is not started."; exit 1
fi

echo; echo "=== Stage 2: Netdryrun (containerlab lab)"
t1=$SECONDS
"$ndr" run "$work" --json "$out/${change:-baseline}.report.json"
nd=$?
echo "Stage 2 exit $nd after $((SECONDS - t1))s; JSON report: $out/${change:-baseline}.report.json"
[ "$nd" -eq 0 ] && [ "$bf" -eq 0 ] && exit 0
[ "$nd" -ge 2 ] && exit "$nd"
exit 1
