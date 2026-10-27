# Batfish, then Netdryrun

A two-stage gate for config changes on the FRR triangle from [`../frr-bgp`](../frr-bgp):

1. **Batfish** analyses the configs: parsing, references, BGP sessions, best paths, a default-route guard, a traceroute and a link-failure fork. Nothing boots; it takes seconds.
2. **Netdryrun™** boots the same configs in a containerlab lab and checks what FRR really does: sessions, prefixes received, best paths, ping, the default-route guard and the same link failure.

`pipeline.sh` runs both stages on a scratch copy. By default the lab is skipped when Batfish fails; `BOTH=1` runs it anyway, which is how the table below was measured.

```bash
docker run -d --name batfish -p 9996:9996 -p 9997:9997 batfish/batfish
python3 -m venv ~/.venvs/batfish && ~/.venvs/batfish/bin/pip install pybatfish
BF_PYTHON=~/.venvs/batfish/bin/python examples/batfish-pipeline/pipeline.sh                 # baseline
BF_PYTHON=~/.venvs/batfish/bin/python examples/batfish-pipeline/pipeline.sh no-policy       # a change
docker rm -f batfish
```

[`github-workflow.yml`](github-workflow.yml) is the same pipeline as two GitHub Actions jobs (Batfish as a service container, then the Netdryrun Action). It is an example to copy; this repository's CI does not run it.

## The candidate changes

Each file in [`changes/`](changes) replaces `r2.conf`:

| Change | What it does |
|---|---|
| `default-leak` | Adds `neighbor 10.0.12.1 default-originate`: r2 sends r1 a default route |
| `route-map-typo` | The outbound route-map toward r1 is `ALLOW-AL`, which does not exist |
| `no-policy` | Switches r2 to `frr defaults traditional` and drops the "allow all" route-maps |

## Results

Measured on 2026-10-27 on WSL2 (20 cores, 16 GB) with images already pulled: Batfish 2026.08.27.3685 (`batfish/allinone` and `batfish/batfish` report the same version), pybatfish 2026.9.17.3748, Netdryrun 0.3.0, containerlab 0.81.1, FRR 10.4.1. Batfish times include loading the snapshot. Lab times include deploying and destroying the lab.

| Change | Batfish (8 checks) | Netdryrun lab (9 checks) | Who caught what |
|---|---|---|---|
| none (baseline) | pass, 4 s | pass, 70 s | Both agree |
| `default-leak` | **fail**, 3 s: r1 and r3 learn 0.0.0.0/0 | **fail**, 68 s: default route present on r1 (received, not selected) | Both. Batfish first, and it also names r3 |
| `route-map-typo` | **fail**, 5 s: undefined route-map `ALLOW-AL` at r2.cfg line 27 | **fail**, 179 s: r1 gets 0 prefixes from r2 and reaches r2's LAN the long way, through r3 | Both flag it. But Batfish's own route model still predicts r1 uses the direct path to r2; FRR denies everything through a missing route-map |
| `no-policy` | pass, 3 s | **fail**, 266 s: 6 of 9 checks; r2's LAN is unreachable from r1 | **Only the lab** |

**What Batfish caught first.** The default-route leak and the route-map typo, in seconds, with the file and line for the typo. A pipeline that stops on a Batfish failure never spends a minute or three booting a lab for them.

**What only the lab saw.** Since FRR 7.4, `bgp ebgp-requires-policy` is on by default under `frr defaults traditional` (and off under `datacenter`). An eBGP neighbor without an inbound and outbound policy then gets nothing and sends nothing. The sessions still come up, so the failure is easy to miss. In the lab, r2 shows `(Policy) (Policy)` for both neighbors and 0 prefixes each way. Batfish accepted the config and predicted every route as before. It does not model this FRR default: when the command is written out explicitly, `bgp ebgp-requires-policy` is reported as an unrecognized line.

**The route-map typo** is a partial catch. Batfish's `undefinedReferences` question flags it, so the gate fails. If you look only at its routing answers, though, they say traffic still takes the direct path. Only the lab shows the real result: r1 falls back to the path through r3, and ping still works, so only the best-path check and the prefix count fail.

**The link failure** (r1-r2 down) was predicted correctly by Batfish (`fork_snapshot` with the interface deactivated) and confirmed by the lab for the baseline. In this small topology it did not show a difference between the model and the routers.

The lab runs of the three bad changes take longer than the baseline because Netdryrun's positive checks wait up to `timeout: 90` seconds for convergence before failing.

## How well Batfish parses FRR

Batfish has no stand-alone FRR config format:

- A bare `frr.conf` is **detected as Cisco IOS**. On these files the status was `PARTIALLY_UNRECOGNIZED` (`frr defaults datacenter` unrecognized), and interfaces were renamed `eth1` → `Ethernet1`. The BGP answers happened to be right here, but FRR syntax is then read with IOS semantics.
- Batfish's FRR grammar is used for **Cumulus Linux**. [`batfish_check.py`](batfish_check.py) wraps each `frr.conf` in the "Cumulus concatenated" layout (hostname, an interfaces section, a `ports.conf` marker, then `frr.conf`). With that, all three configs parse as `CUMULUS_CONCATENATED` with status `PASSED` and no warnings, and interface names stay as in the lab.
- What is supported is the subset Cumulus used. Examples from this test: `frr defaults traditional` is accepted without its defaults being modelled, and `bgp ebgp-requires-policy` is not recognized at all. Check `fileParseStatus` and `parseWarning` (the script fails on any file that does not parse cleanly) before trusting an answer for FRR.

This example covers BGP with route-maps on three routers. It says nothing about Batfish's support for other FRR features or other vendors, where its coverage is much broader.
