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


def test_evidence_excerpt_shows_which_route_is_selected():
    # A real leak (frr-bgp-broken style): FRR lists the leaked BGP default first, without "selected", and the
    # selected kernel default after it, beyond the 15-line window. The excerpt must show the proof for
    # "unexpectedly present via bgp (not selected)": the selected route and its protocol.
    import json

    data = json.loads((Path(__file__).parent / "fixtures" / "report-real-failed-leak.json").read_text())
    check = next(c for c in data["checks"] if c["params"].get("prefix") == "0.0.0.0/0" and not c["passed"])
    output = check["evidence"][0]["output"]
    rows = output.splitlines()
    assert len(rows) > 15 and next(i for i, r in enumerate(rows) if '"selected"' in r) > 15
    ex = report._evidence_excerpt(output, check["params"])
    assert '"0.0.0.0/0"' in ex and '"protocol":"bgp"' in ex
    assert '"protocol":"kernel"' in ex and '"selected":true' in ex and '"installed":true' in ex
    assert len(ex.splitlines()) <= 15 + 1 + 8 + 1


def test_markdown_evidence_shows_every_command_of_the_last_sample():
    rep = _big_report(1, failing=1)
    r = rep.results[0]
    r.evidence = [{"node": "leaf1", "cmd": "vtysh -c 'show ip route 192.168.0.0/24 json'", "output": "{}"},
                  {"node": "leaf1", "cmd": "vtysh -c 'show bgp ipv4 unicast 192.168.0.0/24 json'", "output": "{}"}]
    md = report.to_markdown(rep)
    assert "show ip route 192.168.0.0/24 json" in md and "show bgp ipv4 unicast 192.168.0.0/24 json" in md
    assert md.count("<details>") == 1
