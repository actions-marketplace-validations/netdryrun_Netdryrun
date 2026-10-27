#!/usr/bin/env python3
"""Stage 1 of the pipeline: analyse the FRR configs with Batfish, without booting anything.

Batfish has no stand-alone FRR format: a bare frr.conf is detected as Cisco IOS and only partly
parsed. Its FRR grammar is used for Cumulus Linux, so each frr.conf is wrapped in the "Cumulus
concatenated" layout (hostname, an interfaces section, a ports.conf marker, then frr.conf).

Usage: batfish_check.py CONFIG_DIR
  Needs a Batfish service: BATFISH_HOST (default localhost); waits up to BATFISH_WAIT seconds (default 60) for it.
Exit codes: 0 every check passed, 1 a check failed, 2 setup error.
"""
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

ROUTERS = ["r1", "r2", "r3"]
# The same intent as netdryrun.yml, as far as Batfish can express it.
R1_EXPECTED = {"192.168.2.0/24": ("65002", "10.0.12.2"), "192.168.3.0/24": ("65003", "10.0.13.2")}
FAILOVER = ("r1", "eth1", "192.168.2.0/24", "65003 65002", "10.0.13.2")  # node, interface down, prefix, AS path, next hop


def nh_ip(next_hop) -> str:
    return str(getattr(next_hop, "ip", next_hop))


def wrap(hostname: str, frr_conf: str) -> str:
    return (f"{hostname}\n"
            "# This file describes the network interfaces available on your system\n"
            "auto lo\niface lo inet loopback\n\n"
            "# ports.conf --\n"
            "frr version 10.4.1\n" + frr_conf)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: batfish_check.py CONFIG_DIR"); return 2
    try:
        from pybatfish.client.session import Session
        from pybatfish.datamodel.flow import HeaderConstraints
        from pybatfish.datamodel.primitives import Interface
    except ImportError:
        print("pybatfish is not installed (pip install pybatfish)"); return 2
    logging.getLogger("pybatfish").setLevel(logging.ERROR)
    src = Path(sys.argv[1])
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""), flush=True)

    # A freshly started Batfish container needs a few seconds before it answers.
    deadline = time.monotonic() + float(os.environ.get("BATFISH_WAIT", "60"))
    while True:
        try:
            bf = Session(host=os.environ.get("BATFISH_HOST", "localhost"))
            bf.list_networks()
            break
        except Exception as e:  # connection refused, service still starting, ...
            if time.monotonic() > deadline:
                print(f"Batfish is not reachable: {e}"); return 2
            time.sleep(1)

    t0 = time.monotonic()
    with tempfile.TemporaryDirectory() as snap:
        (Path(snap) / "configs").mkdir()
        for r in ROUTERS:
            conf = (src / f"{r}.conf").read_text()
            (Path(snap) / "configs" / f"{r}.cfg").write_text(wrap(r, conf))
        bf.set_network("netdryrun-pipeline")
        bf.init_snapshot(snap, name="candidate", overwrite=True)
    q = bf.q
    print(f"Batfish: snapshot loaded in {time.monotonic() - t0:.1f}s")

    parse = q.fileParseStatus().answer().frame()
    bad = parse[parse.Status != "PASSED"]
    check("every config parses", bad.empty,
          "; ".join(f"{r.File_Name}: {r.Status} as {r.File_Format}" for r in bad.itertuples()))
    warns = q.parseWarning().answer().frame()
    for w in warns.itertuples():
        print(f"        parse warning {w.Filename}:{w.Line}: {w.Text!r}")

    undef = q.undefinedReferences().answer().frame()
    check("no undefined references", undef.empty,
          "; ".join(f"{u.Struct_Type} {u.Ref_Name} used at {u.Lines}" for u in undef.itertuples()))

    sess = q.bgpSessionStatus().answer().frame()
    down = sess[sess.Established_Status != "ESTABLISHED"]
    check(f"all {len(sess)} BGP sessions establish", len(sess) > 0 and down.empty,
          "; ".join(f"{s.Node} -> {s.Remote_IP}: {s.Established_Status}" for s in down.itertuples()))

    rib = q.bgpRib().answer().frame()
    best = rib[rib.Status.apply(lambda s: "BEST" in s)]

    def best_path(node, prefix, frame=best):
        rows = frame[(frame.Node == node) & (frame.Network == prefix)]
        return [(str(r.AS_Path), nh_ip(r.Next_Hop)) for r in rows.itertuples()]

    for prefix, (as_path, nh) in R1_EXPECTED.items():
        got = best_path("r1", prefix)
        check(f"r1 selects {prefix} via AS {as_path}, next hop {nh}", (as_path, nh) in got, f"best: {got or 'none'}")
    defaults = rib[rib.Network == "0.0.0.0/0"]
    check("no router learns 0.0.0.0/0 over BGP", defaults.empty,
          "; ".join(f"{d.Node} from {nh_ip(d.Next_Hop)}" for d in defaults.itertuples()))

    tr = q.traceroute(startLocation="r1", headers=HeaderConstraints(srcIps="192.168.1.1", dstIps="192.168.2.1")).answer().frame()
    dispositions = sorted({str(t.disposition) for row in tr.Traces for t in row})
    check("r1 192.168.1.1 reaches 192.168.2.1", dispositions == ["ACCEPTED"], ", ".join(dispositions))

    node, intf, prefix, as_path, nh = FAILOVER
    bf.fork_snapshot("candidate", name="failover", deactivate_interfaces=[Interface(hostname=node, interface=intf)], overwrite=True)
    frib = q.bgpRib().answer(snapshot="failover").frame()
    got = best_path(node, prefix, frib[frib.Status.apply(lambda s: "BEST" in s)])
    check(f"{node} {intf} down: {prefix} fails over to AS {as_path}", (as_path, nh) in got, f"best: {got or 'none'}")

    failed = results.count(False)
    print(f"Batfish: {len(results) - failed} passed, {failed} failed in {time.monotonic() - t0:.1f}s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
