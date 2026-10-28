#!/usr/bin/env bash
# Rerun corpus case 12 with the lab kept, then show whether pe2 still gets the customer community.
cd "$(dirname "$0")/.." || exit 2
NDR_BIN=python bash scripts/dev.sh corpus/run.py --case 12 --keep 2>&1 | grep -E "^==|ping=|ERROR"
P=$(docker ps --format '{{.Names}}' | grep -E 'pe1$' | head -1); P=${P%pe1}
echo "--- containers prefix: $P"
echo "--- pe1 running config, neighbor 10.0.3.2:"; docker exec ${P}pe1 vtysh -c "show running-config" | grep "10.0.3.2"
echo "--- pe1 advertised to pe2 (community):"; docker exec ${P}pe1 vtysh -c "show bgp ipv4 unicast neighbors 10.0.3.2 advertised-routes detail" 2>/dev/null | grep -iE "^BGP routing table entry|Community" | head -10
echo "--- pe2 customer routes with community:"; docker exec ${P}pe2 vtysh -c "show bgp ipv4 unicast community 65000:100" | tail -6
echo "--- peer1 routes:"; docker exec ${P}peer1 vtysh -c "show bgp ipv4 unicast" | grep -E "^\*" | head
for n in pe1 pe2 ce1 up1 peer1; do docker rm -f ${P}$n >/dev/null 2>&1; done; echo cleaned
