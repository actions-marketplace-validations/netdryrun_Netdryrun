"""Startup config the NOS rejected, on Arista cEOS, Nokia SR Linux and SONiC (0.4; scheduled in 0.3.3's limits).

Captured live on 2026-10-30 (cEOS 4.36.3M, SR Linux 26.7.2, docker-sonic-vs master.1258173):
- cEOS loads its startup config line by line and skips a line it rejects, like FRR; `show startup-config errors`
  lists each one ("% Invalid input at line N") or says "No errors were found in startup-config.".
- SR Linux: containerlab applies the startup config as one commit; a line that doesn't parse, or a commit that
  fails, fails containerlab's deploy (rc 1), so the lab never runs a partial config.
- SONiC (docker-sonic-vs) has no startup config: Netdryrun configures it with setup commands, each checked. A
  config file bound into it is not checked, so it is an error, never a silent pass.
Anything that can't be read is an error (fail closed), as on FRR."""
from pathlib import Path

import pytest

from netdryrun import runner
from netdryrun.drivers import eos
from netdryrun.drivers.base import DriverError
from netdryrun.lab import ExecResult, Node

FIX = Path(__file__).parent / "fixtures"


def text(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_eos_lists_each_rejected_startup_line():
    assert eos.parse_startup_config_errors(text("eos_startup_config_errors_clean.txt")) == []
    assert eos.parse_startup_config_errors(text("eos_startup_config_errors_one.txt")) == [
        "line 10: neighbor 10.0.12.2 defualt-originate (Invalid input)"]
    assert eos.parse_startup_config_errors(text("eos_startup_config_errors_two.txt")) == [
        "line 5: neighbor 10.0.12.2 defualt-originate (Invalid input)",
        "line 6: neighbor 10.0.12.2 maximum-routes twelve (Invalid input)"]


@pytest.mark.parametrize("out", ["", "% Invalid input at line 1\n", "Total 2 errors found in startup-config.\n\n\n"
                                 ">    x\n\n% Invalid input at line 5\nerrors in startup-config: 2\n",
                                 "some other text\n"])
def test_eos_output_it_can_not_account_for_is_an_error(out):
    """A count that doesn't match the lines found, or text it doesn't know, is never read as clean."""
    with pytest.raises(DriverError):
        eos.parse_startup_config_errors(out)


class Lab:
    def __init__(self, nodes: dict, outputs: dict | None = None, binds: str = ""):
        self.nodes = {n: Node(n, f"clab-t-{n}", kind, image) for n, (kind, image) in nodes.items()}
        self.outputs = outputs or {}
        self.topology = None
        self.binds = binds
        self.ran = []

    def exec(self, node, cmd, timeout=60, input=None):
        self.ran.append((node, cmd))
        rc, out = self.outputs.get(node, (0, text("eos_startup_config_errors_clean.txt")))
        return ExecResult(cmd, rc, out, "" if rc == 0 else "Cli: not ready")

    def boot_log(self, node):
        return ExecResult([], 0, "[45|bgpd] sending configuration\n", "")


CEOS = ("arista_ceos", "ceos:4.36.3M")
SRL = ("nokia_srlinux", "ghcr.io/nokia/srlinux:26.7.2")
SONIC = ("sonic-vs", "docker-sonic-vs:master.1258173-c10162df4")


def by_node(lab, sonic_binds=()):
    return runner.config_load_by_node(lab, runner._driver_of(runner.Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[])),
                                      bound=lambda name: list(sonic_binds))


def test_a_ceos_line_rejected_at_boot_makes_the_run_an_error():
    lab = Lab({"ceos1": CEOS}, {"ceos1": (0, text("eos_startup_config_errors_one.txt"))})
    found = by_node(lab)
    assert found == {"ceos1": ["line 10: neighbor 10.0.12.2 defualt-originate (Invalid input)"]}
    msg = runner.rejected_config_message(found)
    assert "ceos1: line 10" in msg and "NOS rejected configuration lines" in msg
    assert lab.ran == [("ceos1", ["Cli", "-p", "15", "-c", "show startup-config errors"])]


def test_a_clean_ceos_boot_is_clean():
    assert by_node(Lab({"ceos1": CEOS})) == {"ceos1": []}


def test_a_ceos_whose_errors_can_not_be_read_is_an_error():
    found = by_node(Lab({"ceos1": CEOS}, {"ceos1": (1, "")}))
    assert "could not be read" in found["ceos1"][0]


def test_sr_linux_is_checked_by_containerlabs_deploy():
    """Its startup config is one commit containerlab applies at deploy: a rejected line fails the deploy, so a
    running SR Linux node ran its whole config. Nothing to read after the run."""
    lab = Lab({"srl1": SRL})
    assert by_node(lab) == {"srl1": []} and lab.ran == []


def test_sonic_without_bound_config_is_clean_and_with_it_is_an_error():
    assert by_node(Lab({"sonic1": SONIC})) == {"sonic1": []}
    found = by_node(Lab({"sonic1": SONIC}), sonic_binds=["configs/frr.conf:/etc/frr/frr.conf"])
    assert "not checked" in found["sonic1"][0] and "setup" in found["sonic1"][0]


def test_the_report_records_each_platforms_load():
    rep = runner.RunReport(config=runner.Config(path=Path("t.yml"), lab=Path("t.clab.yml"), timeout=60, checks=[]))
    lab = Lab({"ceos1": CEOS, "srl1": SRL})
    lab.image_digest = lambda image: None

    class Drv:
        def __init__(self, name):
            self.name = name

        def nos_version(self):
            return None
    runner._config_load(lab, lambda n: Drv({"ceos1": "eos", "srl1": "srlinux"}[n]), rep, by_node(lab))
    assert rep.environment["nodes"]["ceos1"]["config_load"] == "clean"
    assert rep.environment["nodes"]["srl1"]["config_load"] == "clean"


def test_ceos_output_it_can_not_read_is_named():
    found = by_node(Lab({"ceos1": CEOS}, {"ceos1": (0, "% Invalid input\n")}))
    assert "unexpected output" in found["ceos1"][0] and "unknown" in found["ceos1"][0]


def test_the_binds_a_sonic_node_gets_are_read_from_the_topology(tmp_path):
    topo = tmp_path / "t.clab.yml"
    topo.write_text("name: t\ntopology:\n  defaults: {binds: [shared/a:/etc/x]}\n  nodes:\n"
                    "    sonic1: {kind: sonic-vs, binds: [configs/frr.conf:/etc/frr/frr.conf]}\n"
                    "    sonic2: {kind: sonic-vs}\n")
    lab = Lab({"sonic1": SONIC, "sonic2": SONIC})
    lab.topology = topo
    assert runner._bound_files(lab, "sonic1") == ["shared/a:/etc/x", "configs/frr.conf:/etc/frr/frr.conf"]
    found = runner.config_load_by_node(lab, runner._driver_of(runner.Config(path=Path("t.yml"), lab=topo, timeout=60,
                                                                            checks=[])))
    assert found["sonic2"] == [] and "not checked" in found["sonic1"][0]
    lab.topology = tmp_path / "missing.clab.yml"           # unreadable: an error, never clean
    assert "could not be read" in runner._bound_files(lab, "sonic1")[0]
