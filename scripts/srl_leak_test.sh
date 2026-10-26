#!/usr/bin/env bash
# Live test: a BGP default leaked to SR Linux but outranked by a local static (blackhole) default
# must still fail a `present: false` check. Also captures the real outputs as test fixtures.
set -e
cd "$(dirname "$0")/.."
export CLAB_LABDIR_BASE="$HOME/.cache/netdryrun/labs"
containerlab deploy -t examples/srl-frr/topology.clab.yml --reconfigure >/dev/null 2>&1
until docker exec clab-ndr-srl-frr-srl1 sr_cli "show network-instance default protocols bgp neighbor" 2>/dev/null | grep -q established; do sleep 5; done
docker exec clab-ndr-srl-frr-frr1 vtysh -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" \
  -c "neighbor 10.0.100.1 default-originate" >/dev/null
printf '%s\n' "enter candidate" \
  "set / network-instance default next-hop-groups group bh blackhole" \
  "set / network-instance default static-routes route 0.0.0.0/0 next-hop-group bh" \
  "set / network-instance default static-routes route 0.0.0.0/0 admin-state enable" \
  "commit now" | docker exec -i clab-ndr-srl-frr-srl1 sr_cli >/dev/null
sleep 10
cat > /tmp/srl-leak.yml <<EOF
lab: $(pwd)/examples/srl-frr/topology.clab.yml
checks:
  - {type: route, node: srl1, prefix: 0.0.0.0/0, protocol: bgp, present: false, name: "leaked default must be absent"}
  - {type: route, node: srl1, prefix: 192.168.20.0/24, protocol: bgp, name: "normal BGP route still present"}
EOF
bash scripts/dev.sh check /tmp/srl-leak.yml --no-step-summary --hold 4 --settle 1 | grep -E "PASS|FAIL|ERROR" || true
S="docker exec clab-ndr-srl-frr-srl1 sr_cli --output-format json"
$S "info from state /network-instance default route-table ipv4-unicast route 0.0.0.0/0 id * route-type * route-owner * origin-network-instance *" > tests/fixtures/srl_leak_route.txt
$S "info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route 0.0.0.0/0 neighbor * origin-protocol * path-id *" > tests/fixtures/srl_leak_rib.txt
$S "info from state /network-instance default bgp-rib afi-safi ipv4-unicast ipv4-unicast local-rib route 10.99.0.0/16 neighbor * origin-protocol * path-id *" > tests/fixtures/srl_rib_empty.txt
wc -c tests/fixtures/srl_leak_route.txt tests/fixtures/srl_leak_rib.txt tests/fixtures/srl_rib_empty.txt
containerlab destroy -t examples/srl-frr/topology.clab.yml --cleanup >/dev/null 2>&1
