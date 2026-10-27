#!/usr/bin/env bash
# Run a check pack's verifier against every corpus case (the verifier writes VERIFICATION.md in the pack folder).
# Usage: scripts/pack_verify.sh PATH/TO/verify_against_corpus.py
set -euo pipefail
verifier="${1:?usage: scripts/pack_verify.sh PATH/TO/verify_against_corpus.py}"
verifier="$(cd "$(dirname "$verifier")" && pwd)/$(basename "$verifier")"
cd "$(dirname "$0")/.." || exit 2
NDR_BIN=python bash scripts/dev.sh "$verifier" "$PWD/corpus"
