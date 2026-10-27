"""The release gate's live layer must only ever remove labs we started (named ndr-*)."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_gate():
    spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["release_gate"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeLayer:
    def __init__(self):
        self.checks = []

    def add(self, id, title, severity, passed, notes="", *rest, **kw):
        self.checks.append((id, passed, notes))


def test_leftovers_fail_but_only_ours_are_removed(monkeypatch, tmp_path):
    gate = load_gate()
    removed = []
    monkeypatch.setattr(gate, "clab_containers",
                        lambda: {"clab-ndr-frr-bgp-r1", "clab-ospfv3-r1", "clab-already-r1"})
    monkeypatch.setattr(gate, "run", lambda cmd, **kw: removed.append(cmd[-1]))
    live = gate.Live(FakeLayer(), tmp_path)
    live.before = {"clab-already-r1"}

    assert live.assert_clean("case", "case") is False
    assert removed == ["clab-ndr-frr-bgp-r1"]          # someone else's new lab is reported, never touched
    (_, passed, notes), = live.layer.checks
    assert passed is False and "clab-ospfv3-r1" in notes and "clab-already-r1" not in notes


def test_every_shipped_topology_uses_our_prefix():
    gate = load_gate()
    prefix = gate.OUR_LAB_PREFIX.removeprefix("clab-")
    for p in [*ROOT.glob("examples/**/*.clab.yml"), *ROOT.glob("corpus/**/*.clab.yml")]:
        name = next((ln.split(":", 1)[1].strip() for ln in p.read_text(encoding="utf-8").splitlines()
                     if ln.startswith("name:")), "")
        assert name.startswith(prefix), p
