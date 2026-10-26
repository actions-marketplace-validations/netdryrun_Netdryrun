from netdryrun.record import render


def test_render_has_review_header_and_warnings():
    text = render({"lab": "topology.clab.yml", "timeout": 120, "checks": [{"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2"}]},
                  ["r2: BGP neighbor 10.0.0.9 is active; not recorded"])
    assert text.startswith("# Recorded by netdryrun")
    assert "# warning: r2" in text
    assert "neighbor: 10.0.0.2" in text
