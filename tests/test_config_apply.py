"""A config the NOS rejected, wholly or in part, is never a pass (0.4; expert war game, 2026-10-29).

Reproduced live on FRR 10.4.1 (examples/frr-bgp, r2 adds `neighbor 10.0.12.1 default-orignate`, a typo): FRR's
boot apply skipped that line, logged `line 18: % Unknown command`, loaded the rest, and 0.3.2 said PASSED (exit
0) on a config whose changed line never ran. Now every node's driver reports what it rejected at load, and any
rejection makes the run an error (exit 2) naming the node and the line; a driver that can't tell says so in the
report, never silently."""
from netdryrun.drivers.frr import FrrDriver, parse_config_load_errors
from netdryrun.drivers.sonic import SonicDriver

# the container log of r2 in the live repro (FRR's vtysh -b prints each rejected line once per daemon)
LIVE_LOG = """\
2026/10/29 23:05:11 [...] watchfrr: all daemons up
line 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate
line 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate
line 18: % Unknown command[31]:   neighbor 10.0.12.1 default-orignate
% Error 16 from MGMTD for vty-mgmtd-25 with no pending command: Lock already taken on datastore by session: 0
% Can't enter config; running datastore locked by another session
"""


def test_frr_reads_each_rejected_line_once():
    assert parse_config_load_errors(LIVE_LOG) == ["line 18: % Unknown command: neighbor 10.0.12.1 default-orignate"]
    assert parse_config_load_errors("watchfrr: all daemons up\n") == []
    for kind in ("% Invalid input", "% Ambiguous command", "% Command incomplete", "% Command failed"):
        assert parse_config_load_errors(f"line 4: {kind}:  router bgp 1 2\n") == [f"line 4: {kind}: router bgp 1 2"]


class LogLab:
    def __init__(self, log):
        self.log = log

    def logs(self, node):
        return self.log


def test_the_frr_driver_reads_the_nodes_log_and_sonic_says_it_cannot():
    assert FrrDriver(LogLab(LIVE_LOG), "r2").config_load_errors() == [
        "line 18: % Unknown command: neighbor 10.0.12.1 default-orignate"]
    assert FrrDriver(LogLab(""), "r2").config_load_errors() == []
    assert SonicDriver(LogLab(LIVE_LOG), "s1").config_load_errors() is None   # its boot log is not known yet


def test_verify_stops_on_a_side_whose_config_did_not_load():
    """verify_change: a changed line FRR rejected on the after side would read as NO BEHAVIOR CHANGE. Each side's
    FRR nodes are checked after the snapshot: any rejected line stops the run (exit 2), naming the side."""
    import pytest

    from netdryrun.lab import LabError
    from netdryrun.verify import run as vrun

    class Lab:
        def logs(self, node):
            return LIVE_LOG if node == "r2" else "watchfrr: all daemons up\n"
    with pytest.raises(LabError) as e:
        vrun.check_config_loaded(Lab(), {"r1": "frr", "r2": "frr", "h1": ""}, "after")
    assert "after" in str(e.value) and "r2" in str(e.value) and "default-orignate" in str(e.value)
    vrun.check_config_loaded(Lab(), {"r1": "frr", "h1": ""}, "before")      # clean: no error


def test_frr_reports_its_version():
    from netdryrun.drivers.frr import parse_version

    text = "FRRouting 10.4.1_git (edge1) on Linux(6.18.54.1-microsoft-standard-WSL2).\nCopyright 1996-2005 ...\n"
    assert parse_version(text) == "FRRouting 10.4.1_git"
    assert parse_version("% Unknown command\n") is None


def test_driver_defaults_never_claim_what_they_do_not_read():
    import pytest

    from netdryrun.drivers.base import Driver, DriverError
    d = Driver(None, "x1")
    assert d.nos_version() is None and d.config_load_errors() is None
    with pytest.raises(DriverError):
        d.vrfs()


def test_frr_reads_its_version_from_the_node_and_none_when_it_cannot():
    from netdryrun.lab import ExecResult

    class Lab:
        def __init__(self, rc, out):
            self.rc, self.out = rc, out

        def exec(self, node, cmd, timeout=60, input=None):
            return ExecResult(cmd, self.rc, self.out, "")
    assert FrrDriver(Lab(0, "FRRouting 10.4.1_git (r1) on Linux.\n"), "r1").nos_version() == "FRRouting 10.4.1_git"
    assert FrrDriver(Lab(1, ""), "r1").nos_version() is None
