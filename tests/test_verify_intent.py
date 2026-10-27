"""The intent file: every form parses to its canonical line, and every malformed file is an IntentError."""
import pytest

from netdryrun.verify.intent import IntentError, check_nodes, load_intent, parse_intent
from netdryrun.verify.snapshot import AsPath


def parse(lines=(), allow=None):
    data = {"intent": list(lines)}
    if allow is not None:
        data["allow_anywhere"] = allow
    return parse_intent(data, "t")


def test_every_form_parses():
    it = parse([
        {"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"], "with": {"from": "10.0.2.1", "as_path": "65000 65101",
                                                                           "communities": ["no-export", "65000:1"]}},
        {"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"local_pref": 200, "med": None}},
        {"session": {"node": "edge1", "neighbor": "10.0.9.2"}, "goes": "down"},
        {"prefix": "192.0.2.128/25", "disappears_from": "cust1", "including_received_only": True},
        {"prefix": "198.51.100.0/24", "advertisement": {"node": "edge1", "neighbor": "192.0.2.9"}, "goes": "added"},
        {"prefix": "2001:db8::/32", "vrf": "cust", "advertisement": {"node": "edge1", "neighbor": "2001:db8::9"},
         "to": {"as_path": "65000 65000"}},
    ], allow=["10.200.*.0/24", {"prefix": "10.9.0.0/16", "vrf": "cust"}])
    a, b, s, d, adv, adv6 = it.lines
    assert a.form == "appears_on" and a.nodes == ("up1", "peer1") and a.state == "installed"
    assert a.pins["as_path"] == AsPath.parse("65000 65101") and a.pins["communities"] == ("65000:1", "65535:65281")
    assert b.to == {"local_pref": 200, "med": None} and b.vrf == "default"
    assert s.form == "session" and s.neighbor == "10.0.9.2" and s.goes == "down" and s.afi is None
    assert d.nodes == ("cust1",) and d.including_received_only
    assert adv.goes == "added" and adv.neighbor == "192.0.2.9"
    assert adv6.vrf == "cust" and adv6.to["as_path"].render() == "65000 65000"
    assert [x.pattern for x in it.allow] == ["10.200.*.0/24", "10.9.0.0/16"] and it.allow[0].glob
    assert it.nodes() == {"up1", "peer1", "edge1", "cust1"}


def test_empty_intent():
    it = parse()
    assert it.empty and it.lines == []


@pytest.mark.parametrize("data", [
    None, [], "intent", {}, {"intent": None}, {"intent": {}}, {"intent": [], "extra": 1},
    {"intent": [{"prefix": "10.0.0.0/24"}]},                                                  # no form
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "disappears_from": ["b"]}]},  # two forms
    {"intent": [{"prefix": "10.0.0.1/24", "appears_on": ["a"]}]},                             # host bits
    {"intent": [{"prefix": "10.0.0.0", "appears_on": ["a"]}]},                                # no length
    {"intent": [{"prefix": "nope", "appears_on": ["a"]}]},
    {"intent": [{"appears_on": ["a"]}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": []}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a", "a"]}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "state": "fib"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"colour": 1}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"local_pref": "200"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"communities": "65000:1"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"as_path": "65000 x"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "with": {"protocol": "ebgp"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "state": "received", "with": {"protocol": "bgp"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "vrf": "all"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"], "goes": "down"}]},            # key of another form
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": "a"}]},                             # no to:
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": ["a", "b"], "to": {"med": 1}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": "a", "to": {}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "best_path_on": "a", "to": {"protocol": "bgp"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "disappears_from": ["a"], "including_received_only": "yes"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1"}}]},                          # no goes
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "up"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "eth1"}, "goes": "down"}]},
    {"intent": [{"session": {"node": "a"}, "goes": "down"}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1", "afi": "evpn"}, "goes": "down"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "down"}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "added",
                 "to": {"med": 1}}]},
    {"intent": [{"prefix": "10.0.0.0/24", "advertisement": {"node": "a", "neighbor": "10.0.0.1"},
                 "to": {"from": "10.0.0.1"}}]},
    # two lines about the same route on the same node
    {"intent": [{"prefix": "10.0.0.0/24", "appears_on": ["a"]}, {"prefix": "10.0.0.0/24", "best_path_on": "a",
                                                                "to": {"med": 1}}]},
    {"intent": [{"session": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "down"},
                {"session": {"node": "a", "neighbor": "10.0.0.1"}, "goes": "down"}]},
    {"intent": [], "allow_anywhere": "10.0.0.0/8"},
    {"intent": [], "allow_anywhere": ["*"]},
    {"intent": [], "allow_anywhere": ["*/*"]},
    {"intent": [], "allow_anywhere": ["10.*"]},
    {"intent": [], "allow_anywhere": ["1*.0.0.0/8"]},
    {"intent": [], "allow_anywhere": ["10.0.[0-9.0/24"]},
    {"intent": [], "allow_anywhere": ["10.0.0.1/24"]},
    {"intent": [], "allow_anywhere": ["10.0.0.0/24", "10.0.0.0/24"]},
    {"intent": [], "allow_anywhere": [{"prefix": "10.0.0.0/24", "node": "a"}]},
])
def test_malformed_intents_are_errors(data):
    with pytest.raises(IntentError):
        parse_intent(data, "t")


def test_allow_anywhere_matches_exactly_or_by_explicit_glob_never_by_containment():
    it = parse(allow=["10.200.*.0/24", "10.0.0.0/8", "2001:db8:1:*::/64"])
    glob, exact, v6 = it.allow
    assert glob.matches("10.200.7.0/24", "default") and not glob.matches("10.200.7.0/25", "default")
    assert not glob.matches("10.200.7.0/24", "cust")                      # default VRF only
    assert exact.matches("10.0.0.0/8", "default")
    assert not exact.matches("10.1.0.0/16", "default")                     # no supernet containment
    assert v6.matches("2001:db8:1:2::/64", "default") and not v6.matches("2001:db8:4::/64", "default")


def test_load_intent_reads_yaml_strictly(tmp_path):
    p = tmp_path / "intent.yml"
    p.write_text("intent:\n  - prefix: 10.0.0.0/24\n    appears_on: [r1]\n")
    assert load_intent(p).lines[0].nodes == ("r1",)
    p.write_text("intent: []\nintent: []\n")                                # duplicate key
    with pytest.raises(IntentError):
        load_intent(p)
    p.write_text("intent: [\n")
    with pytest.raises(IntentError):
        load_intent(p)
    with pytest.raises(IntentError):
        load_intent(tmp_path / "missing.yml")


def test_check_nodes_refuses_unknown_and_unobserved_nodes():
    it = parse([{"prefix": "10.0.0.0/24", "appears_on": ["r1", "r2"]}])
    check_nodes(it, {"r1": "frr", "r2": "frr"})
    with pytest.raises(IntentError):
        check_nodes(it, {"r1": "frr"})
    with pytest.raises(IntentError):
        check_nodes(it, {"r1": "frr", "r2": ""})


# --- allow_anywhere breadth (review finding 3) ---------------------------------------------------------------

@pytest.mark.parametrize("entry", [
    "10.*/*", "10.*.0.0/16", "10.*.*.0/24", "*.0.0.0/8", "10.*.0.0/24",        # wider than /16 of reach
    "10.200.*.0/*", "10.200.*.0/2?", "10.200.*.0",                            # the length is always explicit
    "10.2*.0.0/24", "10.200.1*.0/24", "10.200.*1.0/24",                        # `*` is one whole octet
    "10.20?.1.0/24", "10.200.[0-3].0/24",                                      # no other wildcards
    "10.200.0.*/24",                                                          # a wildcard past the length
    "10.200.*.1/24",                                                          # host bits
    "2001:db8:*::/48", "2001:*::/32", "2001:db8:1:*::/*", "2001:db8:1:5*::/64", "2001:db8:1:*::/48",
])
def test_allow_anywhere_globs_are_bounded(entry):
    with pytest.raises(IntentError):
        parse(allow=[entry])


def test_allow_anywhere_glob_reach_and_matching():
    v4, v4b, v6 = parse(allow=["10.200.*.0/24", "10.200.*.*/32", "2001:db8:1:*::/64"]).allow
    assert v4.matches("10.200.7.0/24", "default") and v4.matches("10.200.255.0/24", "default")
    assert not v4.matches("10.200.7.0/25", "default") and not v4.matches("10.201.7.0/24", "default")
    assert not v4.matches("10.200.7.128/25", "default")
    assert v4b.matches("10.200.1.9/32", "default") and not v4b.matches("10.200.1.0/24", "default")
    assert v6.matches("2001:db8:1:5::/64", "default") and v6.matches("2001:0db8:0001:ffff::/64", "default")
    assert not v6.matches("2001:db8:2:5::/64", "default") and not v6.matches("2001:db8:1:5::/80", "default")
    assert not v6.matches("10.200.7.0/24", "default") and not v4.matches("2001:db8:1:5::/64", "default")
