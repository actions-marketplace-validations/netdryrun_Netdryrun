# Batfish, then Netdryrun

A two-stage gate for config changes on the FRR triangle from [`../frr-bgp`](../frr-bgp):

1. **Batfish** analyses the configs (8 checks): parsing without warnings, references, all six BGP sessions, r1's best paths, no default route on any router, a traceroute, and a link-failure fork. Nothing boots. With the Batfish service already running, the stage took 2 to 6 seconds in the runs below.
2. **Netdryrun™** boots the same configs in a containerlab lab and checks what FRR really does (10 checks): r1's sessions, the prefixes r1 receives from r2, r1's route and best path to r2's LAN, a ping, no default route on r1 or r3, and the same link failure.

The two stages check the same intent with two differences: Batfish checks the default route on all three routers (r2, which would send it, is not checked in the lab), and the lab adds a prefix count and a ping.

`pipeline.sh` runs both stages on a scratch copy; nothing in this folder is modified. By default the lab is skipped when Batfish fails. `BOTH=1` runs the lab anyway, to compare the two stages; the results below were measured that way.

## Run it

You need Linux (or WSL2) with Docker, containerlab and Netdryrun installed, as in [Getting started](https://netdryrun.com/getting-started/), plus Python 3 with `venv`. From the root of a clone of this repository:

```bash
python3 -m venv ~/.venvs/batfish && ~/.venvs/batfish/bin/pip install pybatfish==2026.9.17.3748
docker run -d --name batfish -p 9996:9996 -p 9997:9997 batfish/batfish:2026.08.27.3685
export BF_PYTHON=~/.venvs/batfish/bin/python
examples/batfish-pipeline/pipeline.sh                            # baseline: both stages pass, exit 0
BOTH=1 examples/batfish-pipeline/pipeline.sh default-leak        # both stages fail, exit 1
BOTH=1 examples/batfish-pipeline/pipeline.sh route-map-typo      # both stages fail, exit 1
BOTH=1 examples/batfish-pipeline/pipeline.sh no-policy           # Batfish passes, the lab fails, exit 1
docker rm -f batfish
```

`batfish_check.py` waits up to 60 seconds for the Batfish service to answer, so the first run can start right after `docker run`. If ports 9996 and 9997 are taken, map others and set `BATFISH_PORT` to the first one. Without `BOTH=1`, a change that fails Batfish stops there with exit code 1 and no lab is started. Netdryrun's JSON reports go to `batfish-pipeline-reports/` in the current folder (set `OUT` to change that). The lab is named `ndr-bf-pipeline`, so run one pipeline at a time on a machine.

Exit codes: 0 both stages passed, 1 a stage failed, 2 setup error (including any Batfish error that is not a failed check), 3 the lab run was inconclusive.

[`github-workflow.yml`](github-workflow.yml) is the same pipeline as two GitHub Actions jobs (Batfish as a service container, then the Netdryrun Action). It is an example to copy; this repository's CI does not run it.

## The candidate changes

Each file in [`changes/`](changes) replaces `r2.conf`:

| Change | What it does |
|---|---|
| `default-leak` | Adds `neighbor 10.0.12.1 default-originate`: r2 sends r1 a default route |
| `route-map-typo` | The outbound route-map toward r1 is `ALLOW-AL`, which does not exist |
| `no-policy` | Switches r2 to `frr defaults traditional` and drops the "allow all" route-maps |

## Results

Measured on 2026-10-27 from a fresh clone of commit f368194, following [Run it](#run-it) word for word (later commits change only this README and the website), on WSL2 (20 cores, 16 GB) with images already pulled: `batfish/batfish` (Batfish 2026.08.27.3685), pybatfish 2026.9.17.3748, Netdryrun 0.3.0 from PyPI, containerlab 0.81.1, FRR 10.4.1. Times are `pipeline.sh`'s own "Stage 1 exit ... after" and "Stage 2 exit ... after" lines. The Batfish stage includes loading the snapshot (the first run after the container starts is the slowest); the lab stage includes deploying and destroying the lab. Installing pybatfish took 14 s. Two earlier runs the same day, before the r3 default-route check was added, gave the same verdicts with times within 4 s.

| Change (command) | Batfish (8 checks) | Netdryrun lab (10 checks) | Who caught what |
|---|---|---|---|
| none (baseline): `pipeline.sh` | pass, 6 s | pass, 66 s | Both agree |
| `BOTH=1 pipeline.sh default-leak` | **fail**, 3 s: r1 and r3 learn 0.0.0.0/0 | **fail**, 68 s, 2 of 10: the default route is present on r1 and on r3 | Both, Batfish first |
| `BOTH=1 pipeline.sh route-map-typo` | **fail**, 2 s: undefined route-map `ALLOW-AL` at r2.conf line 20 | **fail**, 179 s, 2 of 10: r1 gets 0 prefixes from r2 and reaches r2's LAN the long way, through r3 | Both flag it. But Batfish's own route model still predicts r1 uses the direct path to r2; FRR denies everything through a missing route-map |
| `BOTH=1 pipeline.sh no-policy` | pass, 3 s | **fail**, 265 s, 6 of 10: r2's LAN is unreachable from r1 | **Only the lab** |

**What Batfish caught first.** The default-route leak and the route-map typo, each in 2 to 3 seconds. For the typo it names the file and line (`r2.conf line 20`: the candidate `changes/route-map-typo.conf`, copied in as `r2.conf`); for the leak it names the routers. A pipeline that stops on a Batfish failure does not spend the 68 to 179 seconds of a lab run on them.

In the lab, Netdryrun reports the leaked route on r1 and r3 as "present via bgp (not selected)": FRR picks it as the BGP best path and passes it on, but it is not the route the router installs for 0.0.0.0/0.

**What only the lab saw.** [`bgp ebgp-requires-policy`](https://docs.frrouting.org/en/latest/bgp.html#clicmd-bgp-ebgp-requires-policy) is on by default under `frr defaults traditional` and off under `datacenter` (FRR documentation). An eBGP neighbor without an inbound and outbound policy then gets nothing and sends nothing. The sessions still come up, so a session check alone passes. In the lab, r2 shows `(Policy) (Policy)` for both neighbors and 0 prefixes each way. Batfish accepted the config and predicted every route as before. It does not model this FRR default: when the command is written out explicitly, `bgp ebgp-requires-policy` is reported as an unrecognized line.

**The route-map typo** is a partial catch. Batfish's `undefinedReferences` question flags it, so the gate fails. If you look only at its routing answers, though, they say traffic still takes the direct path. Only the lab shows the real result: r1 falls back to the path through r3, and ping still works, so only the best-path check and the prefix count fail.

**The link failure** (r1-r2 down) was predicted correctly by Batfish (`fork_snapshot` with the interface deactivated) and confirmed by the lab for the baseline. In this small topology it did not show a difference between the model and the routers.

The lab runs of the three bad changes take longer than the baseline because Netdryrun's positive checks wait up to `timeout: 90` seconds for convergence before failing.

## What Batfish does that this example does not show

This test uses a small part of Batfish. It also analyses ACLs and firewall rules, searches every packet that could match a rule rather than the few a ping sends, compares two snapshots to report exactly what a change does, scales to networks far larger than a lab can boot, and supports many vendors whose software cannot run in a container. None of that needs a lab. Netdryrun does not do any of it.

## How well Batfish parses FRR

Batfish reads FRR configs as part of its Cumulus Linux and SONiC support. This example uses the Cumulus path; the probe below also tries the SONiC one.

- A bare `frr.conf` is **detected as Cisco IOS**. On these files the status was `PARTIALLY_UNRECOGNIZED` (`frr defaults datacenter` unrecognized), and interfaces were renamed `eth1` → `Ethernet1`. The BGP answers happened to be right here, but FRR syntax is then read with IOS semantics.
- **Cumulus Linux** layout: [`batfish_check.py`](batfish_check.py) wraps each `frr.conf` in the "Cumulus concatenated" layout (hostname, an interfaces section, a `ports.conf` marker, then `frr.conf`). With that, all three configs parse as `CUMULUS_CONCATENATED` with status `PASSED` and no warnings, and interface names stay as in the lab.
- **SONiC** layout (a `config_db.json` with the hostname and interface addresses, next to an unchanged `frr.conf`): the three configs also parse as `SONIC` with status `PASSED` and no warnings. Batfish predicts the same routes as through the Cumulus path, for the baseline and for `no-policy`.
- Not every FRR command or default is supported. In this test, `frr defaults traditional` is accepted without its defaults being modelled, and `bgp ebgp-requires-policy` is not recognized at all. `batfish_check.py` fails on any file that does not parse cleanly or has a parse warning, so an unrecognized line stops the gate instead of being ignored.

## Reproduce the findings

With the Batfish container from [Run it](#run-it) still running and `BF_PYTHON` set, from the root of the clone:

```bash
# How Batfish reads the configs in three layouts (bare, Cumulus, SONiC), and the route it predicts
$BF_PYTHON examples/batfish-pipeline/frr_parse_probe.py examples/batfish-pipeline/configs

# The same for the no-policy candidate: every layout still predicts r2's routes reach r1
w=$(mktemp -d) && cp examples/batfish-pipeline/configs/r*.conf "$w"/
cp examples/batfish-pipeline/changes/no-policy.conf "$w/r2.conf"
$BF_PYTHON examples/batfish-pipeline/frr_parse_probe.py "$w" | grep -E '^==|best path'
rm -rf "$w"

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

Expected: the bare configs are `PARTIALLY_UNRECOGNIZED as CISCO_IOS` with r1's interfaces named `Ethernet1, Ethernet2, Loopback`; the Cumulus ones are `PASSED as CUMULUS_CONCATENATED` with `eth1, eth2, lo`; the SONiC ones are `PASSED as SONIC` with `eth1, eth2`. All three predict `AS 65002 via 10.0.12.2` for r1's path to r2's LAN, and they predict the same for the `no-policy` candidate. The explicit command gives `FAIL  every config parses, with no parse warnings` with `r2.conf line 15: 'bgp ebgp-requires-policy' not recognized`. FRR shows both of r2's neighbors with `(Policy)` in the `State/PfxRcd` and `PfxSnt` columns.

This example covers BGP with route-maps on three routers. It says nothing about Batfish's support for other FRR features or other vendors, where its coverage is much broader.
