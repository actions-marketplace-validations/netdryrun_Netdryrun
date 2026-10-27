#!/usr/bin/env bash
# Independent rerun for the grader: copy an agent's final folder to /tmp, give the lab a unique name,
# append the hidden checks, run Netdryrun, print the JSON report on one line after "REPORT ".
#   grade_rerun.sh <folder> <label> <extra checks as JSON list> <netdryrun binary>
set -u
src="$1"; label="$2"; extra="$3"; ndr="$4"
work="/tmp/ndr-grade/$label"
rm -rf "$work"; mkdir -p "$work"
cp -r "$src"/. "$work"/
find "$work" -type f -exec sed -i 's/\r$//' {} +
rm -rf "$work"/clab-* "$work"/netdryrun-report.json
sed -i "s/^name: .*/name: ndr-grade-$label/" "$work/topology.clab.yml"
"$(dirname "$ndr")/python" - "$work/netdryrun.yml" "$extra" <<'PY'
import json, sys, yaml
p, extra = sys.argv[1], json.loads(sys.argv[2])
cfg = yaml.safe_load(open(p))
cfg["checks"] = (cfg.get("checks") or []) + extra
yaml.safe_dump(cfg, open(p, "w"), sort_keys=False)
PY
cd "$work" && "$ndr" run . --json "$work/grade-report.json"
rc=$?
echo "REPORT $(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))))' "$work/grade-report.json" 2>/dev/null || echo '{}')"
exit $rc
