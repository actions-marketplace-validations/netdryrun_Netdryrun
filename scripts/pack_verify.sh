#!/usr/bin/env bash
# Run the isp-edge-guard pack against every corpus case (writes VERIFICATION.md in the pack folder).
cd "$(dirname "$0")/.." || exit 2
NDR_BIN=python bash scripts/dev.sh "/mnt/c/NetCL Business/packs/isp-edge-guard/verify_against_corpus.py" "$PWD/corpus"
