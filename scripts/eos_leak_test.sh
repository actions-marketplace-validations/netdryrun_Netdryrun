#!/usr/bin/env bash
# Live test: a BGP default leaked to the Arista but outranked by a local static default must still
# fail a `present: false` check ("received but not selected").
set -e
cd "$(dirname "$0")/.."
docker exec clab-ndr-arista-frr-frr1 vtysh -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" \
  -c "neighbor 10.0.200.1 default-originate" >/dev/null
docker exec clab-ndr-arista-frr-ceos1 Cli -p 15 -c $'enable\nconfigure\nip route 0.0.0.0/0 Null0\nend' >/dev/null
sleep 8
echo "--- EOS BGP table for the default:"
docker exec clab-ndr-arista-frr-ceos1 Cli -p 15 -c "show ip bgp 0.0.0.0/0" | grep -E "BGP routing table|best|Received|Not|valid" | head -5
cat > /tmp/eos-leak.yml <<EOF
lab: $(pwd)/examples/arista-frr/topology.clab.yml
checks:
  - {type: route, node: ceos1, prefix: 0.0.0.0/0, protocol: bgp, present: false, name: "leaked default must be absent"}
EOF
bash scripts/dev.sh check /tmp/eos-leak.yml --no-step-summary --hold 4 --settle 1 | grep -E "PASS|FAIL"
# undo
docker exec clab-ndr-arista-frr-ceos1 Cli -p 15 -c $'enable\nconfigure\nno ip route 0.0.0.0/0 Null0\nend' >/dev/null
docker exec clab-ndr-arista-frr-frr1 vtysh -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" \
  -c "no neighbor 10.0.200.1 default-originate" >/dev/null
