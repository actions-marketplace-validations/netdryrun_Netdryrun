---
title: Troubleshooting
description: Real Netdryrun errors and how to fix them. containerlab not installed, Docker permission denied, unknown keys, unknown nodes, labs that never converge, checks not evaluated, faults that did not take effect, SR Linux on a Windows drive, missing cEOS image, lab name and port collisions, link_down on SR Linux, and MCP tool timeouts.
---

# Troubleshooting

Each error below was reproduced on purpose on WSL2 (Ubuntu 22.04) with containerlab 0.81.1, using Netdryrun™ 0.2.0, and 0.3.0 for the inconclusive case. The error messages are copied from those runs; the surrounding lines (the version, the deploy progress line, and no `Destroying lab...` when nothing was deployed) are shown as 0.3.1 prints them. The entries for errors new in 0.3.1 quote the message as the 0.3.1 code writes it.

Exit code `2` means the run has no verdict (a config error, a lab error, a fault that did not take effect, or an internal error; `--debug` shows the traceback of an internal error). Exit code `1` means a check failed. See [exit codes](reference/cli.md#exit-codes).

## Unknown key ... did you mean

```text
$ netdryrun validate my-lab
config error: checks[2]: unknown keys ['presnt'] for type route; did you mean 'present'?; allowed: active, hold, name, node, prefix, present, protocol, timeout, type, vrf
```

Exit code `2`. From 0.3.1, a key Netdryrun doesn't know is an error at every level of the file (top level, `nodes`, checks, scenarios and their faults), not only inside checks. Before 0.3.1, a misspelled key at the top level, under `nodes` or inside a fault was ignored: a whole block of checks under `chekcs:` never ran, and nothing said so. Fix the spelling the message suggests; `allowed:` lists every key that fits there. The same goes for values from a fixed list (`afi`, `protocol`, `state`, `expect`, `driver`), and a key written twice in the same mapping is an error too (`duplicate key 'present' (first defined on line 12)`). Run `netdryrun validate` after upgrading: a file that 0.3.0 accepted can fail here, and every such failure was a check that didn't test what it said.

## containerlab is not installed

```text
$ netdryrun run my-lab
Netdryrun 0.3.1: 14 checks from my-lab/netdryrun.yml
ERROR: 'containerlab' not found on PATH
```

Exit code `2`. Netdryrun drives the `containerlab` CLI and needs it on `PATH`. Install it ([containerlab.dev/install](https://containerlab.dev/install/)) and check with `containerlab version`. The same error names `docker` if Docker is missing. Nothing was deployed, so nothing is destroyed.

## Docker or containerlab permission denied

As a user who is not in the `docker` and `clab_admins` groups:

```text
$ netdryrun run my-lab
Netdryrun 0.3.1: 14 checks from my-lab/netdryrun.yml
Deploying lab my-lab (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
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

A typo (`r9` instead of `r1`) is caught before anything is deployed:

```text
$ netdryrun run unk
Netdryrun 0.3.1: 14 checks from unk/netdryrun.yml
ERROR: unknown node(s) r9; the topology has r1, r2, r3
```

From 0.3.1, `netdryrun validate` reads the topology too and catches it without starting anything (`lab error: unknown node(s) r9; ...`). Before 0.3.1, `validate` checked only the file itself and printed `OK` for this typo.

Exit code `2`, and nothing is deployed or destroyed: from 0.3.1, a lab you kept running with `--keep` survives a typo like this (0.3.0 and earlier destroyed it). Use the node names from the topology's `nodes:` section (`r1`), not the container names (`clab-my-lab-r1`).

## The lab never converges (timeout)

A positive check waits up to `timeout` seconds (default 120) for the network to converge, then fails. Here r1 has the wrong `remote-as` for r2 and `timeout` is 30:

```text
$ netdryrun run slow
Netdryrun 0.3.1: 14 checks from slow/netdryrun.yml
Deploying lab ndrdocs-slow (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] r1: BGP session to 10.0.13.2 is established -- state is established (13.8s)
  ...
  [FAIL] r1: BGP session to 10.0.12.2 is established -- state is idle (30.1s)
  [FAIL] r2: BGP session to 10.0.12.1 is established -- state is idle (30.1s)
  [FAIL] r1: route 192.168.33.0/24 via bgp is present -- not active via bgp; seen: nothing (30.1s)
Convergence checks done; settling 10s before post-convergence checks...
  ...
  [FAIL] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- not evaluated: BGP session(s) on r1 not established: 10.0.12.2 (idle) after waiting 30s. A post-convergence check only means something once every BGP session on its node is up (a leak can arrive over any of them). If a session is down on purpose, add a bgp_session check with state: down for it (30.0s)
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
Lab ndrdocs-slow left running for debugging; destroy with: containerlab destroy -t /home/user/ndr-docs/slow/topology.clab.yml --cleanup
FAILED: 10 passed, 4 failed (14 checks)
$ docker exec clab-ndrdocs-slow-r1 vtysh -c "show bgp summary"
...
Neighbor        V         AS   MsgRcvd   MsgSent   TblVer  InQ OutQ  Up/Down State/PfxRcd   PfxSnt Desc
10.0.12.2       4      65099         6        12        0    0    0    never         Idle        0 N/A
r3(10.0.13.2)   4      65003        38        40        3    0    0 00:01:17            2        3 FRRouting/10.4.1_git
```

r1 expects AS 65099 at 10.0.12.2, but r2 is AS 65002. Destroy the lab with the command Netdryrun printed.

The prefix check is a post-convergence check (it has `max`), so it reports `not evaluated`; see the next entry.

## Not evaluated (a session on the node never came up)

```text
  [FAIL] r1: prefixes from 10.0.12.2 >= 2 and <= 10 -- not evaluated: BGP session(s) on r1 not established: 10.0.12.2 (idle) after waiting 30s. A post-convergence check only means something once every BGP session on its node is up (a leak can arrive over any of them). If a session is down on purpose, add a bgp_session check with state: down for it
```

Exit code `1`. From 0.3.1, a post-convergence check (a route that must be absent, a ping that must fail, a prefix count with `max` or `exact`, a `bgp_route` attribute) starts only once every configured BGP neighbor on its node is up with stable prefix counts. A leak can arrive over any session, so a check that passed while one was still down would prove nothing. Netdryrun waits up to the largest `timeout` of the node's post-convergence checks; if a session is still down then, those checks fail as `not evaluated` and name the session.

Fix: if the session should be up, it's a finding: look at it as in [the lab never converges](#the-lab-never-converges-timeout), or raise `timeout` for a slow NOS. If it is down on purpose (a shut neighbor, a peer that isn't in the lab), add a check that says so, and the wait leaves it out:

```yaml
- type: bgp_session
  node: r1
  neighbor: 10.0.12.2
  state: down
```

## The fault did not take effect

```text
ERROR: scenario 'r1-r2 link fails': the fault did not take effect within 30s: BGP session(s) over the downed links still established (r2 -> 10.0.12.1). Netdryrun won't judge the scenario's checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) to notice a failure: raise the checks' timeout, or lower the hold timers in the lab
```

Exit code `2`. From 0.3.1, after taking links down a scenario waits until every BGP session that ran over them is down on both ends, so its checks are never judged on the state from before the failure. The wait is capped at the largest `timeout` of the scenario's checks. Here the far end, r2, still had the session up when the time ran out: without BFD, a router notices a dead link only when its BGP hold timer expires (180 s on FRR by default).

Fix: give the scenario's checks a `timeout` above the hold time (for example `timeout: 200` on them, or at the top of the file), lower the hold timers in the lab configs (`timers bgp 3 9` on FRR), or enable BFD. The links are restored and the lab destroyed as usual. See [scenario timing](reference/config.md#scenario-timing).

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
Netdryrun 0.3.1: 6 checks from netdryrun.yml
Deploying lab ndrdocs-srlmnt (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [PASS] srl1: BGP session to 10.0.100.2 is established -- state is established (31.2s)
  ...
PASSED: 6 passed, 0 failed (6 checks)
```

If you deploy with containerlab yourself (for example for `netdryrun check`), either keep the lab on the Linux filesystem (`~/...`) or set `CLAB_LABDIR_BASE` to a Linux path. Keeping labs on the Linux filesystem is also faster.

## The cEOS image is missing

Arista does not allow cEOS to be redistributed, so you import it yourself. If the image named in the topology is not in Docker, Docker tries to pull it from Docker Hub and fails:

```text
$ netdryrun run ceos
Netdryrun 0.3.1: 7 checks from ceos/netdryrun.yml
Deploying lab ndrdocs-ceos (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
Destroying lab...
ERROR: containerlab deploy failed:
10:57:23 INFO Containerlab started version=0.81.1
10:57:23 INFO Parsing & checking topology file=topology.clab.yml
10:57:23 INFO Removing directory path=/home/user/ndr-docs/ceos/clab-ndrdocs-ceos
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

## A lab named X is already running

```text
ERROR: a lab named 'my-lab' is already running (3 container(s), e.g. clab-my-lab-r1): another Netdryrun run, or a lab deployed by hand or kept with --keep. Netdryrun won't redeploy or destroy it. Wait for the other run to finish, or remove the lab with: containerlab destroy -t /home/user/my-lab/topology.clab.yml --cleanup
```

Exit code `2`, before anything is deployed. containerlab lab names are global on a machine: containers are named `clab-<lab>-<node>`. From 0.3.1, `netdryrun run` refuses to deploy a lab whose name is already in use, because redeploying would reconfigure the other lab's containers, and destroying it afterwards would remove them from under whoever is using it. Two runs of the same lab started at the same moment on one host get `another Netdryrun run is already using lab 'my-lab' on this host` instead.

Fix: wait for the other run, destroy the old lab with the command in the message (for a lab you kept with `--keep` or `--keep-on-failure`), or give every lab a unique `name:`. On a shared CI runner or machine, put something unique in the name (for example the branch). `netdryrun check` doesn't deploy, so it still runs against the running lab.

Before 0.3.1, Netdryrun deployed with `containerlab deploy --reconfigure` regardless, so a second lab with the same `name:` **replaced** the first one, even from a different folder. Here, on 0.2.0, `my-lab` was left running with `--keep`, then a copy of it in `other-lab` (same `name: my-lab`) was run:

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

Before you run, check what is up with `docker ps` or `containerlab inspect --all`.

## A host port is already in use

If a topology publishes ports on the host (`ports:` on a node), two labs cannot use the same host port:

```text
$ netdryrun run p2
Netdryrun 0.3.1: 14 checks from p2/netdryrun.yml
Deploying lab ndrdocs-p2 (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
Destroying lab...
ERROR: containerlab deploy failed:
...
11:05:40 ERRO node "r1" deploy: Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint clab-ndrdocs-p2-r1 (40a6a46a...): Bind for 0.0.0.0:18179 failed: port is already allocated
```

Fix: Netdryrun does not need published ports; it runs every command with `docker exec`. Remove `ports:` from the topology, or use different host ports per lab. `docker ps` shows which container holds the port.

## link_down on an SR Linux node

Failure scenarios take links down with `ip link` inside the node, which works on FRR, SONiC and cEOS but not yet on SR Linux. From 0.3.1, `netdryrun validate` refuses the file (exit code `2`). `run` finds out only when the scenario starts, after the main checks:

```text
$ netdryrun run srl-ld
Netdryrun 0.3.1: 6 checks from srl-ld/netdryrun.yml
Deploying lab ndrdocs-srlld (2 nodes); this usually takes 30-90 s, longer the first time images are pulled...
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

## No PR comment on a big lab

With `pr-comment: true`, the job log says `could not comment on the PR (needs permissions pull-requests: write ...)` even though the permission is set, and the lab has several hundred checks, for example a file `netdryrun record` wrote for a 20-node lab.

GitHub rejects a comment longer than 65,536 characters. Netdryrun 0.3.0 lists every check in the comment, about 90 characters each, so above roughly 700 checks the comment is too long. The verdict, the job status and the reports are not affected. Fixed in 0.3.1: the table stops before the limit, failures first, and says how many checks it left out. On 0.3.0, trim the recorded file to the checks that matter, or split it into several `netdryrun.yml` files run as a [matrix](github-action.md#several-labs).

## Inconclusive: the lab never came up

Exit code `3` means checks failed, but the lab never reached a testable state, so the result says nothing about your change. Reproduced with Netdryrun 0.3.0 by turning off `bgpd` in the FRR `daemons` file of a copy of `examples/frr-bgp` (and `timeout: 30`):

```text
$ netdryrun run . --json report.json
Netdryrun 0.3.1: 7 checks from netdryrun.yml
Deploying lab ndrdocs-nobgp (3 nodes); this usually takes 30-90 s, longer the first time images are pulled...
  [FAIL] r1: BGP session to 10.0.12.2 is established -- error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running (33.1s)
  [FAIL] r1: BGP session to 10.0.13.2 is established -- error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running (33.1s)
  [FAIL] r1: route 192.168.3.0/24 via bgp is present -- not active via bgp; seen: nothing (33.1s)
  [FAIL] r1: ping 192.168.3.1 from 192.168.1.1 expects success -- 0/3 replies (need 2) (33.1s)
  [FAIL] r1: BGP best path for 192.168.2.0/24 has as-path '65002', next hop 10.0.12.2 -- error: `vtysh -c show bgp ipv4 unicast 192.168.2.0/24 json` failed on r1 (rc=1): bgpd is not running (33.1s)
Convergence checks done; settling 10s before post-convergence checks...
  [FAIL] r1: prefixes from 10.0.12.2 >= 1 and <= 10 -- error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running (30.1s)
  [PASS] r1: route 0.0.0.0/0 via bgp is absent -- absent (held 10s, 5 samples) (10.1s)
Destroying lab...
INCONCLUSIVE: the lab did not reach a testable state: r1 never returned usable BGP state (r1: error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running), and no check passed on any sample. Rerun with a longer timeout, or check that the lab boots (6 of 7 checks failed; this says nothing about the change)
  wrote json report: report.json
```

The JSON report has the same text in `inconclusive_reason`, and every unready sample in `history` is marked:

```json
{"t": 33.1, "passed": false, "detail": "error: `vtysh -c show bgp neighbors json` failed on r1 (rc=1): bgpd is not running", "unready": true}
```

How it differs from the other results:

- **`error` (exit `2`):** the run could not start or finish: a config error, a missing tool, a failed deploy, a fault that did not take effect.
- **`failed` (exit `1`):** the lab was up and something is wrong. A configured BGP session that is down (an ASN typo, as in [the lab never converges](#the-lab-never-converges-timeout)) is `failed`, not `inconclusive`.
- **`inconclusive` (exit `3`):** no positive check passed on any sample, and every failed check is on a node whose CLI or BGP never answered.

Fix: check that the lab boots (`containerlab inspect`, `docker logs <container>`), that the routing daemon is enabled, and that `timeout` is long enough for slow NOSes, then rerun. One known limit: a change that deletes a node's whole BGP config looks the same and is reported `inconclusive`. It is still never `passed`. See the [full rules](reference/cli.md#when-a-run-is-inconclusive).

## Still stuck

Run with `--keep-on-failure`, look inside the nodes with `docker exec`, and read the JSON report (`--json report.json`): every check keeps the raw commands and output. If it looks like a bug, [open an issue](https://github.com/netdryrun/netdryrun/issues) with the report attached. See [Support](support.md).
