"""Concatenate the docs into docs/llms-full.txt (one plain-text file AI assistants can read in one fetch).

Run before `mkdocs build` (the Pages workflow does it). scripts/sync_facts.py also runs it and,
with --check, fails CI when the committed file is out of date.
"""
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"


def nav_files(nav):
    for item in nav:
        for _, v in item.items():
            if isinstance(v, list):
                yield from nav_files(v)
            else:
                yield v


def build() -> str:
    cfg = yaml.safe_load((HERE / "mkdocs.yml").read_text(encoding="utf-8").replace("!!python/name:", "#"))
    parts = ["# Netdryrun: full documentation", "",
             "> Netdryrun is an open-source tool that tests network changes in a real virtual lab before they reach production. "
             "It boots the topology with containerlab, waits for convergence, checks BGP sessions, prefixes, routes and reachability, "
             "and returns a pass/fail verdict with evidence. It runs locally, in GitHub Actions, or as an MCP server for AI agents.", "",
             "Install: `pip install netdryrun` · Source: https://github.com/netdryrun/netdryrun · Docs: https://netdryrun.com/", ""]
    for rel in nav_files(cfg["nav"]):
        text = (DOCS / rel).read_text(encoding="utf-8")
        text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)           # front matter
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)                  # html comments
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)\n?", "", text)                 # images
        url = "https://netdryrun.com/" + rel.replace("index.md", "").replace(".md", "/")
        parts += [f"\n\n---\nSource: {url}\n", text.strip()]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    (DOCS / "llms-full.txt").write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote llms-full.txt ({(DOCS / 'llms-full.txt').stat().st_size // 1024} KB)")
