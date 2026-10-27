"""The diff and matching engine on snapshot pairs: every intent form, the declared-but-didn't-happen path,
allow_anywhere, and the design's red tests (each must give UNDECLARED CHANGES with an empty or honest
intent). Assertions are on statuses and item keys, never on message text."""
from dataclasses import replace

import pytest

from netdryrun.verify.engine import VerifyError, baseline_problems, diff, match
from netdryrun.verify.intent import IntentError
from verify_helpers import add_new_customer_block, attrs, base, intent, path, rib, session


def undeclared(m):
    return {(d.key.kind, d.key.node, d.key.prefix or d.key.neighbor) for d in m.undeclared}


def run(before, after, lines=(), allow=()):
    return match(before.snap(), after.snap(), intent(lines, allow))


# --- the basics --------------------------------------------------------------------------------------------

def test_no_change_with_an_empty_intent():
    m = run(base(), base())
    assert m.status == "no_change" and not m.items


def test_an_intent_on_an_unchanged_lab_did_not_happen():
    m = run(base(), base(), [{"prefix": "10.101.0.0/24", "appears_on": ["up1"]}])
    assert m.status == "failed" and len(m.not_happened) == 1 and not m.undeclared


def test_any_change_with_an_empty_intent_is_undeclared():
    after = base()
    after.drop("cust1", "path", "198.18.0.0/24")
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("path", "cust1", "198.18.0.0/24")}


def test_diff_refuses_different_node_sets():
    a = base().snap()
    b = base().snap()
    del b.nodes["peer1"]
    with pytest.raises(VerifyError):
        diff(a, b)


# --- appears_on --------------------------------------------------------------------------------------------

def test_appears_on_explains_the_new_route_and_its_advertisements():
    after = add_new_customer_block(base())
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "matched", undeclared(m)
    (lr,) = m.lines
    assert {d["node"] for d in lr.details} == {"edge1", "up1", "peer1"}
    up1 = next(d for d in lr.details if d["node"] == "up1")
    assert up1["from"] == "10.0.2.1" and up1["as_path"] == "65000 65101" and up1["next_hop"] == ["10.0.2.1"]


def test_appears_on_covers_only_the_listed_nodes():
    after = add_new_customer_block(base())
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["up1", "peer1"]}])
    assert m.status == "failed"
    assert undeclared(m) == {("path", "edge1", "10.101.0.0/24"), ("rib", "edge1", "10.101.0.0/24")}


def test_appears_on_a_node_where_it_did_not_appear():
    after = add_new_customer_block(base(), nodes=("edge1", "up1"))
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}])
    assert m.status == "failed" and [r.line.index for r in m.not_happened] == [0]
    # a line that didn't happen explains nothing
    assert ("path", "up1", "10.101.0.0/24") in undeclared(m)


def test_appears_on_needs_the_route_absent_before():
    m = run(base(), base(), [{"prefix": "10.100.0.0/24", "appears_on": ["up1"]}])
    assert m.status == "failed" and m.not_happened


def test_appears_on_requires_selected_and_fib_installed_by_default():
    after = add_new_customer_block(base())
    after.rib("up1", "10.101.0.0/24", rib("bgp", hops=("10.0.2.1",), fib=False))
    lines = [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]
    assert run(base(), after, lines).status == "failed"
    lines[0]["state"] = "selected"
    assert run(base(), after, lines).status == "matched"


def test_appears_on_as_received_only():
    after = base()
    after.path("up1", "10.101.0.0/24", "10.0.2.1", path(best=False, as_path="65000 65101", next_hop="10.0.2.1"))
    after.adj_out("edge1", "10.0.2.2", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    lines = [{"prefix": "10.101.0.0/24", "appears_on": "up1"}]
    assert run(base(), after, lines).status == "failed"                    # default: must be in the FIB
    lines[0]["state"] = "received"
    assert run(base(), after, lines).status == "matched"
    lines[0]["with"] = {"as_path": "65000 65101"}
    assert run(base(), after, lines).status == "matched"
    lines[0]["with"] = {"as_path": "65000 65999"}
    assert run(base(), after, lines).status == "failed"


@pytest.mark.parametrize("pins,ok", [
    ({"from": "10.0.2.1", "as_path": "65000 65101", "next_hop": "10.0.2.1", "origin": "igp"}, True),
    ({"protocol": "bgp", "distance": 20}, True),
    ({"from": "10.0.3.1"}, False),
    ({"as_path": "65000 65000 65101"}, False),
    ({"local_pref": 200}, False),
    ({"communities": ["no-export"]}, False),
    ({"protocol": "static"}, False),
    ({"metric": 5}, False),
])
def test_appears_on_with_pins(pins, ok):
    after = add_new_customer_block(base())
    m = run(base(), after, [{"prefix": "10.101.0.0/24", "appears_on": ["edge1"]},
                            {"prefix": "10.101.0.0/24", "appears_on": ["up1"], "with": pins},
                            {"prefix": "10.101.0.0/24", "appears_on": ["peer1"]}])
    assert (m.status == "matched") is ok


def test_an_extra_advertisement_to_a_non_lab_neighbor_is_undeclared():
    after = add_new_customer_block(base())
    after.adj_out("edge1", "198.51.100.9", "10.101.0.0/24", attrs(as_path="65101", next_hop="10.0.1.2"))
    lines = [{"prefix": "10.101.0.0/24", "appears_on": ["edge1", "up1", "peer1"]}]
    m = run(base(), after, lines)
    assert m.status == "failed" and undeclared(m) == {("adj_out", "edge1", "10.101.0.0/24")}
    lines.append({"prefix": "10.101.0.0/24", "advertisement": {"node": "edge1", "neighbor": "198.51.100.9"},
                  "goes": "added"})
    assert run(base(), after, lines).status == "matched"


# --- disappears_from ---------------------------------------------------------------------------------------

def _withdraw_from_peer1(lab):
    lab.drop("edge1", "adj_out", "10.100.0.0/24", neighbor="10.0.3.2")
    lab.drop("peer1", "path", "10.100.0.0/24")
    lab.drop("peer1", "rib", "10.100.0.0/24")
    return lab


def test_disappears_from():
    after = _withdraw_from_peer1(base())
    assert run(base(), after).status == "failed"
    m = run(base(), after, [{"prefix": "10.100.0.0/24", "disappears_from": ["peer1"]}])
    assert m.status == "matched", undeclared(m)


def test_disappears_from_a_node_that_still_has_it():
    after = _withdraw_from_peer1(base())
    m = run(base(), after, [{"prefix": "10.100.0.0/24", "disappears_from": ["peer1", "up1"]}])
    assert m.status == "failed" and m.not_happened


def test_disappears_from_needs_the_route_selected_before():
    before = base()
    before.path("up1", "10.99.0.0/24", "10.0.2.1", path(best=False, as_path="65000", next_hop="10.0.2.1"))
    after = base()
    m = run(before, after, [{"prefix": "10.99.0.0/24", "disappears_from": ["up1"]}])
    assert m.status == "failed" and m.not_happened
    m = run(before, after, [{"prefix": "10.99.0.0/24", "disappears_from": ["up1"], "including_received_only": True}])
    assert m.status == "matched"


def _soft_reconfig_lab():
    lab = base()
    lab.adj_in("edge1", "10.0.2.2", "0.0.0.0/0", attrs(as_path="65002", next_hop="10.0.2.2"))   # filtered inbound
    lab.adj_in("edge1", "10.0.2.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    return lab


def test_red_removed_soft_reconfiguration_is_a_received_only_disappearance():
    before = _soft_reconfig_lab()
    after = base()                                       # soft-reconfiguration inbound removed on edge1
    m = run(before, after)
    assert m.status == "failed"
    assert undeclared(m) == {("adj_in", "edge1", "0.0.0.0/0"), ("adj_in", "edge1", "203.0.113.0/24")}
    # 0/0 was received-only: disappears_from without including_received_only didn't happen
    m = run(before, after, [{"prefix": "0.0.0.0/0", "disappears_from": ["edge1"]}])
    assert m.status == "failed" and m.not_happened


def test_soft_reconfiguration_removal_with_an_honest_intent():
    before, after = _soft_reconfig_lab(), base()
    after.drop("edge1", "adj_in")
    m = run(before, after, [{"prefix": "0.0.0.0/0", "disappears_from": ["edge1"], "including_received_only": True}])
    # 203.0.113.0/24 is still selected on edge1, only its pre-policy copy vanished: still undeclared
    assert m.status == "failed" and undeclared(m) == {("adj_in", "edge1", "203.0.113.0/24")}
    assert not m.not_happened


# --- best_path_on ------------------------------------------------------------------------------------------

def _raise_local_pref(lab, value=200):
    lab.path("edge1", "203.0.113.0/24", "10.0.2.2", path(as_path="65002", next_hop="10.0.2.2", local_pref=value))
    return lab


def test_best_path_on_with_listed_values():
    after = _raise_local_pref(base())
    assert run(base(), after).status == "failed"
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"local_pref": 200}}])
    assert m.status == "matched", undeclared(m)


@pytest.mark.parametrize("to", [{"local_pref": 300}, {"local_pref": 200, "med": 5}, {"med": 5}, {"local_pref": 100}])
def test_best_path_on_listed_values_must_be_exact(to):
    after = _raise_local_pref(base())
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": to}])
    assert m.status == "failed" and m.not_happened


def test_best_path_on_unlisted_attributes_are_frozen():
    after = base()
    after.path("edge1", "203.0.113.0/24", "10.0.2.2",
               path(as_path="65002", next_hop="10.0.2.2", local_pref=200, communities=["65000:7"]))
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"local_pref": 200}}])
    assert m.status == "failed" and m.not_happened
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1",
                             "to": {"local_pref": 200, "communities": ["65000:7"]}}])
    assert m.status == "matched"


def test_best_path_on_a_node_without_the_route():
    m = run(base(), base(), [{"prefix": "10.77.0.0/24", "best_path_on": "edge1", "to": {"med": 1}}])
    assert m.status == "failed" and m.not_happened


def _two_paths(lab, winner_kw=None, backup_kw=None):
    """198.51.100.0/24 on edge1 from peer1 (best) and up1 (backup), advertised to cust1."""
    lab.path("edge1", "198.51.100.0/24", "10.0.3.2", path(as_path="65003", next_hop="10.0.3.2", **(winner_kw or {})))
    lab.path("edge1", "198.51.100.0/24", "10.0.2.2",
             path(best=False, as_path="65002 65003", next_hop="10.0.2.2", **(backup_kw or {})))
    lab.rib("edge1", "198.51.100.0/24", rib("bgp", hops=("10.0.3.2",)))
    lab.adj_out("edge1", "10.0.1.2", "198.51.100.0/24", attrs(as_path="65003", next_hop="10.0.3.2"))
    lab.learn("cust1", "198.51.100.0/24", "10.0.1.1", "65000 65003")
    return lab


def _swap_winner(lab, key, value):
    lab.path("edge1", "198.51.100.0/24", "10.0.3.2", path(best=False, as_path="65003", next_hop="10.0.3.2"))
    lab.path("edge1", "198.51.100.0/24", "10.0.2.2",
             path(as_path="65002 65003", next_hop="10.0.2.2", **{key: value}))
    lab.rib("edge1", "198.51.100.0/24", rib("bgp", hops=("10.0.2.2",)))
    lab.adj_out("edge1", "10.0.1.2", "198.51.100.0/24", attrs(as_path="65002 65003", next_hop="10.0.2.2"))
    lab.learn("cust1", "198.51.100.0/24", "10.0.1.1", "65000 65002 65003")
    return lab


@pytest.mark.parametrize("key,value", [("weight", 100), ("origin", "igp")])
def test_red_a_weight_or_origin_change_that_swaps_the_winner(key, value):
    backup = {"origin": "incomplete"} if key == "origin" else {}
    before = _two_paths(base(), backup_kw=backup)
    after = _swap_winner(_two_paths(base(), backup_kw=backup), key, value)
    assert run(before, after).status == "failed"
    # an honest intent naming only the attribute: the winner (from, next hop, AS path) is frozen
    m = run(before, after, [{"prefix": "198.51.100.0/24", "best_path_on": "edge1", "to": {key: value}}])
    assert m.status == "failed" and m.not_happened
    # every changed attribute declared, on edge1 and on cust1 (which now sees another AS path)
    full = [{"prefix": "198.51.100.0/24", "best_path_on": "edge1",
             "to": {key: value, "from": "10.0.2.2", "next_hop": "10.0.2.2", "as_path": "65002 65003"}}]
    m = run(before, after, full)
    assert m.status == "failed" and undeclared(m) == {("path", "cust1", "198.51.100.0/24")}
    full.append({"prefix": "198.51.100.0/24", "best_path_on": "cust1", "to": {"as_path": "65000 65002 65003"}})
    assert run(before, after, full).status == "matched"


def test_red_lost_backup_path():
    before = _two_paths(base())
    after = _two_paths(base())
    after.drop("edge1", "path", "198.51.100.0/24", neighbor="10.0.2.2")
    m = run(before, after)
    assert m.status == "failed" and undeclared(m) == {("path", "edge1", "198.51.100.0/24")}
    # the best path is unchanged, so a best-path line can't explain it
    m = run(before, after, [{"prefix": "198.51.100.0/24", "best_path_on": "edge1", "to": {"med": 0}}])
    assert m.status == "failed"


def test_red_fib_swap_with_the_bgp_best_path_unchanged():
    after = base()
    after.rib("edge1", "203.0.113.0/24", rib("bgp", hops=("10.0.2.2",), selected=False, fib=False))
    after.rib("edge1", "203.0.113.0/24", rib("static", hops=("10.0.3.2",), distance=1))
    m = run(base(), after)
    assert m.status == "failed"
    assert undeclared(m) == {("rib", "edge1", "203.0.113.0/24")}
    assert {d.key.protocol for d in m.undeclared} == {"bgp", "static"}
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"next_hop": "10.0.3.2"}}])
    assert m.status == "failed"


def test_red_large_community_edit():
    after = base()
    after.path("up1", "10.100.0.0/24", "10.0.2.1",
               path(as_path="65000 65101", next_hop="10.0.2.1", large=("65000:1:9",)))
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("path", "up1", "10.100.0.0/24")}
    assert m.undeclared[0].fields == ("large_communities",)


def test_red_static_distance_change():
    after = base()
    after.rib("edge1", "192.0.2.0/24", rib("static", hops=(), distance=5))
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("rib", "edge1", "192.0.2.0/24")}
    assert m.undeclared[0].fields == ("distance",)


def test_red_ospf_cost_change():
    after = base()
    after.rib("up1", "10.255.0.9/32", rib("ospf", hops=("10.0.2.1",), distance=110, metric=20))
    m = run(base(), after)
    assert m.status == "failed" and m.undeclared[0].fields == ("metric",)


def test_red_outbound_only_change_toward_an_external_peer():
    after = base()
    after.adj_out("edge1", "198.51.100.9", "192.0.2.0/24", attrs(as_path="65000 65000", next_hop="198.51.100.8"))
    m = run(base(), after)
    assert m.status == "failed" and undeclared(m) == {("adj_out", "edge1", "192.0.2.0/24")}
    # nothing changed on edge1's own best path: a best-path line can't explain it
    m = run(base(), after, [{"prefix": "192.0.2.0/24", "best_path_on": "edge1", "to": {"as_path": "65000"}}])
    assert m.status == "failed"
    adv = {"prefix": "192.0.2.0/24", "advertisement": {"node": "edge1", "neighbor": "198.51.100.9"}}
    assert run(base(), after, [{**adv, "to": {"as_path": "65000 65000"}}]).status == "matched"
    assert run(base(), after, [{**adv, "to": {"as_path": "65000 65000 65000"}}]).status == "failed"
    assert run(base(), after, [{**adv, "goes": "removed"}]).status == "failed"


def test_red_no_export_toward_the_outside():
    after = base()
    after.adj_out("edge1", "198.51.100.9", "192.0.2.0/24",
                  attrs(as_path="", next_hop="198.51.100.8", communities=["no-export"]))
    assert run(base(), after).status == "failed"


def test_best_path_change_explains_the_advertisement_it_propagates():
    before, after = base(), base()
    after.path("edge1", "203.0.113.0/24", "10.0.2.2",
               path(as_path="65002", next_hop="10.0.2.2", local_pref=100, communities=["65000:9"]))
    after.adj_out("edge1", "10.0.1.2", "203.0.113.0/24",
                  attrs(as_path="65002", next_hop="10.0.2.2", communities=["65000:9"]))
    after.learn("cust1", "203.0.113.0/24", "10.0.1.1", "65000 65002", communities=["65000:9"])
    lines = [{"prefix": "203.0.113.0/24", "best_path_on": "edge1", "to": {"communities": ["65000:9"]}},
             {"prefix": "203.0.113.0/24", "best_path_on": "cust1", "to": {"communities": ["65000:9"]}}]
    assert run(before, after, lines).status == "matched"
    # an outbound edit on top (a different community toward cust1) is not the propagated value
    after.adj_out("edge1", "10.0.1.2", "203.0.113.0/24",
                  attrs(as_path="65002", next_hop="10.0.2.2", communities=["65000:9", "65000:66"]))
    assert run(before, after, lines).status == "failed"


# --- session goes down -------------------------------------------------------------------------------------

def _peer1_down(lab):
    lab.session("edge1", "10.0.3.2", session(None, state="active", remote_as=65003))
    lab.session("peer1", "10.0.3.1", session(None, state="active"))
    for p in ("198.18.0.0/24",):
        lab.drop("edge1", "path", p)
        lab.drop("edge1", "rib", p)
    lab.drop("edge1", "adj_out", neighbor="10.0.3.2")
    lab.drop("peer1", "adj_out", neighbor="10.0.3.1")
    lab.drop("peer1", "path", "10.100.0.0/24")
    lab.drop("peer1", "rib", "10.100.0.0/24")
    # consequence beyond the session: cust1 loses the peer route
    lab.drop("edge1", "adj_out", "198.18.0.0/24", neighbor="10.0.1.2")
    lab.drop("cust1", "path", "198.18.0.0/24")
    lab.drop("cust1", "rib", "198.18.0.0/24")
    return lab


def test_session_goes_down_covers_only_routes_learned_over_it():
    after = _peer1_down(base())
    line = {"session": {"node": "edge1", "neighbor": "10.0.3.2"}, "goes": "down"}
    m = run(base(), after, [line])
    assert m.status == "failed"
    assert undeclared(m) == {("adj_out", "edge1", "198.18.0.0/24"), ("path", "cust1", "198.18.0.0/24"),
                             ("rib", "cust1", "198.18.0.0/24")}
    (lr,) = m.lines
    learned = {d["node"]: d["routes_learned_over_it"] for d in lr.details}
    assert learned == {"edge1": ["198.18.0.0/24"], "peer1": ["10.100.0.0/24"]}   # both ends of the one session
    m = run(base(), after, [line, {"prefix": "198.18.0.0/24", "disappears_from": ["cust1"]}])
    assert m.status == "matched", undeclared(m)


def test_session_goes_down_but_it_stayed_up():
    m = run(base(), base(), [{"session": {"node": "edge1", "neighbor": "10.0.3.2"}, "goes": "down"}])
    assert m.status == "failed" and m.not_happened


def test_session_goes_down_does_not_explain_a_failover():
    before = _two_paths(base())
    after = _two_paths(base())
    after.session("edge1", "10.0.3.2", session(None, state="idle", remote_as=65003))
    after.session("peer1", "10.0.3.1", session(None, state="idle"))
    after.drop("edge1", "path", "198.51.100.0/24", neighbor="10.0.3.2")
    after.path("edge1", "198.51.100.0/24", "10.0.2.2", path(as_path="65002 65003", next_hop="10.0.2.2"))
    after.rib("edge1", "198.51.100.0/24", rib("bgp", hops=("10.0.2.2",)))
    for lab in (before, after):   # keep the rest of the lab as it was, to isolate the failover
        lab.drop("edge1", "adj_out", neighbor="10.0.3.2")
        lab.drop("peer1", "adj_out", neighbor="10.0.3.1")
    after.drop("edge1", "path", "198.18.0.0/24")
    after.drop("edge1", "rib", "198.18.0.0/24")
    after.drop("peer1", "path", "10.100.0.0/24")
    after.drop("peer1", "rib", "10.100.0.0/24")
    m = run(before, after, [{"session": {"node": "edge1", "neighbor": "10.0.3.2"}, "goes": "down"}])
    assert m.status == "failed"
    assert ("path", "edge1", "198.51.100.0/24") in undeclared(m)     # the backup became best
    assert ("rib", "edge1", "198.51.100.0/24") in undeclared(m)


def test_session_line_needs_the_afi_when_the_session_carries_several():
    before = base()
    before.session("edge1", "10.0.3.2", session("10.0.3.1", afis=("ipv4-unicast", "ipv6-unicast"), remote_as=65003))
    after = base()
    after.session("edge1", "10.0.3.2", session(None, state="active", afis=("ipv4-unicast", "ipv6-unicast")))
    with pytest.raises(IntentError):
        run(before, after, [{"session": {"node": "edge1", "neighbor": "10.0.3.2"}, "goes": "down"}])
    m = run(before, after, [{"session": {"node": "edge1", "neighbor": "10.0.3.2", "afi": "ipv6-unicast"}, "goes": "down"}])
    assert m.status == "failed" and m.not_happened     # evaluated: the far end (peer1) is still established


# --- allow_anywhere ----------------------------------------------------------------------------------------

def test_allow_anywhere_exact_and_glob_expanded_never_supernet():
    after = base()
    after.learn("cust1", "10.200.5.0/24", "10.0.1.1", "65000 65002")
    after.learn("cust1", "10.201.0.0/24", "10.0.1.1", "65000 65002")
    m = run(base(), after, allow=["10.200.*.0/24"])
    assert m.status == "failed" and undeclared(m) == {("path", "cust1", "10.201.0.0/24"),
                                                      ("rib", "cust1", "10.201.0.0/24")}
    assert {d.key.prefix for d in m.allowed[0]} == {"10.200.5.0/24"}
    assert run(base(), after, allow=["10.0.0.0/8"]).status == "failed"            # no containment
    assert run(base(), after, allow=["10.200.5.0/24", "10.201.0.0/24"]).status == "matched"
    assert run(base(), after, allow=[{"prefix": "10.200.*.0/24", "vrf": "cust"}]).status == "failed"


def test_allow_anywhere_never_covers_sessions():
    after = base()
    after.session("edge1", "198.51.100.9", session(None, state="idle", remote_as=64999))
    after.drop("edge1", "adj_out", neighbor="198.51.100.9")
    m = run(base(), after, allow=["192.0.2.0/24"])
    assert m.status == "failed" and undeclared(m) == {("session", "edge1", "198.51.100.9")}


def test_dishonest_intent_declaring_a_leak_matches_the_diff():
    """The engine explains what is declared; it is the base-branch guards that must fail a declared leak
    (see test_verify_run). The verdict wording never says safe."""
    after = base()
    after.adj_out("edge1", "10.0.3.2", "203.0.113.0/24", attrs(as_path="65002", next_hop="10.0.2.2"))
    after.learn("peer1", "203.0.113.0/24", "10.0.3.1", "65000 65002")
    m = run(base(), after, [{"prefix": "203.0.113.0/24", "appears_on": ["peer1"]}])
    assert m.status == "matched"


# --- baseline ----------------------------------------------------------------------------------------------

def test_baseline_problems_list_every_session_not_established():
    lab = base()
    assert baseline_problems(lab.snap()) == []
    lab.session("edge1", "10.0.9.2", session(None, state="active"))
    lab.session("edge1", "10.0.3.2", replace(lab.get("edge1", "session", neighbor="10.0.3.2"), state="connect",
                                             local_address=None))
    probs = baseline_problems(lab.snap())
    assert len(probs) == 2 and all("edge1" in p for p in probs)


# --- best_path_on freezes every path but the new best (review finding 5) ------------------------------------

def test_best_path_on_the_old_best_path_changing_a_listed_attribute_is_undeclared():
    before = _two_paths(base())
    after = _swap_winner(_two_paths(base()), "weight", 100)
    lines = [{"prefix": "198.51.100.0/24", "best_path_on": "edge1",
              "to": {"weight": 100, "from": "10.0.2.2", "next_hop": "10.0.2.2", "as_path": "65002 65003"}},
             {"prefix": "198.51.100.0/24", "best_path_on": "cust1", "to": {"as_path": "65000 65002 65003"}}]
    assert run(before, after, lines).status == "matched"
    # the old best path also changes weight, to a value nobody declared: only the best flag may move on it
    after.path("edge1", "198.51.100.0/24", "10.0.3.2", path(best=False, as_path="65003", next_hop="10.0.3.2", weight=50))
    m = run(before, after, lines)
    assert m.status == "failed" and undeclared(m) == {("path", "edge1", "198.51.100.0/24")}
    assert {d.key.neighbor for d in m.undeclared} == {"10.0.3.2"}
