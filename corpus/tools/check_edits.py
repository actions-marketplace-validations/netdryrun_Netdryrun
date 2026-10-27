"""Validate every case file and apply its edits to a scratch copy (no lab started).

Usage: python corpus/tools/check_edits.py [--corpus v2]
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run import CORPORA, CaseError, build_workdir, load_cases  # noqa: E402

corpus = CORPORA[sys.argv[2] if sys.argv[1:2] == ["--corpus"] else "v1"]
bad = 0
with tempfile.TemporaryDirectory() as tmp:
    for case in load_cases(None, corpus):
        try:
            build_workdir(case, Path(tmp), corpus)
            print(f"ok   {case['id']} ({case['expected']})")
        except CaseError as e:
            bad += 1
            print(f"FAIL {e}")
print(f"{bad} problem(s)")
sys.exit(1 if bad else 0)
