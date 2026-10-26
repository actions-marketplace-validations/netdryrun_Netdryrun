#!/usr/bin/env bash
# Capture real Arista cEOS outputs into tests/fixtures (normal state + the not-selected leak case).
set -e
cd "$(dirname "$0")/.."
C=clab-ndr-arista-frr-ceos1
cli() { docker exec "$C" Cli -p 15 -c "$1"; }
cli "show ip bgp summary vrf default | json" > tests/fixtures/eos_bgp_summary.txt
cli "show ip route vrf default 192.168.20.0/24 | json" > tests/fixtures/eos_route.txt
cli "show ip bgp 192.168.20.0/24 vrf default | json" > tests/fixtures/eos_bgp_route.txt
cli "ping vrf default 192.168.20.1 repeat 3 source 192.168.30.1" > tests/fixtures/eos_ping.txt
# leak case: BGP default received, static default installed instead
docker exec clab-ndr-arista-frr-frr1 vtysh -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" -c "neighbor 10.0.200.1 default-originate" >/dev/null
cli $'enable\nconfigure\nip route 0.0.0.0/0 Null0\nend' >/dev/null
sleep 8
cli "show ip route vrf default 0.0.0.0/0 | json" > tests/fixtures/eos_leak_route.txt
cli "show ip bgp 0.0.0.0/0 vrf default | json" > tests/fixtures/eos_leak_bgp.txt
cli $'enable\nconfigure\nno ip route 0.0.0.0/0 Null0\nend' >/dev/null
docker exec clab-ndr-arista-frr-frr1 vtysh -c "conf t" -c "router bgp 65020" -c "address-family ipv4 unicast" -c "no neighbor 10.0.200.1 default-originate" >/dev/null
ls -la tests/fixtures/eos_*
