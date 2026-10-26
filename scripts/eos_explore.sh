#!/usr/bin/env bash
# Explore Arista cEOS JSON output for driver development: ./scripts/eos_explore.sh <container>
C=${1:-clab-ndr-arista-frr-ceos1}
for cmd in "show ip bgp summary | json" "show ip route 192.168.20.0/24 | json" "show ip bgp 192.168.20.0/24 | json" "show ip route | json"; do
  echo "##### $cmd"
  docker exec "$C" Cli -p 15 -c "$cmd" | head -c 1600
  echo
done
echo "##### ping"
docker exec "$C" Cli -p 15 -c "ping 192.168.20.1 source 192.168.30.1 repeat 3" | tail -4
