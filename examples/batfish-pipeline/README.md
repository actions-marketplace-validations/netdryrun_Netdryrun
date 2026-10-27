# Batfish, then Netdryrun

A two-stage gate for config changes on the FRR triangle from [`../frr-bgp`](../frr-bgp):

1. **Batfish** analyses the configs: parsing, references, BGP sessions, best paths, a default-route guard, a traceroute and a link-failure fork. Nothing boots; in the runs below the stage took 2 to 6 seconds.
2. **Netdryrun™** boots the same configs in a containerlab lab and checks what FRR really does: sessions, prefixes received, best paths, ping, the default-route guard and the same link failure.

`pipeline.sh` runs both stages on a scratch copy; nothing in this folder is modified. By default the lab is skipped when Batfish fails. `BOTH=1` runs the lab anyway, to compare the two stages; the results below were measured that way.

## Run it

You need Linux (or WSL2) with Docker, containerlab and Netdryrun installed, as in [Getting started](https://netdryrun.com/getting-started/), plus Python 3 with `venv`. From the root of a clone of this repository:

```bash
python3 -m venv ~/.venvs/batfish && ~/.venvs/batfish/bin/pip install pybatfish
docker run -d --name batfish -p 9996:9996 -p 9997:9997 batfish/batfish
export BF_PYTHON=~/.venvs/batfish/bin/python
examples/batfish-pipeline/pipeline.sh                            # baseline: both stages pass, exit 0
BOTH=1 examples/batfish-pipeline/pipeline.sh default-leak        # both stages fail, exit 1
BOTH=1 examples/batfish-pipeline/pipeline.sh route-map-typo      # both stages fail, exit 1
BOTH=1 examples/batfish-pipeline/pipeline.sh no-policy           # Batfish passes, the lab fails, exit 1
docker rm -f batfish
```

`batfish_check.py` waits up to 60 seconds for the Batfish service to answer, so the first run can start right after `docker run`. Without `BOTH=1`, a change that fails Batfish stops there with exit code 1 and no lab is started. The lab is named `ndr-bf-pipeline`, so run one pipeline at a time on a machine.

[`github-workflow.yml`](github-workflow.yml) is the same pipeline as two GitHub Actions jobs (Batfish as a service container, then the Netdryrun Action). It is an example to copy; this repository's CI does not run it.

## The candidate changes

Each file in [`changes/`](changes) replaces `r2.conf`:

| Change | What it does |
|---|---|
| `default-leak` | Adds `neighbor 10.0.12.1 default-originate`: r2 sends r1 a default route |
| `route-map-typo` | The outbound route-map toward r1 is `ALLOW-AL`, which does not exist |
| `no-policy` | Switches r2 to `frr defaults traditional` and drops the "allow all" route-maps |

## Results

Measured on 2026-10-27 from a fresh clone of commit c2d5c92, following [Run it](#run-it) word for word, on WSL2 (20 cores, 16 GB) with images already pulled: `batfish/batfish` (Batfish 2026.08.27.3685), pybatfish 2026.9.17.3748, Netdryrun 0.3.0 from PyPI, containerlab 0.81.1, FRR 10.4.1. Times are `pipeline.sh`'s own "Stage 1 exit ... after" and "Stage 2 exit ... after" lines. The Batfish stage includes loading the snapshot (the first run after the container starts is the slowest); the lab stage includes deploying and destroying the lab. An earlier run the same day with `batfish/allinone` (same Batfish version) gave the same results, with times within 3 s.

| Change (command) | Batfish (8 checks) | Netdryrun lab (9 checks) | Who caught what |
|---|---|---|---|
| none (baseline): `pipeline.sh` | pass, 6 s | pass, 69 s | Both agree |
| `BOTH=1 pipeline.sh default-leak` | **fail**, 2 s: r1 and r3 learn 0.0.0.0/0 | **fail**, 68 s: default route present on r1 (received, not selected) | Both. Batfish first, and it also names r3 |
| `BOTH=1 pipeline.sh route-map-typo` | **fail**, 2 s: undefined route-map `ALLOW-AL` at r2.cfg line 27 | **fail**, 177 s: r1 gets 0 prefixes from r2 and reaches r2's LAN the long way, through r3 | Both flag it. But Batfish's own route model still predicts r1 uses the direct path to r2; FRR denies everything through a missing route-map |
| `BOTH=1 pipeline.sh no-policy` | pass, 2 s | **fail**, 265 s: 6 of 9 checks; r2's LAN is unreachable from r1 | **Only the lab** |

**What Batfish caught first.** The default-route leak and the route-map typo, in seconds, with the file and line for the typo. A pipeline that stops on a Batfish failure never spends a minute or three booting a lab for them.

**What only the lab saw.** Since FRR 7.4, `bgp ebgp-requires-policy` is on by default under `frr defaults traditional` (and off under `datacenter`). An eBGP neighbor without an inbound and outbound policy then gets nothing and sends nothing. The sessions still come up, so the failure is easy to miss. In the lab, r2 shows `(Policy) (Policy)` for both neighbors and 0 prefixes each way. Batfish accepted the config and predicted every route as before. It does not model this FRR default: when the command is written out explicitly, `bgp ebgp-requires-policy` is reported as an unrecognized line.

**The route-map typo** is a partial catch. Batfish's `undefinedReferences` question flags it, so the gate fails. If you look only at its routing answers, though, they say traffic still takes the direct path. Only the lab shows the real result: r1 falls back to the path through r3, and ping still works, so only the best-path check and the prefix count fail.

**The link failure** (r1-r2 down) was predicted correctly by Batfish (`fork_snapshot` with the interface deactivated) and confirmed by the lab for the baseline. In this small topology it did not show a difference between the model and the routers.

The lab runs of the three bad changes take longer than the baseline because Netdryrun's positive checks wait up to `timeout: 90` seconds for convergence before failing.

## What Batfish does that this example does not show

This test uses a small part of Batfish. It also analyses ACLs and firewall rules, searches every packet that could match a rule rather than the few a ping sends, compares two snapshots to report exactly what a change does, scales to networks far larger than a lab can boot, and supports many vendors whose software cannot run in a container. None of that needs a lab. Netdryrun does not do any of it.

## How well Batfish parses FRR

Batfish has no stand-alone FRR config format:

- A bare `frr.conf` is **detected as Cisco IOS**. On these files the status was `PARTIALLY_UNRECOGNIZED` (`frr defaults datacenter` unrecognized), and interfaces were renamed `eth1` → `Ethernet1`. The BGP answers happened to be right here, but FRR syntax is then read with IOS semantics.
- Batfish's FRR grammar is used for **Cumulus Linux**. [`batfish_check.py`](batfish_check.py) wraps each `frr.conf` in the "Cumulus concatenated" layout (hostname, an interfaces section, a `ports.conf` marker, then `frr.conf`). With that, all three configs parse as `CUMULUS_CONCATENATED` with status `PASSED` and no warnings, and interface names stay as in the lab.
- What is supported is the subset Cumulus used. Examples from this test: `frr defaults traditional` is accepted without its defaults being modelled, and `bgp ebgp-requires-policy` is not recognized at all. Check `fileParseStatus` and `parseWarning` (the script fails on any file that does not parse cleanly) before trusting an answer for FRR.

## Reproduce the findings

With the Batfish container from [Run it](#run-it) still running and `BF_PYTHON` set, from the root of the clone:

```bash
# How Batfish parses the configs, bare and wrapped
$BF_PYTHON examples/batfish-pipeline/frr_parse_probe.py examples/batfish-pipeline/configs

# Batfish does not recognize the explicit command
w=$(mktemp -d) && cp examples/batfish-pipeline/configs/r*.conf "$w"/
sed 's/^ bgp router-id 2.2.2.2$/&\n bgp ebgp-requires-policy/' examples/batfish-pipeline/changes/no-policy.conf > "$w/r2.conf"
$BF_PYTHON examples/batfish-pipeline/batfish_check.py "$w" | grep -A1 'every config parses'
rm -rf "$w"

# What FRR does with the no-policy change: sessions up, (Policy) instead of prefix counts
w=$(mktemp -d) && cp -r examples/batfish-pipeline/configs examples/batfish-pipeline/topology.clab.yml "$w"/
cp examples/batfish-pipeline/changes/no-policy.conf "$w/configs/r2.conf"
containerlab deploy -t "$w/topology.clab.yml" && sleep 30
docker exec clab-ndr-bf-pipeline-r2 vtysh -c "show bgp ipv4 unicast summary"
containerlab destroy -t "$w/topology.clab.yml" --cleanup && rm -rf "$w"
```

Expected: the bare configs are `PARTIALLY_UNRECOGNIZED as CISCO_IOS` with r1's interfaces named `Ethernet1, Ethernet2, Loopback`, and the wrapped ones are `PASSED as CUMULUS_CONCATENATED` with `eth1, eth2, lo`. The explicit command gives `FAIL  every config parses` and a warning for `' bgp ebgp-requires-policy'`. FRR shows both of r2's neighbors with `(Policy)` in the `State/PfxRcd` and `PfxSnt` columns.

This example covers BGP with route-maps on three routers. It says nothing about Batfish's support for other FRR features or other vendors, where its coverage is much broader.
