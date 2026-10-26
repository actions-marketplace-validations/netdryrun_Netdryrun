import textwrap

import pytest

from netdryrun.config import ConfigError, load


def write(tmp_path, body, topo=True):
    if topo:
        (tmp_path / "topo.clab.yml").write_text("name: t\ntopology:\n  nodes:\n    r1: {}\n")
    p = tmp_path / "netdryrun.yml"
    p.write_text(textwrap.dedent(body))
    return p


def test_loads_and_names_checks(tmp_path):
    cfg = load(write(tmp_path, """
        lab: topo.clab.yml
        checks:
          - {type: route, node: r1, prefix: 10.1.2.3/24}
          - {type: ping, node: r1, target: 10.0.0.1, timeout: 5}
    """))
    assert cfg.checks[0].params["prefix"] == "10.1.2.0/24"  # normalized
    assert "10.1.2.0/24" in cfg.checks[0].name
    assert cfg.checks[1].timeout == 5 and cfg.checks[0].timeout == 120


def test_directory_path_finds_file(tmp_path):
    write(tmp_path, "lab: topo.clab.yml\nchecks:\n  - {type: ping, node: r1, target: 10.0.0.1}\n")
    assert load(tmp_path).checks


@pytest.mark.parametrize("check,msg", [
    ("{type: bogus, node: r1}", "unknown type"),
    ("{type: route, node: r1}", "missing required key 'prefix'"),
    ("{type: route, node: r1, prefix: 10.0.0.0/8, colour: red}", "unknown keys"),
    ("{type: ping, node: r1, target: not-an-ip}", "does not appear to be"),
    ("{type: ping, node: r1, target: 10.0.0.1, expect: maybe}", "expect must be"),
])
def test_rejects_bad_checks(tmp_path, check, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, f"lab: topo.clab.yml\nchecks:\n  - {check}\n"))


def test_missing_lab_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load(write(tmp_path, "lab: nope.yml\nchecks:\n  - {type: ping, node: r1, target: 10.0.0.1}\n", topo=False))


@pytest.mark.parametrize("check,msg", [
    ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2}", "at least one of"),
    ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: 5, max: 2}", "greater than max"),
    ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, exact: 3, max: 4}", "not both"),
    ("{type: bgp_prefixes, node: r1, neighbor: 10.0.0.2, min: lots}", "non-negative integer"),
    ("{type: bgp_session, node: r1, neighbor: 10.0.0.2, state: establised}", "state must be one of"),
    ("{type: ping, node: r1, target: 10.0.0.1, timeout: 0}", "positive number"),
])
def test_rejects_bad_values(tmp_path, check, msg):
    with pytest.raises(ConfigError, match=msg):
        load(write(tmp_path, f"lab: topo.clab.yml\nchecks:\n  - {check}\n"))


def test_ipv6_is_canonicalized(tmp_path):
    cfg = load(write(tmp_path, "lab: topo.clab.yml\nchecks:\n  - {type: bgp_session, node: r1, neighbor: '2001:db8:0:0::1', vrf: blue}\n"))
    assert cfg.checks[0].params["neighbor"] == "2001:db8::1"
    assert cfg.checks[0].params["vrf"] == "blue"


def test_scenarios(tmp_path):
    cfg = load(write(tmp_path, """
        lab: topo.clab.yml
        checks:
          - {type: ping, node: r1, target: 10.0.0.1}
        scenarios:
          - name: uplink fails
            link_down: {node: r1, interface: eth1}
            checks:
              - {type: ping, node: r1, target: 10.0.0.9}
          - node_isolated: r2
            checks:
              - {type: route, node: r1, prefix: 10.2.0.0/24, present: false}
    """))
    assert [s.name for s in cfg.scenarios] == ["uplink fails", "r2 isolated"]
    assert cfg.scenarios[0].checks[0].name.startswith("[uplink fails]")


def test_scenario_needs_a_fault(tmp_path):
    with pytest.raises(ConfigError, match="at least one fault"):
        load(write(tmp_path, "lab: topo.clab.yml\nchecks:\n  - {type: ping, node: r1, target: 10.0.0.1}\nscenarios:\n  - checks: [{type: ping, node: r1, target: 10.0.0.1}]\n"))
