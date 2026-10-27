#!/usr/bin/env python3
"""Show how Batfish parses a folder of frr.conf files: as given, and wrapped as Cumulus concatenated.

Usage: frr_parse_probe.py CONFIG_DIR     (reads r1.conf, r2.conf, r3.conf; same service settings as batfish_check.py)
"""
import logging
import os
import sys
import tempfile
from pathlib import Path

from batfish_check import ROUTERS, wrap


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: frr_parse_probe.py CONFIG_DIR"); return 2
    from pybatfish.client.session import Session
    logging.getLogger("pybatfish").setLevel(logging.ERROR)
    bf = Session(host=os.environ.get("BATFISH_HOST", "localhost"))
    bf.set_network("netdryrun-frr-parse-probe")
    src = Path(sys.argv[1])
    for label, ext, convert in (("as given (bare frr.conf)", "conf", lambda r, c: c),
                                ("wrapped as Cumulus concatenated", "cfg", wrap)):
        with tempfile.TemporaryDirectory() as snap:
            (Path(snap) / "configs").mkdir()
            for r in ROUTERS:
                (Path(snap) / "configs" / f"{r}.{ext}").write_text(convert(r, (src / f"{r}.conf").read_text()))
            bf.init_snapshot(snap, name=ext, overwrite=True)
        print(f"== {label}")
        for f in bf.q.fileParseStatus().answer().frame().itertuples():
            print(f"  {f.File_Name}: {f.Status} as {f.File_Format}")
        for w in bf.q.parseWarning().answer().frame().itertuples():
            print(f"  warning {w.Filename}:{w.Line}: {w.Text!r}")
        names = sorted(i.Interface.interface for i in bf.q.interfaceProperties().answer().frame().itertuples()
                       if i.Interface.hostname == "r1")
        print(f"  r1 interfaces: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
