#!/usr/bin/env bash
# Run every example lab end to end and check each one's expected outcome.
# frr-bgp-broken contains a deliberate bad change and must FAIL.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
rc=0
for ex in examples/*/; do
  ex="${ex%/}"; name="${ex##*/}"
  expect=0; [[ "$name" == *broken* ]] && expect=1
  echo "### $name (expect exit $expect)"
  bash scripts/dev.sh run "$ex" --json "/tmp/ndr-$name.json" --no-step-summary | grep -E "PASS|FAIL|ERROR"
  got=${PIPESTATUS[0]}
  if [[ "$got" == "$expect" ]]; then echo "OK: exit $got"; else echo "MISMATCH: exit $got, expected $expect"; rc=1; fi
done
exit $rc
