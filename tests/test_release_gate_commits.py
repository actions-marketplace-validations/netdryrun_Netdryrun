"""Gate layers may differ only in the gate's records or in prose, and only if static ran on the newest commit."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
gate = importlib.util.module_from_spec(spec)
sys.modules["release_gate"] = gate
spec.loader.exec_module(gate)


def fake_git(ancestors: set, diffs: dict):
    def git(*args):
        if args[0] == "merge-base":
            return "" if (args[2], args[3]) in ancestors else None
        if args[0] == "diff":
            return diffs[(args[2], args[3])]
        raise AssertionError(args)
    return git


def test_prose_only():
    for p in ("README.md", "CHANGELOG.md", "advisories/x/README.md", "website/docs/reference/cli.md",
              "website/docs/llms-full.txt"):
        assert gate.prose_only(p), p
    for p in ("src/netdryrun/runner.py", "tests/README.md", "scripts/x.md", ".github/workflows/ci.yml",
              "advisories/x/1.yml", "website/mkdocs.yml", "pyproject.toml"):
        assert not gate.prose_only(p), p


def test_same_commit_is_fine():
    assert gate.code_differs({"static": "a", "unit": "a", "live": "a"}) is None


def test_prose_change_after_the_code_layers_is_allowed_when_static_is_newest(monkeypatch):
    monkeypatch.setattr(gate, "git", fake_git({("old", "new")}, {("old", "new"): "README.md\nCHANGELOG.md\nreleases/0.3.1/GATE.md"}))
    assert gate.code_differs({"static": "new", "unit": "old", "mutation": "old", "live": "old"}) is None


def test_code_change_between_layers_blocks(monkeypatch):
    monkeypatch.setattr(gate, "git", fake_git({("old", "new")}, {("old", "new"): "README.md\nsrc/netdryrun/runner.py"}))
    assert "different code" in gate.code_differs({"static": "new", "mutation": "old"})


def test_static_must_be_the_newest(monkeypatch):
    monkeypatch.setattr(gate, "git", fake_git(set(), {}))
    assert "not an ancestor" in gate.code_differs({"static": "old", "live": "new"})


def test_missing_static_record_blocks():
    assert "static layer" in gate.code_differs({"unit": "a", "live": "b"})
