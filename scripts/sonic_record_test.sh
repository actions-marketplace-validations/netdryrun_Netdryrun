#!/usr/bin/env bash
# Keep the SONiC lab up, record a baseline from it, capture driver fixtures, then destroy.
set -u
cd "$(dirname "$0")/.."
bash scripts/dev.sh run examples/sonic-frr --keep > /tmp/sonic-keep.log 2>&1; tail -1 /tmp/sonic-keep.log
bash scripts/dev.sh record examples/sonic-frr/topology.clab.yml --out /tmp/sonic-baseline.yml --force 2>&1 | tail -3
echo "--- baseline:"; cat /tmp/sonic-baseline.yml
C=clab-ndr-sonic-frr-sonic1; F=tests/fixtures
docker exec $C vtysh -c "show bgp neighbors json" > $F/sonic_bgp_neighbors.txt
docker exec $C vtysh -c "show ip route 192.168.20.0/24 json" > $F/sonic_route.txt
echo "--- fixtures:"; ls -la $F/sonic_*
sudo -n true 2>/dev/null; containerlab destroy -t examples/sonic-frr/topology.clab.yml --cleanup >/dev/null 2>&1 || sudo containerlab destroy -t examples/sonic-frr/topology.clab.yml --cleanup >/dev/null 2>&1
echo destroyed
