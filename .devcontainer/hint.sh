#!/usr/bin/env bash
# Prints the first command to run, in the terminal Codespaces opens and in every new one.
hint='echo; echo "  Netdryrun is ready. Run the demo (about 65 s):"; echo; echo "    bash examples/agent-demo/demo.sh"; echo'
grep -q "netdryrun-hint" ~/.bashrc 2>/dev/null || echo "$hint  # netdryrun-hint" >> ~/.bashrc
eval "$hint"
