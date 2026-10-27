"""`netdryrun verify` end to end without a lab: the sides (directories and git refs), the topology rule,
node classification, the verdict statuses and exit codes, the guards, the report and its JSON Schema."""
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import pytest

from netdryrun import cli
from netdryrun.verify import report as vreport
from netdryrun.verify import run as vrun
from netdryrun.verify.converge import Inconclusive
from netdryrun.verify.snapshot import SnapshotError
from verify_helpers import add_new_customer_block, attrs, base

jsonschema = pytest.importorskip("jsonschema")
ROOT = Path(__file__).parents[1]
SCHEMA = json.loads((ROOT / "website/docs/schemas/verify-v1.json").read_text(encoding="utf-8"))

TOPO = """name: vlab
topology:
  defaults:
    kind: linux
    image: quay.io/frrouting/frr:10.4.1
    binds:
      - configs/daemons:/etc/frr/daemons
      - shared/vtysh.conf:/etc/frr/vtysh.conf
  nodes:
    cust1: {binds: [configs/cust1.conf:/etc/frr/frr.conf]}
    edge1: {binds: [configs/edge1.conf:/etc/frr/frr.conf]}
    up1: {binds: [configs/up1.conf:/etc/frr/frr.conf]}
    peer1: {binds: [configs/peer1.conf:/etc/frr/frr.conf]}
  links:
    - endpoints: ["edge1:eth1", "cust1:eth1"]
"""
GUARDS = """lab: topology.clab.yml
checks:
  - {type: bgp_session, node: edge1, neighbor: 10.0.1.2}
  - {type: route, node: peer1, prefix: 203.0.113.0/24, present: false}
"""


def validate(res) -> dict:
    data = json.loads(vreport.to_json(res))
    jsonschema.Draft202012Validator(SCHEMA).validate(data)
    return data


def make_lab(tmp_path: Path, topo: str = TOPO) -> Path:
    d = tmp_path / "lab"
    (d / "configs").mkdir(parents=True)
    (d / "shared").mkdir()
    (d / "topology.clab.yml").write_text(topo)
    (d / "shared" / "vtysh.conf").write_text("service integrated-vtysh-config\n")
    for f in ("daemons", "cust1.conf", "edge1.conf", "up1.conf", "peer1.conf"):
        (d / "configs" / f).write_text(f"! {f} before\n")
    return d


def side_dir(tmp_path: Path, lab: Path, name: str, edit: str | None = None) -> Path:
    d = tmp_path / name
    shutil.copytree(lab / "configs", d)
    if edit:
        (d / "edge1.conf").write_text(edit)
    return d


def intent_file(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "intent.yml"
    p.write_text(text)
    return p


def fake_side(before, after, guards=None, raise_on=None):
    calls = []

    def side(label, topology, on_up=None):
        folder = Path(topology).parent
        calls.append((label, {f.relative_to(folder).as_posix(): f.read_bytes()
                              for f in folder.rglob("*") if f.is_file()}))
        if raise_on == label:
            raise SnapshotError("unexpected output from `show bgp vrf all neighbors json`: unknown field(s) ['x']")
        snap = before if label == "before" else after
        return snap, 1.0, (guards if label == "after" else None)
    side.calls = calls
    return side


NEW_BLOCK = "intent:\n  - prefix: 10.101.0.0/24\n    appears_on: [edge1, up1, peer1]\n"


def run_verify(tmp_path, before_snap, after_snap, intent_text=NEW_BLOCK, guards=None, **kw):
    lab = make_lab(tmp_path)
    b = side_dir(tmp_path, lab, "before")
    a = side_dir(tmp_path, lab, "after", edit="! edge1 after\n")
    side = fake_side(before_snap, after_snap, guards=guards, raise_on=kw.pop("raise_on", None))
    kw.setdefault("config_dir_name", "configs")
    res = vrun.verify(str(lab / "topology.clab.yml"), str(b), str(a), str(intent_file(tmp_path, intent_text)),
                      side_fn=side, **kw)
    return res, side


# --- statuses and exit codes -------------------------------------------------------------------------------

def test_matched(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap())
    assert (res.status, res.exit_code) == ("matched", 0)
    data = validate(res)
    assert data["verdict"] == "INTENT MATCHED" and data["intent"]["lines"] and not data["undeclared"]
    assert data["evidence"]["before"]["schema"] == "netdryrun.snapshot/v1"
    assert [c[0] for c in side.calls] == ["before", "after"]
    # each side's lab folder holds the topology byte for byte, its own configs and the shared binds
    bfiles, afiles = side.calls[0][1], side.calls[1][1]
    assert afiles["configs/edge1.conf"] == b"! edge1 after\n"
    assert bfiles["configs/edge1.conf"] == b"! edge1.conf before\n"
    assert "shared/vtysh.conf" in afiles
    assert afiles["topology.clab.yml"] == bfiles["topology.clab.yml"] == TOPO.encode()


def test_undeclared_changes(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap(), intent_text="intent: []\n")
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["undeclared"]
    data = validate(res)
    assert data["verdict"] == "UNDECLARED CHANGES: DO NOT APPLY"
    for it in data["undeclared"]:
        assert it["next_diagnostic"].startswith("docker exec clab-vlab-") and "vtysh" in it["next_diagnostic"]
    assert {it["route_before"] for it in data["undeclared"] if it["kind"] == "rib"} == {"absent"}


def test_declared_but_did_not_happen(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap())
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["not_happened"]
    assert validate(res)["not_happened"][0]["intent"] == 0


def test_no_behavior_change(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(), intent_text="intent: []\n")
    assert (res.status, res.exit_code) == ("no_change", 0)
    assert validate(res)["verdict"] == "NO BEHAVIOR CHANGE"


def test_unreadable_snapshot_is_exit_2(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(), raise_on="after")
    assert (res.status, res.exit_code) == ("error", 2) and res.match is None
    assert validate(res)["error"]


def test_inconclusive_is_exit_3(tmp_path):
    inc = Inconclusive("kept moving", ["edge1 203.0.113.0/24 changed"])
    res, side = run_verify(tmp_path, inc, base().snap())
    assert (res.status, res.exit_code) == ("inconclusive", 3)
    assert [c[0] for c in side.calls] == ["before"]           # the after lab is not deployed
    data = validate(res)
    assert data["inconclusive"]["side"] == "before" and data["inconclusive"]["moving"]


def test_unhealthy_baseline(tmp_path):
    from verify_helpers import session
    lab = base()
    lab.session("edge1", "10.0.9.2", session(None, state="active"))
    res, side = run_verify(tmp_path, lab.snap(), base().snap())
    assert (res.status, res.exit_code) == ("unhealthy_baseline", 3) and res.baseline_problems
    assert [c[0] for c in side.calls] == ["before"]
    validate(res)
    after = add_new_customer_block(lab.copy())
    res, _ = run_verify(tmp_path / "again", lab.snap(), after.snap(), allow_unhealthy_baseline=True)
    assert res.status == "matched" and res.baseline_overridden
    assert validate(res)["baseline"] == {"healthy": False, "problems": res.baseline_problems, "overridden": True}


def test_failed_guards_fail_a_matched_intent(tmp_path):
    """A dishonest intent can explain a leak; the standing guards (from the base) still fail it."""
    guards = {"status": "failed", "passed": 1, "failed": 1, "error": None, "source": "netdryrun.yml at main",
              "failures": [{"check": "LEAK GUARD", "node": "peer1", "reason": "route present"}]}
    after = base()
    after.adj_out("edge1", "10.0.3.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    after.learn("peer1", "203.0.113.0/24", "10.0.3.1", "65000 65002")
    res, _ = run_verify(tmp_path, base().snap(), after.snap(), guards=guards,
                        intent_text="intent:\n  - {prefix: 203.0.113.0/24, appears_on: [peer1]}\n")
    assert (res.status, res.exit_code) == ("failed", 1) and res.failed_because == ["guards"]
    assert validate(res)["guards"]["failed"] == 1


@pytest.mark.parametrize("gstatus,status", [("error", "error"), ("inconclusive", "inconclusive")])
def test_guards_without_a_verdict_leave_no_verdict(tmp_path, gstatus, status):
    guards = {"status": gstatus, "passed": 0, "failed": 0, "error": "lab problem", "failures": []}
    res, _ = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap(), guards=guards)
    assert res.status == status
    validate(res)


def test_allow_anywhere_warns(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), base().snap(),
                        intent_text="intent: []\nallow_anywhere: ['10.200.*.0/24']\n")
    assert res.status == "no_change" and res.warnings == [vreport.ALLOW_WARNING]


def test_bad_intent_is_exit_2(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), base().snap(), intent_text="intent:\n  - prefix: nope\n")
    assert (res.status, res.exit_code) == ("error", 2) and not side.calls
    assert validate(res)["intent"] is None


def test_unknown_node_in_the_intent_is_exit_2(tmp_path):
    res, side = run_verify(tmp_path, base().snap(), base().snap(),
                           intent_text="intent:\n  - {prefix: 10.1.0.0/24, appears_on: [r9]}\n")
    assert res.exit_code == 2 and not side.calls


# --- sides and the topology rule ---------------------------------------------------------------------------

def test_config_dir_detection(tmp_path):
    lab = make_lab(tmp_path)
    topo = lab / "topology.clab.yml"
    with pytest.raises(vrun.VerifyInputError):           # configs/ and shared/
        vrun.config_dir(topo, None)
    assert vrun.config_dir(topo, "configs") == PurePosixPath("configs")
    topo.write_text(TOPO.replace("shared/vtysh.conf", "configs/vtysh.conf"))
    assert vrun.config_dir(topo, None) == PurePosixPath("configs")
    assert vrun.config_dir(ROOT / "examples/agent-demo/topology.clab.yml", None) == PurePosixPath("configs")
    for bad in ("../x", "/etc"):
        with pytest.raises(vrun.VerifyInputError):
            vrun.config_dir(topo, bad)


def test_a_side_missing_a_bound_file_is_an_error(tmp_path):
    lab = make_lab(tmp_path)
    side = side_dir(tmp_path, lab, "before")
    (side / "up1.conf").unlink()
    with pytest.raises(vrun.VerifyInputError):
        vrun.materialize(str(side), "before", lab / "topology.clab.yml", PurePosixPath("configs"), tmp_path / "w")


def test_a_side_that_is_neither_a_directory_nor_a_ref(tmp_path):
    lab = make_lab(tmp_path)
    git(lab, "init", "-q")
    with pytest.raises(vrun.VerifyInputError):
        vrun.materialize("no-such-ref", "before", lab / "topology.clab.yml", PurePosixPath("configs"), tmp_path / "w")


def git(cwd: Path, *args: str) -> str:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    p = subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false",
                        *args], cwd=cwd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def repo_lab(tmp_path: Path) -> Path:
    lab = make_lab(tmp_path)
    (lab / "netdryrun.yml").write_text(GUARDS)
    git(lab, "init", "-q")
    git(lab, "add", ".")
    git(lab, "commit", "-q", "-m", "base")
    return lab


def test_git_ref_side(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / "configs" / "edge1.conf").write_text("! edge1 after\n")
    topo, desc, tree = vrun.materialize("HEAD", "before", lab / "topology.clab.yml", PurePosixPath("configs"),
                                        tmp_path / "w")
    assert "git ref HEAD" in desc and (topo.parent / "configs" / "edge1.conf").read_text() == "! edge1.conf before\n"
    assert topo.read_bytes() == (lab / "topology.clab.yml").read_bytes()


def test_topology_changed_since_the_ref_is_exit_2(tmp_path):
    lab = repo_lab(tmp_path)
    (lab / "topology.clab.yml").write_text(TOPO + "    - endpoints: [\"edge1:eth2\", \"up1:eth1\"]\n")
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD", str(lab / "configs"),
                      str(intent_file(tmp_path, "intent: []\n")), config_dir_name="configs",
                      side_fn=fake_side(base().snap(), base().snap()))
    assert (res.status, res.exit_code) == ("error", 2)
    validate(res)
    code = cli.main(["verify", str(lab / "topology.clab.yml"), "--before", "HEAD", "--after", str(lab / "configs"),
                     "--intent", str(tmp_path / "intent.yml"), "--config-dir", "configs"])
    assert code == 2


def test_guards_are_read_from_the_before_ref(tmp_path, monkeypatch):
    lab = repo_lab(tmp_path)
    # the change weakens the guards in the working tree: verify must ignore that
    (lab / "netdryrun.yml").write_text("lab: topology.clab.yml\nchecks:\n  - {type: bgp_session, node: edge1, neighbor: 10.0.1.2}\n")
    seen = {}

    def fake_guards(cfg, topology, settle, hold, log):
        seen["checks"] = len(cfg.checks)
        return {"status": "passed", "passed": len(cfg.checks), "failed": 0, "error": None, "failures": []}
    monkeypatch.setattr(vrun, "run_guards", fake_guards)

    def side(label, topology, on_up=None):
        extra = on_up(None, topology) if on_up else None
        return (base().snap(), 1.0, extra)
    res = vrun.verify(str(lab / "topology.clab.yml"), "HEAD", str(lab / "configs"),
                      str(intent_file(tmp_path, "intent: []\n")), config_dir_name="configs",
                      guards=str(lab / "netdryrun.yml"), side_fn=side)
    assert res.status == "no_change", res.error
    assert seen["checks"] == 2 and res.guards["source"] == "netdryrun.yml at HEAD"
    validate(res)


# --- nodes -------------------------------------------------------------------------------------------------

def test_node_classification(tmp_path):
    from netdryrun.lab import Lab
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  nodes:\n    r1: {kind: linux, image: quay.io/frrouting/frr:10.4.1}\n"
                    "    h1: {kind: linux, image: alpine:3}\n    br: {kind: bridge}\n"
                    "    s1: {kind: nokia_srlinux, image: ghcr.io/nokia/srlinux}\n")
    lab = Lab(topo)
    with pytest.raises(vrun.VerifyInputError):           # h1 can't be classified
        vrun.classify_nodes(lab, {}, [])
    with pytest.raises(vrun.VerifyInputError):           # s1 is SR Linux: FRR only in 0.4
        vrun.classify_nodes(lab, {}, ["h1"])
    assert vrun.classify_nodes(lab, {}, ["h1", "s1"]) == {"r1": "frr", "h1": "", "br": "", "s1": ""}
    assert vrun.classify_nodes(lab, {"h1": "frr"}, ["s1"])["h1"] == "frr"
    with pytest.raises(vrun.VerifyInputError):
        vrun.classify_nodes(lab, {}, ["h1", "s1", "zz"])


# --- CLI ---------------------------------------------------------------------------------------------------

def test_cli_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    out = tmp_path / "r.json"
    for status in ("matched", "no_change", "failed", "error", "inconclusive", "unhealthy_baseline"):
        res = vreport.VerifyResult(status=status, run_id="x")
        monkeypatch.setattr(vrun, "verify", lambda *a, _r=res, **k: _r)
        code = cli.main(["verify", "t.yml", "--before", "a", "--after", "b", "--intent", "i.yml", "--json", str(out)])
        assert code == vreport.EXIT_CODES[status]
        jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out.read_text()))
    assert "INCONCLUSIVE" in capsys.readouterr().out


def test_cli_bad_intent_is_exit_2(tmp_path):
    lab = make_lab(tmp_path)
    code = cli.main(["verify", str(lab / "topology.clab.yml"), "--before", str(lab / "configs"), "--after",
                     str(lab / "configs"), "--intent", str(intent_file(tmp_path, "intent: {}\n"))])
    assert code == 2


def test_console_echoes_the_intent_first(tmp_path):
    res, _ = run_verify(tmp_path, base().snap(), add_new_customer_block(base()).snap())
    lines = vreport.console(res).splitlines()
    assert lines[0] == "verify: INTENT MATCHED" and lines[1].startswith("Intent (")


def test_schema_is_valid():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["properties"]["schema"]["const"] == vreport.SCHEMA
