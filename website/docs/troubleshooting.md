---
title: Troubleshooting
description: Real Netdryrun errors and how to fix them. containerlab not installed, Docker permission denied, unknown nodes, labs that never converge, SR Linux on a Windows drive, missing cEOS image, lab name and port collisions, link_down on SR Linux, and MCP tool timeouts.
---

# Troubleshooting

Each error below was reproduced on purpose with Netdryrun™ 0.2.0 and containerlab 0.81.1 on WSL2 (Ubuntu 22.04). The output is copied from those runs.

Exit code `2` means the run could not complete (a config error or a lab error). Exit code `1` means a check failed. See [exit codes](reference/cli.md#exit-codes).

## containerlab is not installed

```text
$ netdryrun run my-lab
Netdryrun 0.2.0: 14 checks from my-lab/netdryrun.yml
Destroying lab...
warning: lab cleanup failed: [Errno 2] No such file or directory: 'containerlab'
ERROR: 'containerlab' not found on PATH
```

Exit code `2`. Netdryrun drives the `containerlab` CLI and needs it on `PATH`. Install it ([containerlab.dev/install](https://containerlab.dev/install/)) and check with `containerlab version`. The same error names `docker` if Docker is missing. The cleanup warning is harmless: nothing was deployed.

## Docker or containerlab permission denied

As a user who is not in the `docker` and `clab_admins` groups:

```text
$ netdryrun run my-lab
Netdryrun 0.2.0: 14 checks from my-lab/netdryrun.yml
Deploying lab my-lab (3 nodes)...
Destroying lab...
warning: lab cleanup failed: ROR
...
ERROR: containerlab deploy failed:

   ERROR

  User 'ndrtest' is not part of containerlab admin group 'clab_admins', which is required to execute this command.
  To add yourself to this group, run the following command:
      $ sudo usermod -aG clab_admins ndrtest.
```

```text
$ docker ps
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Fix: add your user to both groups, then start a new login session so the groups apply.

```bash
sudo usermod -aG docker,clab_admins "$USER"
```

On WSL, close the terminal and run `wsl --shutdown` from Windows, then open it again. Check with `id`: both groups must be listed.

```text
$ id
uid=1001(ndrtest) gid=1001(ndrtest) groups=1001(ndrtest),998(clab_admins),999(docker)
```

After this, the same user deployed and ran the lab. Running Netdryrun with `sudo` also works, but then the reports are owned by root.

## A check names a node that is not in the topology

`netdryrun validate` checks the file's syntax and values, not the node names against the topology. A typo (`r9` instead of `r1`) passes validation:

```text
$ netdryrun validate unk
OK: unk/netdryrun.yml (14 checks, lab /home/dmin/ndr-docs/unk/topology.clab.yml)
  - [bgp_session] r9: BGP session to 10.0.12.2 is established
  ...
```

`run` catches it before anything is deployed:

```text
$ netdryrun run unk
Netdryrun 0.2.0: 14 checks from unk/netdryrun.yml
Destroying lab...
ERROR: unknown node(s) r9; the topology has r1, r2, r3
```

Exit code `2`. Use the node names from the topology's `nodes:` section (`r1`), not the container names (`clab-my-lab-r1`).

## The lab never converges (timeout)

A positive check waits up to `timeout` seconds (default 120) for the network to converge, then fails. Here r1 has the wrong `remote-as` for r2 and `timeout` is 30:

```text
$ netdryrun run slow
Netdryrun 0.2.0: 14 checks from slow/netdryrun.yml
Deploying lab ndrdocs-slow (3 nodes)...
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.8s)
  ...
  [FAIL] r1: BGP session to 10.0.12.2 is established -- state is idle (30.1s)
  [FAIL] r2: BGP session to 10.0.12.1 is established -- state is idle (30.1s)
  [FAIL] r1: route 192.168.33.0/24 via bgp is present -- not active via bgp; seen: nothing (30.1s)
Convergence checks done; settling 10s before post-convergence checks...
  [FAIL] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- session is idle; prefix counts are only meaningful when established (30.4s)
  ...
Destroying lab...
FAILED: 10 passed, 4 failed (14 checks)
```

A check that fails at exactly its timeout (`30.1s` here) never reached the expected state. Two causes:

- **The change really breaks something.** The `detail` says what the router reported (`state is idle`). This is the test working.
- **The lab is slow to boot.** SR Linux, SONiC and cEOS take longer than FRR. Raise `timeout` at the top of `netdryrun.yml`, or on one check. `examples/srl-frr` uses 120.

To see why, keep the lab and look inside:

```text
$ netdryrun run slow --keep-on-failure
...
Lab ndrdocs-slow left running for debugging; destroy with: containerlab destroy -t /home/dmin/ndr-docs/slow/topology.clab.yml --cleanup
FAILED: 10 passed, 4 failed (14 checks)
$ docker exec clab-ndrdocs-slow-r1 vtysh -c "show bgp summary"
...
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.12.2       4      65099         6        12        0    0    0    never         Idle        0 N/A
r3(10.0.13.2)   4      65003        38        40        3    0    0 00:01:17            2        3 FRRouting/10.4.1_git
```

r1 expects AS 65099 at 10.0.12.2, but r2 is AS 65002. Destroy the lab with the command Netdryrun printed.

## SR Linux fails on a Windows drive (/mnt/c)

On WSL, files under `/mnt/c` are on the Windows filesystem, which has no Linux permissions. If containerlab's lab directory is there, SR Linux cannot save its config. Running containerlab directly in such a folder:

```text
$ containerlab deploy -t topology.clab.yml
11:07:03 INFO Creating lab directory path=/mnt/c/Users/.../srlmnt/clab-ndrdocs-srlmnt
11:07:03 INFO unable to adjust Labdir file ACLs: operation not supported
...
11:07:32 ERRO node "srl1" post-deploy: command execution error:Error in /system:
    Setting permissions for file '/etc/opt/srlinux/config.tmp' failed with error_code = 1 [Operation not permitted]
Error: Commit failed
```

The SR Linux container keeps running, but without its startup config, so every check fails:

```text
  [FAIL] srl1: BGP session to 10.0.100.2 is established -- neighbor 10.0.100.2 not configured (seen: none) (122.6s)
```

Netdryrun avoids this. When the topology is under `/mnt/`, it puts containerlab's lab directory in `~/.cache/netdryrun/labs` (unless you set `CLAB_LABDIR_BASE` yourself). The same folder with `netdryrun run .`:

```text
$ netdryrun run .
Netdryrun 0.2.0: 6 checks from netdryrun.yml
Deploying lab ndrdocs-srlmnt (2 nodes)...
  [PASS] srl1: BGP session to 10.0.100.2 is established -- state is established (31.2s)
  ...
PASSED: 6 passed, 0 failed (6 checks)
```

If you deploy with containerlab yourself (for example for `netdryrun check`), either keep the lab on the Linux filesystem (`~/...`) or set `CLAB_LABDIR_BASE` to a Linux path. Keeping labs on the Linux filesystem is also faster.

## The cEOS image is missing

Arista does not allow cEOS to be redistributed, so you import it yourself. If the image named in the topology is not in Docker, Docker tries to pull it from Docker Hub and fails:

```text
$ netdryrun run ceos
Netdryrun 0.2.0: 7 checks from ceos/netdryrun.yml
Deploying lab ndrdocs-ceos (2 nodes)...
Destroying lab...
ERROR: containerlab deploy failed:
10:57:23 INFO Containerlab started version=0.81.1
10:57:23 INFO Parsing & checking topology file=topology.clab.yml
10:57:23 INFO Removing directory path=/home/dmin/ndr-docs/ceos/clab-ndrdocs-ceos
10:57:23 INFO Pulling image image=docker.io/library/ceos:4.34.1F
10:57:25 ERRO Failed to pull image image=docker.io/library/ceos:4.34.1F err="Error response from daemon: pull access denied for ceos, repository does not exist or may require 'docker login'"
```

Fix: download cEOS-lab from arista.com (free account) and import it with the exact name and tag the topology uses: `docker import cEOS-lab-<version>.tar ceos:<version>`, as the comment in `examples/arista-frr/topology.clab.yml` says. Then check that Docker has it:

```text
$ docker images ceos
IMAGE          ID             DISK USAGE   CONTENT SIZE   EXTRA
ceos:4.36.3M   94cc1e5462fe       3.55GB          976MB   U
```

`examples/arista-frr` expects `ceos:4.36.3M`. Either import with that tag or change `image:` in the topology to match yours.

## Two labs with the same name

containerlab lab names are global on a machine: containers are named `clab-<lab>-<node>`. Netdryrun deploys with `containerlab deploy --reconfigure`, so a second lab with the same `name:` **replaces** the first one, even from a different folder. Here `my-lab` was left running with `--keep`, then a copy of it in `other-lab` (same `name: my-lab`) was run:

```text
$ netdryrun run other-lab
Netdryrun 0.2.0: 14 checks from other-lab/netdryrun.yml
Deploying lab my-lab (3 nodes)...
...
Destroying lab...
```

The first lab is gone:

```text
$ netdryrun check my-lab
Netdryrun 0.2.0: 14 checks from my-lab/netdryrun.yml
ERROR: lab containers not running: clab-my-lab-r1, clab-my-lab-r2, clab-my-lab-r3
```

Fix: give every lab a unique `name:`. Before you run, check what is up with `docker ps` or `containerlab inspect --all`. On a shared CI runner or machine, put something unique in the name (for example the branch).

## A host port is already in use

If a topology publishes ports on the host (`ports:` on a node), two labs cannot use the same host port:

```text
$ netdryrun run p2
Netdryrun 0.2.0: 14 checks from p2/netdryrun.yml
Deploying lab ndrdocs-p2 (3 nodes)...
Destroying lab...
ERROR: containerlab deploy failed:
...
11:05:40 ERRO node "r1" deploy: Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint clab-ndrdocs-p2-r1 (40a6a46a...): Bind for 0.0.0.0:18179 failed: port is already allocated
```

Fix: Netdryrun does not need published ports; it runs every command with `docker exec`. Remove `ports:` from the topology, or use different host ports per lab. `docker ps` shows which container holds the port.

## link_down on an SR Linux node

Failure scenarios take links down with `ip link` inside the node, which works on FRR, SONiC and cEOS but not yet on SR Linux. `validate` accepts the file; the error comes when the scenario starts, after the main checks:

```text
$ netdryrun run srl-ld
Netdryrun 0.2.0: 6 checks from srl-ld/netdryrun.yml
Deploying lab ndrdocs-srlld (2 nodes)...
  [PASS] srl1: BGP session to 10.0.100.2 is established -- state is established (16.1s)
  ...
  [PASS] frr1: ping 192.168.10.1 from 192.168.20.1 expects success -- 3/3 replies (need 2) (21.5s)
Scenario: srl1-frr1 link fails
Destroying lab...
ERROR: failure scenarios on SR Linux nodes (srl1) are not supported yet; take the link down on the FRR/Linux side of the link instead
```

Fix: take down the other end of the same link. For `examples/srl-frr`, the link is `srl1:e1-1` to `frr1:eth1`:

```yaml
scenarios:
  - name: srl1-frr1 link fails
    link_down: {node: frr1, interface: eth1}
```

The effect on the network is the same: the link is down for both sides. `node_isolated` on an SR Linux node fails the same way; isolate its neighbors' links instead.

## MCP tool calls time out in the client

`dry_run` deploys a lab, so it takes 30 seconds to several minutes. Many MCP clients give up on a tool call sooner. Reproduced with the Python MCP SDK (mcp 2.3.0) and a 20-second client timeout:

```text
MCPError: Request 'tools/call' timed out
after 20.0s
```

With a 300-second timeout, the same call returned the full result after 143 seconds.

When the client gives up, it usually stops the server, and **the lab is left running**. Right after the timeout above:

```text
$ docker ps --format '{{.Names}} {{.Status}}'
clab-my-lab-r1 Up 27 seconds
clab-my-lab-r2 Up 27 seconds
clab-my-lab-r3 Up 27 seconds
```

The next `dry_run` on the same folder redeploys over it and cleans up, or destroy it yourself with `containerlab destroy -t my-lab/topology.clab.yml --cleanup`.

Fixes:

- **Raise the client's tool timeout** to at least 5 minutes. In Claude Code, set `MCP_TOOL_TIMEOUT` (milliseconds) before starting it, for example `MCP_TOOL_TIMEOUT=600000 claude`. For other clients, look for a tool-call or request timeout setting.
- **Make the lab faster.** Lower `timeout` in `netdryrun.yml` so a broken change fails sooner, and pull images in advance so the first call does not wait on a download.
- **If the client cannot wait that long**, let the agent run `netdryrun run <folder>` in a shell and read `netdryrun-report.json`.

<!-- TODO(v0.3): add the `inconclusive` status here once ndr/v03 is merged: what it means, which errors produce it, and how it differs from `error`. -->

## Still stuck

Run with `--keep-on-failure`, look inside the nodes with `docker exec`, and read the JSON report (`--json report.json`): every check keeps the raw commands and output. If it looks like a bug, [open an issue](https://github.com/netdryrun/netdryrun/issues) with the report attached. See [Support](support.md).
