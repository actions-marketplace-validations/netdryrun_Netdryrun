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
    ok = {"reason": "r", "diff": fp, "class": "logging"}
    assert gate.accepted_now({name: ok}, name, diffs)
    assert not gate.accepted_now({name: "old format, no fingerprint"}, name, diffs)
    assert not gate.accepted_now({name: {**ok, "diff": "0" * 16}}, name, diffs)   # renumbered: a different mutant
    assert not gate.accepted_now({}, name, diffs)
    assert not gate.accepted_now({name: ok}, name, {})                             # no diff seen


def test_reason_reads_both_formats():
    assert gate.reason("text") == "text"
    assert gate.reason({"reason": "text", "diff": "x"}) == "text"


# ------------------------------------------------------------- classed acceptances (RELEASE-GATE.md Layer 4, 2026-10-28)

def test_an_acceptance_needs_one_of_the_fixed_classes():
    name = "netdryrun.config.x__describe__mutmut_1"
    fp = gate.mutant_fingerprint(DIFF)
    for cls in gate.ACCEPT_CLASSES:
        assert gate.accepted_now({name: {"reason": "r", "diff": fp, "class": cls}}, name, {name: DIFF}), cls
    assert not gate.accepted_now({name: {"reason": "r", "diff": fp}}, name, {name: DIFF})
    assert not gate.accepted_now({name: {"reason": "r", "diff": fp, "class": "harmless"}}, name, {name: DIFF})
    assert "class" in gate.acceptance_problem({"reason": "r", "diff": fp}, name, {name: DIFF})


def test_a_verdict_function_survivor_needs_an_argument_checked_by_the_adversarial_reviewer():
    name = "netdryrun.runner.x__bgp_convergence_gate__mutmut_7"
    assert gate.mutant_function(name) in gate.VERDICT_FUNCTIONS
    fp = gate.mutant_fingerprint(DIFF)
    base = {"reason": "r", "diff": fp, "class": "message-text"}
    assert not gate.accepted_now({name: base}, name, {name: DIFF})
    assert not gate.accepted_now({name: {**base, "argument": "why"}}, name, {name: DIFF})         # not reviewed
    assert not gate.accepted_now({name: {**base, "reviewed": "adversarial"}}, name, {name: DIFF})  # no argument
    assert gate.accepted_now({name: {**base, "argument": "why", "reviewed": "adversarial: ref"}}, name, {name: DIFF})
    assert "argument" in gate.acceptance_problem({name: base}[name], name, {name: DIFF})


def test_the_verdict_functions_exist():
    import ast
    src = ROOT / "src" / "netdryrun"
    found = set()
    for mod in ("checks", "runner"):
        for node in ast.walk(ast.parse((src / f"{mod}.py").read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                found |= {f"{mod}.{node.name}.{f.name}" for f in node.body if isinstance(f, ast.FunctionDef)}
            elif isinstance(node, ast.FunctionDef):
                found.add(f"{mod}.{node.name}")
    assert gate.VERDICT_FUNCTIONS <= found, sorted(gate.VERDICT_FUNCTIONS - found)


def test_accepted_counts_by_class():
    names = ["netdryrun.config.x_a__mutmut_1", "netdryrun.config.x_a__mutmut_2", "netdryrun.config.x_b__mutmut_1"]
    fp = gate.mutant_fingerprint(DIFF)
    acc = {names[0]: {"reason": "r", "diff": fp, "class": "logging"},
           names[1]: {"reason": "r", "diff": fp, "class": "equivalent"},
           names[2]: {"reason": "r", "diff": fp, "class": "logging"}}
    assert gate.accepted_by_class(acc, names, {n: DIFF for n in names}) == {"logging": 2, "equivalent": 1}


# ------------------------------------------- false passes on their own line (RELEASE-GATE.md Layer 5, 2026-10-28)

def _case(cid, expected, verdict):
    return {"id": cid, "expected": expected, "strategies": {"netdryrun": {"verdict": verdict}}}


def test_harmful_changes_approved_are_listed_by_case():
    cases = [_case("01", "safe", "safe"), _case("18", "harmful", "safe"), _case("23", "harmful", "safe"),
             _case("05", "harmful", "harmful"), _case("06", "safe", "harmful")]
    assert gate.harmful_approved(cases) == ["18", "23"]


def test_a_new_harmful_approval_blocks_even_when_the_score_rose():
    published = [_case("18", "harmful", "safe"), _case("23", "harmful", "safe"), _case("06", "safe", "harmful")]
    rerun = [_case("18", "harmful", "harmful"), _case("23", "harmful", "safe"), _case("06", "safe", "safe"),
             _case("30", "harmful", "safe")]   # two more right, but 30 is a new false pass
    ok, summary = gate.harmful_approved_check(published, rerun)
    assert not ok and "30" in summary and "new" in summary
    ok, summary = gate.harmful_approved_check(published, published)
    assert ok and "18, 23" in summary
