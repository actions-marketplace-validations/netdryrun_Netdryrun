#!/usr/bin/env bash
# Explore a running docker-sonic-vs node: services, interfaces, FRR access.
C=${1:-clab-ndr-sonic-frr-sonic1}
x() { echo "##### $*"; docker exec "$C" bash -lc "$*" 2>&1 | head -${N:-15}; }
x "supervisorctl status 2>/dev/null | head -30"
x "ip -br link"
x "which vtysh; vtysh -c 'show version' | head -3"
x "ls /etc/frr /etc/sonic 2>/dev/null"
x "cat /usr/share/sonic/hwsku/port_config.ini 2>/dev/null | head -6"
x "show interfaces status 2>/dev/null | head -8"
