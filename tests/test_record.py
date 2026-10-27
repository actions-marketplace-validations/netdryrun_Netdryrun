from netdryrun.record import render


def test_render_has_review_header_and_warnings():
    text = render({"lab": "topology.clab.yml", "timeout": 120, "checks": [{"type": "bgp_session", "node": "r1", "neighbor": "10.0.0.2"}]},
                  ["r2: BGP neighbor 10.0.0.9 is active; not recorded"])
    assert text.startswith("# Recorded by netdryrun")
    assert "# warning: r2" in text
    assert "neighbor: 10.0.0.2" in text


def test_attribute_check_pins_best_path():
    from netdryrun.drivers.base import BgpPath, Observation
    from netdryrun.record import _attribute_check

    class Drv:
        def bgp_paths(self, prefix, vrf="default"):
            return Observation([
                BgpPath(best=False, as_path="65020 65020", next_hop="10.0.0.6", local_pref=100, med=10),
                BgpPath(best=True, as_path="65020", next_hop="10.0.0.2", local_pref=200, med=50,
                        communities=["65020:100", "65535:65281"], large_communities=["65020:1:1"]),
            ], [])

    c = _attribute_check(Drv(), "r1", "192.168.20.0/24")
    assert c == {"type": "bgp_route", "node": "r1", "prefix": "192.168.20.0/24", "as_path": "65020",
                 "local_pref": 200, "communities": ["65020:100", "no-export", "65020:1:1"]}
