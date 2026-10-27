"""Reports for big labs: the Markdown summary must still fit in one GitHub comment."""
from pathlib import Path

from netdryrun import report
from netdryrun.checks import Result
from netdryrun.config import Check, Config
from netdryrun.runner import RunReport

GITHUB_COMMENT_LIMIT = 65536
MARKER = "<!-- netdryrun-comment -->\n"  # what action.yml prepends


def _big_report(n: int, failing: int) -> RunReport:
    """Like a recorded 20-node fabric: hundreds of route checks with long names and details."""
    rep = RunReport(config=Config(Path("netdryrun.yml"), Path("topology.clab.yml"), 120, []), lab_name="ndr-scale20",
                    started="2026-10-27T12:00:00+00:00", environment={"netdryrun": "0.3.0", "containerlab": "0.81.1"})
    for i in range(n):
        c = Check(type="route", params={"node": f"leaf{i % 16 + 1}", "prefix": f"192.168.{i % 250}.0/24"},
                  name=f"leaf{i % 16 + 1}: route 192.168.{i % 250}.0/24 via bgp is present", timeout=120)
        ok = i >= failing
        ev = [] if ok else [{"node": c.params["node"], "cmd": "vtysh -c 'show ip route json'", "output": "line\n" * 40}]
        rep.results.append(Result(c, ok, "selected route via bgp (ecmp over 4 next hops)" if ok else "route missing",
                                  2, 20.9, "t", ev))
    return rep


def test_small_report_lists_every_check():
    md = report.to_markdown(_big_report(20, failing=2))
    assert md.count("| ✅ |") == 18 and md.count("| ❌ |") == 2
    assert "more checks" not in md


def test_huge_report_fits_one_github_comment():
    # 2000 checks would be ~180,000 characters: GitHub rejected the comment and the run lost its PR verdict
    md = report.to_markdown(_big_report(2000, failing=30))
    assert len(MARKER + md) <= GITHUB_COMMENT_LIMIT
    # every failure is still listed (failures come first), with evidence, and the cut is stated
    assert md.count("| ❌ |") == 30
    assert "Evidence:" in md and "full evidence in the JSON report" in md
    shown = md.count("| ✅ |")
    assert 0 < shown < 1970
    assert f"… {1970 - shown} more checks (0 failed, {1970 - shown} passed)" in md
    assert md.startswith("### ❌ Netdryrun failed") and "**1970 passed, 30 failed**" in md
