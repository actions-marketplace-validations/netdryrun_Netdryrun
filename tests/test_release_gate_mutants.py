"""Accepted mutants are pinned to their diff, so a renumbered mutant ID can't inherit someone else's acceptance."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)

DIFF = """--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -40,7 +40,7 @@
     for d in done:
-        if d.rc == 0:
+        if d.rc != 0:
             ok += 1
"""


def test_fingerprint_ignores_line_numbers_and_headers():
    moved = DIFF.replace("@@ -40,7 +40,7 @@", "@@ -88,7 +88,7 @@")
    assert gate.mutant_fingerprint(DIFF) == gate.mutant_fingerprint(moved)


def test_fingerprint_changes_with_the_mutation():
    other = DIFF.replace("+        if d.rc != 0:", "+        if d.rc == 1:")
    assert gate.mutant_fingerprint(DIFF) != gate.mutant_fingerprint(other)


def test_only_a_pinned_matching_entry_is_accepted():
    name = "netdryrun.runner.x_run__mutmut_225"
    diffs = {name: DIFF}
    fp = gate.mutant_fingerprint(DIFF)
    assert gate.accepted_now({name: {"reason": "r", "diff": fp}}, name, diffs)
    assert not gate.accepted_now({name: "old format, no fingerprint"}, name, diffs)
    assert not gate.accepted_now({name: {"reason": "r", "diff": "0" * 16}}, name, diffs)   # renumbered: a different mutant
    assert not gate.accepted_now({}, name, diffs)
    assert not gate.accepted_now({name: {"reason": "r", "diff": fp}}, name, {})            # no diff seen


def test_reason_reads_both_formats():
    assert gate.reason("text") == "text"
    assert gate.reason({"reason": "text", "diff": "x"}) == "text"
