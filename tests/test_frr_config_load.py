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

    running: dict = {}

    def exec(self, node, cmd, timeout=60, input=None):
        assert cmd == ["vtysh", "-c", "show running-config"], cmd
        r = self.running.get(node, "")
        return r if isinstance(r, ExecResult) else ExecResult(cmd, 0, r, "")


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


# --- Delta review round 2 (2026-10-29) --------------------------------------------------------------------------------

def test_a_node_whose_driver_is_unknown_is_read_too(tmp_path, monkeypatch):
    # R1: FRR in an image without "frr" in its name: its boot log still counts
    lab = BootLogLab(World(), {"edge": REJECTED}, images={"edge": "registry.local/edge-router:10.4"})
    lab.nodes["edge"] = Node("edge", "clab-t-edge", "linux", "registry.local/edge-router:10.4")
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "edge" in lab.read and "default-orignate" in rep.error


def test_a_plain_host_with_an_unknown_driver_is_not_an_error(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"h1": "Starting nginx\nready\n"})
    lab.nodes["h1"] = Node("h1", "clab-t-h1", "linux", "alpine:3.20")
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and "h1" in lab.read


def test_a_bridge_has_no_boot_log_to_read(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {})
    lab.nodes["br1"] = Node("br1", "br1", "bridge", "")
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed" and "br1" not in lab.read


def test_a_daemon_that_reads_its_own_config_file_reports_rejected_lines_too():
    # R2: per-daemon config (bgpd.conf, no integrated frr.conf): the daemon logs "... on config line N: ..."
    text = ("2026/10/29 16:25:51 BGP: [ZWCSR-M7FG9][EC 100663304] No such command on config line 21: "
            "neighbor 1.1.1.1 default-orignate\n")
    assert frr.parse_config_load_errors(text) == [
        "line 21: neighbor 1.1.1.1 default-orignate (No such command, bgp)"]


def test_an_frr_log_with_no_sign_of_a_config_load_is_an_error(tmp_path, monkeypatch):
    # R2: no vtysh boot output at all (a custom entrypoint, config read elsewhere): whether it loaded is unknown
    started_only = "\n".join(line for line in CLEAN.splitlines()
                             if "sending configuration" not in line and "] done" not in line)
    lab = BootLogLab(World(), {"r3": started_only})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r3" in rep.error and "no sign" in rep.error


def test_the_boot_log_is_read_since_the_container_last_started(monkeypatch):
    # R4/R5: a log from before a restart (a config fixed since) must not count; invalid bytes don't crash
    from netdryrun import lab as lab_mod
    from netdryrun.lab import Lab
    calls = []

    def fake_run(cmd, timeout=600, env=None, input=None, errors=None):
        calls.append((cmd, errors))
        if cmd[:2] == ["docker", "inspect"]:
            return ExecResult(cmd, 0, "2026-10-29T16:25:51.123456789Z\n", "")
        return ExecResult(cmd, 0, "[45|bgpd] done", "")

    monkeypatch.setattr(lab_mod, "_run", fake_run)
    lab = object.__new__(Lab)
    lab.nodes = {"r1": Node("r1", "clab-t-r1", "linux", "quay.io/frrouting/frr:10.4.1")}
    r = lab.boot_log("r1")
    assert r.rc == 0 and "done" in r.stdout
    logs = [c for c, _ in calls if c[:2] == ["docker", "logs"]][0]
    assert logs == ["docker", "logs", "--since", "2026-10-29T16:25:51.123456789Z", "clab-t-r1"]
    assert all(e == "replace" for _, e in calls)


# --- Mutation follow-up (2026-10-30): every node is read in order, and the error says exactly what was found ------

def test_a_bridge_a_ceos_node_or_an_unreadable_host_before_an_frr_node_never_ends_the_scan(tmp_path, monkeypatch):
    # nodes that are skipped come first: the FRR node after them is still read
    w = World()
    lab = BootLogLab(w, {"h1": ExecResult([], 1, "", "no such container"), "r3": REJECTED})
    frr_nodes = dict(lab.nodes)
    lab.nodes = {"br1": Node("br1", "br1", "bridge", ""), "ovs1": Node("ovs1", "ovs1", "ovs-bridge", ""),
                 "ce1": Node("ce1", "clab-t-ce1", "ceos", "ceos:4.32.0F"),
                 "h1": Node("h1", "clab-t-h1", "linux", "alpine:3.20"), **frr_nodes}
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r3: line 21" in rep.error
    assert lab.read == ["h1", "r1", "r2", "r3"]


def test_a_driver_set_in_the_file_decides_that_a_node_is_frr(tmp_path, monkeypatch):
    # an image Netdryrun can't name, declared FRR in `drivers:`: an unreadable boot log is an error, as for any FRR
    lab = BootLogLab(World(), {"edge": ExecResult([], 1, "", "no such container")})
    lab.nodes["edge"] = Node("edge", "clab-t-edge", "linux", "registry.local/edge-router:10.4")
    install(monkeypatch, lab.world, lab, {n: FakeDriver(lab.world) for n in ("r1", "r2", "r3")})
    c = cfg(tmp_path, [ALWAYS])
    c.drivers = {"edge": "frr"}
    rep = runner.run(c, deploy=False, settle=0, hold=3)
    assert rep.status == "error" and "edge: its boot log could not be read" in rep.error


def test_the_error_names_every_node_and_every_line_exactly(tmp_path, monkeypatch):
    noise = "x" * 50 + "y" * 200
    no_load = "\n".join(line for line in CLEAN.splitlines() if "sending configuration" not in line and "] done" not in line)
    lab = BootLogLab(World(), {"r1": REJECTED, "r2": ExecResult([], 1, "", noise), "r3": no_load})
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.error == (
        "FRR rejected configuration lines at boot, so the lab ran without them and the checks did not test the "
        "change as written: r1: line 21: neighbor 10.0.12.2 default-orignate (Unknown command); line 22: neighbor "
        "10.0.12.2 maximum-prefix (Command incomplete); line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected "
        f"by bgpd) | r2: its boot log could not be read ({'y' * 200}), so whether its config loaded is unknown | r3: "
        "its boot log shows no sign of a config load (no vtysh boot output, no daemon config line), so whether its "
        "config loaded is unknown. Netdryrun reads the config load FRR's image runs at boot (frr.conf, vtysh -b). "
        "Fix the config and run again.")


def test_every_daemon_rejected_line_is_reported_in_line_order():
    text = ("2026/10/29 16:25:51 BGP: [ZWCSR-M7FG9] No such command on config line 30: neighbor 1.1.1.1 foo\n"
            "2026/10/29 16:25:51 BGP: [ZWCSR-M7FG9] No such command on config line 21: neighbor 1.1.1.1 bar\n"
            "line 25: % Unknown command[4]: baz\n")
    assert frr.parse_config_load_errors(text) == [
        "line 21: neighbor 1.1.1.1 bar (No such command, bgp)",
        "line 25: baz (Unknown command)",
        "line 30: neighbor 1.1.1.1 foo (No such command, bgp)"]


# --- Live gate on ada4dd0 (corpus v1 case 29, 2026-10-29): bgpd can answer a line with "Failure to communicate[13]"
# (CMD_WARNING_CONFIG_FAILED) and still apply it: `bgp graceful-restart` was in pe1's running config. A reported line
# is rejected only if the node's running config doesn't have it; when that can't be read, it stays an error.

GR_LOG = """[36|zebra] done
[35|mgmtd] done
line 64: Failure to communicate[13] to bgpd, line:  bgp graceful-restart
[42|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 13
"""
GR_RUNNING = """frr version 10.4.1
!
router bgp 65000
 bgp router-id 10.255.0.1
 bgp graceful-restart
 neighbor 10.0.1.2 remote-as 65100
exit
!
end
"""


def test_a_line_the_daemon_complained_about_but_applied_is_not_rejected():
    assert frr.parse_config_load_errors(GR_LOG, running=GR_RUNNING) == []
    assert frr.parse_config_load_errors(GR_LOG) == ["line 64: bgp graceful-restart (rejected by bgpd)"]


def test_a_line_missing_from_the_running_config_is_still_rejected():
    assert frr.parse_config_load_errors(REJECTED, running=GR_RUNNING) == [
        "line 21: neighbor 10.0.12.2 default-orignate (Unknown command)",
        "line 22: neighbor 10.0.12.2 maximum-prefix (Command incomplete)",
        "line 23: neighbor 10.9.9.9 route-map ALLOW-ALL in (rejected by bgpd)",
    ]


def test_a_processing_failure_with_no_line_is_still_an_error_whatever_the_running_config():
    text = "[45|bgpd] Configuration file[/etc/frr/frr.conf] processing failure: 13\n"
    assert frr.parse_config_load_errors(text, running=GR_RUNNING) == [
        "bgpd reported a configuration file processing failure (13)"]


def test_an_applied_line_passes_the_run(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r1": GR_LOG})
    lab.running = {"r1": GR_RUNNING}
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "passed", rep.error


def test_an_unreadable_running_config_keeps_the_error(tmp_path, monkeypatch):
    lab = BootLogLab(World(), {"r1": GR_LOG})
    lab.running = {"r1": ExecResult([], 1, "", "vtysh: not found")}
    rep = _run(tmp_path, monkeypatch, lab)
    assert rep.status == "error" and "r1: line 64: bgp graceful-restart (rejected by bgpd)" in rep.error
