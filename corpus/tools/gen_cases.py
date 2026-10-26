"""One-time generator for corpus/cases/02..30. Kept for transparency; edit the YAML files directly afterwards."""
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parents[1] / "cases"

CASES = [
    ("02-med-to-upstream", "Set MED on routes sent to the upstream", "traffic-engineering", "safe",
     "Adds a metric to the upstream export clause. Changes path attributes only; nothing leaks or disappears.", None,
     [{"node": "pe1", "append": "route-map TO-UPSTREAM permit 10\n set metric 50"}]),
    ("03-prepend-to-peer", "Prepend our AS twice toward the peer", "traffic-engineering", "safe",
     "Routine inbound traffic engineering. The same prefixes are still announced.", None,
     [{"node": "pe2", "append": "route-map TO-PEER permit 10\n set as-path prepend 65000 65000"}]),
    ("04-tag-community-upstream", "Tag our aggregate with an informational community toward the upstream", "hygiene", "safe",
     "Adds a community on the OWN clause. Attribute change only.", None,
     [{"node": "pe1", "append": "route-map TO-UPSTREAM permit 20\n set community 65000:999 additive"}]),
    ("05-description-only", "Change an interface description", "hygiene", "safe",
     "Cosmetic change. Must never be blocked.", None,
     [{"node": "pe1", "replace": " description to-upstream-up1", "with": " description to-upstream-up1 (transit, CHG-1042)"}]),
    ("06-customer-adds-prefix", "Customer announces a second allowed /24", "customer-growth", "safe",
     "The customer adds 10.100.1.0/24, inside its registered 10.100.0.0/22. Announcing it upstream is the desired outcome.",
     "Normal customer growth inside the registered range.",
     [{"node": "ce1", "append": "ip route 10.100.1.0/24 blackhole\nrouter bgp 65100\n address-family ipv4 unicast\n  network 10.100.1.0/24\n exit-address-family"}]),
    ("07-tighten-max-prefix", "Lower the customer maximum-prefix from 100 to 50", "hygiene", "safe",
     "Tightening a safety limit that is still far above the customer's real count.", None,
     [{"node": "pe1", "replace": "maximum-prefix 100", "with": "maximum-prefix 50"}]),
    ("08-upstream-timers", "Shorten BGP timers toward the upstream", "hygiene", "safe",
     "Faster failure detection; the session stays up.", None,
     [{"node": "pe1", "append": "router bgp 65000\n neighbor 10.0.2.2 timers 10 30"}]),
    ("09-customer-localpref", "Lower customer local-preference from 300 to 250", "traffic-engineering", "safe",
     "Customer routes stay the most preferred (peer 200, upstream 100).", None,
     [{"node": "pe1", "replace": " set local-preference 300", "with": " set local-preference 250"}]),
    ("10-transit-export-filter-removed", "Upstream export filter replaced with permit-all", "route-leak", "unsafe",
     "pe1 now announces everything to the upstream, including the peer's route: free transit for the peer, a classic route leak.",
     "Route leak as defined in RFC 7908.",
     [{"node": "pe1", "replace": "  neighbor 10.0.2.2 route-map TO-UPSTREAM out", "with": "  neighbor 10.0.2.2 route-map TO-CUSTOMER out"}]),
    ("11-peer-export-filter-removed", "Peer export filter replaced with permit-all", "route-leak", "unsafe",
     "pe2 announces upstream routes and the default to the peer: a route leak toward the peer.",
     "Route leak as defined in RFC 7908.",
     [{"node": "pe2", "append": "route-map ALLOW-ALL permit 10"},
      {"node": "pe2", "replace": "  neighbor 10.0.4.2 route-map TO-PEER out", "with": "  neighbor 10.0.4.2 route-map ALLOW-ALL out"}]),
    ("12-ibgp-send-community-dropped", "send-community removed on the pe1 to pe2 iBGP session", "policy-bug", "unsafe",
     "pe2 no longer sees the customer community, so it stops announcing the customer route to the peer.",
     "A common mistake when rebuilding iBGP sessions.",
     [{"node": "pe1", "replace": "  neighbor 10.0.3.2 send-community\n", "with": ""}]),
    ("13-upstream-asn-typo", "Typo in the upstream's ASN (65020 instead of 65200)", "fat-finger", "unsafe",
     "The upstream session never comes up; the customer loses internet access.", None,
     [{"node": "pe1", "replace": " neighbor 10.0.2.2 remote-as 65200", "with": " neighbor 10.0.2.2 remote-as 65020"}]),
    ("14-peer-session-shutdown", "Peer session administratively shut down", "fat-finger", "unsafe",
     "The peer route disappears and the peer loses our routes.", None,
     [{"node": "pe2", "append": "router bgp 65000\n neighbor 10.0.4.2 shutdown"}]),
    ("15-customer-filter-too-strict", "Customer prefix-list typo rejects the customer's /24", "policy-bug", "unsafe",
     "le 23 instead of le 24 drops the customer's only prefix, so the customer becomes unreachable from the internet.", None,
     [{"node": "pe1", "replace": "permit 10.100.0.0/22 le 24", "with": "permit 10.100.0.0/22 le 23"}]),
    ("16-mass-withdrawal", "Upstream export policy denies everything", "withdrawal", "unsafe",
     "Every route we announce to the upstream is withdrawn: our aggregate and the customer vanish from the upstream.",
     "Mass-withdrawal outage class (the 2021 Facebook outage began with withdrawn routes).",
     [{"node": "pe1",
       "replace": "route-map TO-UPSTREAM permit 10\n match community CUSTOMER\n!\nroute-map TO-UPSTREAM permit 20\n match ip address prefix-list OWN\n",
       "with": "route-map TO-UPSTREAM deny 10\n"}]),
    ("17-default-leaked-to-peer", "default-originate configured toward the peer", "route-leak", "unsafe",
     "We offer the peer a default route, so the peer can send all its traffic through us for free.", None,
     [{"node": "pe2", "append": "router bgp 65000\n address-family ipv4 unicast\n  neighbor 10.0.4.2 default-originate\n exit-address-family"}]),
    ("18-redistribute-connected", "redistribute connected added on pe1", "hygiene", "unsafe",
     "Infrastructure /30s and loopbacks go to the customer and into iBGP. Export filters keep them from the upstream and the peer, but leaking infrastructure to customers is rejected in review.",
     "Not covered by the intent spec, which has no check for infrastructure routes at the customer.",
     [{"node": "pe1", "append": "router bgp 65000\n address-family ipv4 unicast\n  redistribute connected\n exit-address-family"}]),
    ("19-nexthop-self-removed", "next-hop-self removed on pe2 toward pe1", "policy-bug", "unsafe",
     "pe1 learns the peer route with an unreachable next hop, so the customer loses the peer route.", None,
     [{"node": "pe2", "replace": "  neighbor 10.0.3.1 next-hop-self\n", "with": ""}]),
    ("20-ibgp-shutdown", "iBGP session between pe1 and pe2 shut down", "fat-finger", "unsafe",
     "The two halves of the network stop exchanging routes.", None,
     [{"node": "pe1", "append": "router bgp 65000\n neighbor 10.0.3.2 shutdown"}]),
    ("21-customer-max-prefix-removed", "Customer maximum-prefix safety limit removed", "latent-risk", "unsafe",
     "Nothing changes today, but a customer leaking a full table would now be accepted. Reviewers reject removing safety limits.",
     "Latent risk: no steady-state check can see it until the customer actually leaks. Catching it needs a failure-injection scenario (the customer sends many prefixes), planned for a later release.",
     [{"node": "pe1", "replace": "  neighbor 10.0.1.2 maximum-prefix 100\n", "with": ""}]),
    ("22-customer-leaks-third-party", "Customer announces someone else's prefix; our filter blocks it", "filter-works", "safe",
     "ce1 starts announcing 8.8.8.0/24. pe1's customer filter rejects it, so nothing leaks. The customer-side change is bad, but our network behaves correctly, so a test of our network must pass.", None,
     [{"node": "ce1", "append": "ip route 8.8.8.0/24 blackhole\nrouter bgp 65100\n address-family ipv4 unicast\n  network 8.8.8.0/24\n exit-address-family"}]),
    ("23-fat-finger-third-party-origin", "pe1 accidentally originates 8.8.8.0/24", "hijack", "unsafe",
     "A fat-fingered network statement hijacks 8.8.8.0/24 for our own customer. Export filters keep it from the upstream and the peer.",
     "Not covered by the intent spec, which has no check for unexpected routes at the customer.",
     [{"node": "pe1", "append": "ip route 8.8.8.0/24 blackhole\nrouter bgp 65000\n address-family ipv4 unicast\n  network 8.8.8.0/24\n exit-address-family"}]),
    ("24-customer-blackholed", "Static discard route for the customer prefix on pe1", "fat-finger", "unsafe",
     "The static route beats BGP, so traffic to the customer is dropped while the route is still announced.", None,
     [{"node": "pe1", "replace": "ip route 192.0.2.0/24 blackhole\n", "with": "ip route 192.0.2.0/24 blackhole\nip route 10.100.0.0/24 blackhole\n"}]),
    ("25-aggregate-typo", "Aggregate network statement typo (192.0.3.0/24)", "fat-finger", "unsafe",
     "Our own aggregate is no longer announced anywhere.", None,
     [{"node": "pe1", "replace": "  network 192.0.2.0/24", "with": "  network 192.0.3.0/24"}]),
    ("26-route-map-order-bug", "A permit-everything clause inserted before the peer export filter", "route-leak", "unsafe",
     "Sequence 5 matches everything, so upstream routes and the default leak to the peer.", None,
     [{"node": "pe2", "append": "route-map TO-PEER permit 5"}]),
    ("27-local-asn-typo", "pe2 configured with the wrong local ASN", "fat-finger", "unsafe",
     "All of pe2's sessions fail and the peer is cut off.", None,
     [{"node": "pe2", "replace": "router bgp 65000\n bgp router-id 10.255.0.2", "with": "router bgp 65001\n bgp router-id 10.255.0.2"}]),
    ("28-customer-import-policy-removed", "Customer inbound route-map removed", "policy-bug", "unsafe",
     "Without the import policy the customer's routes lose their community (or are rejected outright), so they are no longer exported upstream.", None,
     [{"node": "pe1", "replace": "  neighbor 10.0.1.2 route-map FROM-CUSTOMER in\n", "with": ""}]),
    ("29-graceful-restart", "Enable BGP graceful restart on pe1", "hygiene", "safe",
     "A resilience feature; the routing outcome is unchanged.", None,
     [{"node": "pe1", "append": "router bgp 65000\n bgp graceful-restart"}]),
    ("30-peer-import-filter-removed", "Peer inbound filter replaced with permit-all", "latent-risk", "unsafe",
     "Nothing changes today because the peer only sends its /24, but the peer could now send a default or bogons. Reviewers reject removing an import filter.",
     "Latent risk: invisible in steady state until the peer misbehaves. Needs a failure-injection scenario.",
     [{"node": "pe2", "append": "route-map ALLOW-ALL permit 10"},
      {"node": "pe2", "replace": "  neighbor 10.0.4.2 route-map FROM-PEER in", "with": "  neighbor 10.0.4.2 route-map ALLOW-ALL in"}]),
]


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(str, lambda d, s: d.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None))

for cid, title, cat, exp, why, note, edits in CASES:
    doc = {"id": cid, "title": title, "category": cat, "expected": exp, "rationale": why}
    if note:
        doc["note"] = note
    doc["edits"] = edits
    (OUT / f"{cid}.yml").write_text(yaml.dump(doc, Dumper=Dumper, sort_keys=False, width=200), encoding="utf-8")
print(f"{len(CASES)} cases written")
