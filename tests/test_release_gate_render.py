"""GATE.md verdicts: accepted MAJOR checks, and the state between the pre-publish layers and the proof."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)


def record(name, checks):
    return {"title": gate.LAYERS[name], "git": {"sha": "a", "branch": "b", "dirty": False}, "started": "now",
            "seconds": 1, "host": "h", "python": "3", "tools": {}, "sections": [],
            "checks": [{"id": i, "title": i, "severity": sev, "status": st, "summary": "", "output": "",
                        "seconds": 0, "command": ""} for i, sev, st in checks]}


def write(tmp_path, layers, accepted=None, review=True):
    for name, checks in layers.items():
        (tmp_path / "gate").mkdir(exist_ok=True)
        (tmp_path / "gate" / f"{name}.json").write_text(json.dumps(record(name, checks)))
    if accepted is not None:
        (tmp_path / "accepted.json").write_text(json.dumps({"checks": accepted}))
    if review:
        (tmp_path / "review.md").write_text("review")
    return SimpleNamespace(out=str(tmp_path), version="9.9.9")


PRE = {"static": [("s", "BLOCKER", "PASS")], "unit": [("u", "BLOCKER", "PASS")], "mutation": [("m", "BLOCKER", "PASS")]}


def test_a_skipped_major_can_be_accepted(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("pack", "MAJOR", "SKIP")], "after-publish": [("p", "BLOCKER", "PASS")]},
                 accepted={"live/pack": "not sold yet"})
    text, cleared = gate.render(args)
    assert cleared, text
    assert "not sold yet" in text


def test_a_skipped_major_without_acceptance_blocks(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("pack", "MAJOR", "SKIP")], "after-publish": [("p", "BLOCKER", "PASS")]})
    text, cleared = gate.render(args)
    assert not cleared
    assert "live/pack" in text


def test_a_skipped_blocker_cannot_be_accepted(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("x", "BLOCKER", "SKIP")], "after-publish": [("p", "BLOCKER", "PASS")]},
                 accepted={"live/x": "please"})
    text, cleared = gate.render(args)
    assert not cleared
    assert "BLOCKER checks skipped" in text


def test_ready_to_publish_when_only_the_proof_is_missing(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("l", "BLOCKER", "PASS")]})
    text, cleared = gate.render(args)
    assert not cleared
    assert "**READY TO PUBLISH**" in text


def test_not_ready_without_the_review(tmp_path):
    args = write(tmp_path, {**PRE, "live": [("l", "BLOCKER", "PASS")]}, review=False)
    text, _ = gate.render(args)
    assert "**INCOMPLETE**" in text


def test_not_ready_when_a_pre_publish_layer_is_missing(tmp_path):
    args = write(tmp_path, PRE)
    text, _ = gate.render(args)
    assert "**INCOMPLETE**" in text
