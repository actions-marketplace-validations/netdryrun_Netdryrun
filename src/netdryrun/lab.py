"""Thin wrapper around the containerlab CLI and docker exec."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


class LabError(RuntimeError):
    pass


@dataclass
class Node:
    name: str        # short name from the topology, e.g. r1
    container: str   # docker container name, e.g. clab-mylab-r1
    kind: str
    image: str


@dataclass
class ExecResult:
    cmd: list[str]
    rc: int
    stdout: str
    stderr: str


def _run(cmd: list[str], timeout: float = 600, env: dict | None = None) -> ExecResult:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return ExecResult(cmd, 124, "", f"timed out after {timeout}s")
    return ExecResult(cmd, p.returncode, p.stdout, p.stderr)


class Lab:
    def __init__(self, topology: Path, containerlab: str = "containerlab"):
        self.topology = topology
        self.clab = containerlab
        topo = yaml.safe_load(topology.read_text(encoding="utf-8")) or {}
        self.name = topo.get("name")
        if not self.name:
            raise LabError(f"{topology}: topology has no 'name'")
        t = topo.get("topology") or {}
        defaults = t.get("defaults") or {}
        kinds = t.get("kinds") or {}
        prefix = topo.get("prefix", "clab")
        self.nodes: dict[str, Node] = {}
        for nname, ndef in (t.get("nodes") or {}).items():
            ndef = ndef or {}
            kind = ndef.get("kind", defaults.get("kind", ""))
            image = ndef.get("image") or (kinds.get(kind) or {}).get("image") or defaults.get("image", "")
            if prefix == "":
                container = nname
            elif prefix == "__lab-name":
                container = f"{self.name}-{nname}"
            else:
                container = f"{prefix}-{self.name}-{nname}"
            self.nodes[nname] = Node(nname, container, kind, image)

    def check_tools(self) -> None:
        for tool in (self.clab, "docker"):
            if not shutil.which(tool):
                raise LabError(f"'{tool}' not found on PATH")

    def _env(self) -> dict:
        """Keep containerlab's lab directory on a Linux filesystem.

        On WSL, a topology under /mnt/c lives on a Windows drive without Linux permissions,
        and SR Linux fails to save its config there.
        """
        env = dict(os.environ)
        if "CLAB_LABDIR_BASE" not in env and str(self.topology).startswith("/mnt/"):
            base = Path.home() / ".cache" / "netdryrun" / "labs"
            base.mkdir(parents=True, exist_ok=True)
            env["CLAB_LABDIR_BASE"] = str(base)
        return env

    def deploy(self) -> ExecResult:
        r = _run([self.clab, "deploy", "-t", str(self.topology), "--reconfigure"], env=self._env())
        if r.rc != 0:
            raise LabError(f"containerlab deploy failed:\n{(r.stderr or r.stdout)[-3000:]}")
        return r

    def destroy(self) -> ExecResult:
        return _run([self.clab, "destroy", "-t", str(self.topology), "--cleanup"], env=self._env())

    def version(self) -> str:
        r = _run([self.clab, "version"], timeout=30)
        for line in r.stdout.splitlines():
            if line.strip().startswith("version:"):
                return line.split(":", 1)[1].strip()
        return "unknown"

    def running_containers(self) -> set[str]:
        r = _run([self.clab, "inspect", "-t", str(self.topology), "--format", "json"], timeout=60, env=self._env())
        if r.rc != 0:
            return set()
        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            return set()
        rows = data.get(self.name, []) if isinstance(data, dict) else []
        return {row["name"] for row in rows if row.get("state") == "running"}

    def exec(self, node: str, cmd: list[str], timeout: float = 60) -> ExecResult:
        return _run(["docker", "exec", self.nodes[node].container, *cmd], timeout=timeout)
