"""A config line FRR rejects at boot is skipped: the lab runs without it, so a check can pass on a change that never
loaded (found in 0.3.2 by the 0.4 session: `default-orignate`). After the checks, each FRR node's boot log is read,
and any line vtysh rejected makes the run an error (exit 2), never a pass.

The fixtures are `docker logs` of quay.io/frrouting/frr:10.4.1 started privileged, as containerlab starts it, with
examples/frr-bgp/configs/r1.conf plus three bad lines (frr_boot_log_rejected.conf, lines 21-23), and with the clean
r1.conf: captured 2026-10-29."""
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.drivers import frr
from netdryrun.lab import ExecResult, Node

from test_runner_robustness import ALWAYS, FakeDriver, FakeLab, World, cfg, install

FIX = Path(__file__).parent / "fixtures"
REJECTED = (FIX / "frr_boot_log_rejected.txt").read_text(encoding="utf-8")
CLEAN = (FIX / "frr_boot_log_clean.txt").read_text(encoding="utf-8")


def test_the_rejected_lines_are_read_from_a_real_boot_log():
    found = frr.parse_config_load_errors(REJECTED)
    assert found == [
        "line 21: neighbor 10.0.12.2 default-orignate (Unknown command)",
        "line 22: neighbor 10.0.12.2 maximum-prefix (Command incomplete)",
        "line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected by bgpd)",
    ]
    assert frr.parse_config_load_errors(CLEAN) == []


@pytest.mark.parametrize("text, expected", [
    ("line 7: % Ambiguous command[4]: ip ro\n", ["line 7: ip ro (Ambiguous command)"]),
    ("line 7: % Unknown command: foo\n", ["line 7: foo (Unknown command)"]),   # FRR without the node number
    ("line 9: Warning[31]...:   neighbor 1.2.3.4 shutdown\n", ["line 9: neighbor 1.2.3.4 shutdown (warning)"]),
    ("line 3: Warning[4]...: early exit from config file\n", ["line 3: early exit from config file (warning)"]),
    ("[45|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 13\n",
     ["bgpd reported a configuration file processing failure (13)"]),
])
def test_every_vtysh_load_error_form_counts(text, expected):
    assert frr.parse_config_load_errors(text) == expected


class BootLogLab(FakeLab):
    def __init__(self, world, logs: dict, images: dict | None = None):
        super().__init__(world)
        self.logs, self.read = logs, []
        for n, image in (images or {}).items():
            self.nodes[n] = Node(n, f"clab-t-{n}", "linux" if "frr" in image else "ceos", image)

    def boot_log(self, node):
        self.read.append(node)
        log = self.logs.get(node, CLEAN)
        return log if isinstance(log, ExecResult) else ExecResult([], 0, log, "")


def _run(tmp_path, monkeypatch, lab, deploy=False):
    w = lab.world
    install(monkeypatch, w, lab, {n: FakeDriver(w) for n in ("r1", "r2", "r3")})
    return runner.run(cfg(tmp_path, [ALWAYS]), deploy=deploy, settle=0, hold=3)


def test_a_clean_boot_still_passes(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and sorted(lab.read) == ["r1", "r2", "r3"]


@pytest.mark.parametrize("deploy", [True, False])
def test_a_rejected_line_on_any_frr_node_makes_the_run_an_error(tmp_path, monkeypatch, deploy):
    # r2 has no check at all: the line it rejected can still change what r3 sees
    lab = BootLogLab(World(), {"r2": REJECTED})
    rep = _run(tmp_path, monkeypatch, lab, deploy=deploy)
    assert rep.status == "error" and rep.exit_code == 2
    assert all(r.passed for r in rep.results)   # the checks passed: on a lab without the change
    assert "r2" in rep.error and "line 21: neighbor 10.0.12.2 default-orignate (Unknown command)" in rep.error
    assert "line 23" in rep.error and "r1" not in rep.error.split("rejected")[0]


def test_an_unreadable_boot_log_is_an_error(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r1": ExecResult([], 1, "", "Error response from daemon: configured logging driver does not support reading")})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r1" in rep.error and "boot log" in rep.error


def test_only_frr_nodes_are_read(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"ce1": REJECTED}, images={"ce1": "ceos:4.32.0F"})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and "ce1" not in lab.read


# Config applied by `setup:` commands (SONiC, or FRR configured after boot) goes through `vtysh -c`, which exits 1
# on a rejected line (FRR 10.4.1, 2026-10-29: "% Unknown command: ...", "% Command incomplete: ...",
# "% Specify remote-as or peer-group commands first", each rc=1). A setup command that never succeeds stops the run.

def test_a_setup_command_vtysh_rejects_stops_the_run():
    from netdryrun.lab import Lab, LabError
    lab = object.__new__(Lab)
    lab.nodes = {"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")}
    calls = []

    def exec_(node, cmd, timeout=60, input=None):
        calls.append(cmd)
        if "default-orignate" in cmd[-1]:
            return ExecResult(cmd, 1, "% Unknown command: neighbor 10.0.12.2 default-orignate\n", "")
        return ExecResult(cmd, 0, "", "")

    lab.exec = exec_
    lab.run_setup("r1", ["vtysh -c 'conf t' -c 'router bgp 65001' -c 'neighbor 10.0.12.2 description ok'"], budget=0)
    with pytest.raises(LabError, match="setup on r1 failed.*Unknown command: neighbor 10.0.12.2 default-orignate"):
        lab.run_setup("r1", ["vtysh -c 'conf t' -c 'router bgp 65001' -c 'neighbor 10.0.12.2 default-orignate'"],
                      budget=0)
