"""Validate every case file and apply its edits to a scratch copy (no lab started)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run import CaseError, build_workdir, load_cases  # noqa: E402

bad = 0
with tempfile.TemporaryDirectory() as tmp:
    for case in load_cases(None):
        try:
            build_workdir(case, Path(tmp))
            print(f"ok   {case['id']} ({case['expected']})")
        except CaseError as e:
            bad += 1
            print(f"FAIL {e}")
print(f"{bad} problem(s)")
sys.exit(1 if bad else 0)
