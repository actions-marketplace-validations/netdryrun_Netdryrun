#!/usr/bin/env python3
"""Show how Batfish reads a folder of frr.conf files in three layouts: as given, wrapped as Cumulus
concatenated (what batfish_check.py uses), and as SONiC (a minimal config_db.json next to frr.conf).
For each, print the parse status, parse warnings, r1's interface names and r1's best path to r2's LAN.

Usage: frr_parse_probe.py CONFIG_DIR     (reads r1.conf, r2.conf, r3.conf; same service settings as batfish_check.py)
"""
import json
import logging
import re
import sys
import tempfile
from pathlib import Path

from batfish_check import ROUTERS, connect, nh_ip, wrap


def interfaces(frr_conf: str) -> dict:
    """{name: address} from 'interface X' / ' ip address Y' stanzas, loopback excluded."""
    found = re.findall(r"^interface (\S+)\n ip address (\S+)", frr_conf, re.M)
    return {name: addr for name, addr in found if name != "lo"}


def sonic(snap: Path, r: str, frr_conf: str) -> None:
    d = snap / "sonic_configs" / r
    d.mkdir(parents=True)
    ifs = interfaces(frr_conf)
    config_db = {"DEVICE_METADATA": {"localhost": {"hostname": r}},
                 "PORT": {i: {"admin_status": "up"} for i in ifs},
                 "INTERFACE": {**{i: {} for i in ifs}, **{f"{i}|{a}": {} for i, a in ifs.items()}}}
    (d / "config_db.json").write_text(json.dumps(config_db, indent=1))
    (d / "frr.conf").write_text(frr_conf)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: frr_parse_probe.py CONFIG_DIR"); return 2
    logging.getLogger("pybatfish").setLevel(logging.ERROR)
    bf = connect()
    bf.set_network("netdryrun-frr-parse-probe")
    src = Path(sys.argv[1])
    layouts = (("as given (bare frr.conf)", lambda s, r, c: (s / "configs" / f"{r}.conf").write_text(c)),
               ("wrapped as Cumulus concatenated", lambda s, r, c: (s / "configs" / f"{r}.cfg").write_text(wrap(r, c))),
               ("SONiC (config_db.json + frr.conf)", sonic))
    for n, (label, write) in enumerate(layouts):
        with tempfile.TemporaryDirectory() as snap:
            (Path(snap) / "configs").mkdir()
            for r in ROUTERS:
                write(Path(snap), r, (src / f"{r}.conf").read_text())
            bf.init_snapshot(snap, name=f"layout{n}", overwrite=True)
        print(f"== {label}")
        for f in bf.q.fileParseStatus().answer().frame().itertuples():
            print(f"  {f.File_Name}: {f.Status} as {f.File_Format}")
        for w in bf.q.parseWarning().answer().frame().itertuples():
            print(f"  warning {w.Filename}:{w.Line}: {w.Text!r}")
        names = sorted(i.Interface.interface for i in bf.q.interfaceProperties().answer().frame().itertuples()
                       if i.Interface.hostname == "r1")
        print(f"  r1 interfaces: {', '.join(names)}")
        rib = bf.q.bgpRib(nodes="r1", network="192.168.2.0/24").answer().frame()
        paths = [f"AS {r.AS_Path} via {nh_ip(r.Next_Hop)}" for r in rib.itertuples() if "BEST" in r.Status]
        print(f"  r1 best path to 192.168.2.0/24: {'; '.join(paths) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
