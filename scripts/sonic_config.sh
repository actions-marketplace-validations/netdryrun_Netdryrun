#!/usr/bin/env bash
# Configure the SONiC node of examples/sonic-frr after boot: IPs via the SONiC CLI, BGP via vtysh.
C=${1:-clab-ndr-sonic-frr-sonic1}
until docker exec "$C" bash -lc "supervisorctl status orchagent 2>/dev/null | grep -q RUNNING && supervisorctl status bgpd | grep -q RUNNING"; do sleep 3; done
sleep 10
docker exec "$C" bash -lc "config interface ip add Ethernet0 10.0.40.1/30; config interface startup Ethernet0; config loopback add Loopback0 2>/dev/null; config interface ip add Loopback0 192.168.40.1/32"
docker exec "$C" vtysh -c "conf t" -c "router bgp 65040" -c "bgp router-id 40.40.40.40" -c "no bgp ebgp-requires-policy" \
  -c "neighbor 10.0.40.2 remote-as 65020" -c "address-family ipv4 unicast" -c "network 192.168.40.1/32" -c "end" -c "write memory" >/dev/null
for _ in $(seq 1 30); do
  docker exec "$C" vtysh -c "show bgp summary" | grep -q "^10.0.40.2.*[0-9]\s*$" && break; sleep 3
done
docker exec "$C" vtysh -c "show bgp summary" | tail -4
docker exec "$C" vtysh -c "show ip route 192.168.20.0/24"
echo "--- kernel route:"; docker exec "$C" ip route get 192.168.20.1
echo "--- ping:"; docker exec "$C" ping -c 3 -W 1 -I 192.168.40.1 192.168.20.1 | tail -2
