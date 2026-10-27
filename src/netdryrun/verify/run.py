"""`netdryrun verify`: deploy the lab with the before configs, snapshot it, destroy it; the same with the
after configs (and the standing guards on the after lab); then match the diff against the intent.

`--before` and `--after` each name the config directory the topology binds: a directory, or a git ref
whose tree holds it (at the same path as in the working tree). A directory wins over a ref of the same
name. The lab is built in a temporary folder from the topology file (byte for byte), the side's config
directory, and every other file the topology binds. With a git ref, the topology file in that ref must be
identical to the given one: verify compares configs on one topology (exit 2 otherwise).
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from ..config import ConfigError, load_yaml
from ..drivers import DRIVERS, DriverError, detect
from ..lab import Lab, LabError
from .converge import Inconclusive, stable_snapshot
from .engine import VerifyError, baseline_problems, match
from .frr import FrrCollector
from .intent import IntentError, check_nodes, load_intent
from .report import ALLOW_WARNING, VerifyResult
from .snapshot import Snapshot, SnapshotError

HOST_KINDS = ("bridge", "ovs-bridge", "host", "ext-container", "k8s-kind")


class VerifyInputError(RuntimeError):
    """Bad arguments: an unreadable side, a different topology, a config directory that can't be found."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------------------------------------
# The topology's file references
# ---------------------------------------------------------------------------------------------------------

def bind_sources(topology: Path) -> list[str]:
    """Host paths the topology references (binds and startup-config), as written."""
    try:
        data = load_yaml(topology.read_text(encoding="utf-8"), str(topology)) or {}
    except (ConfigError, OSError, UnicodeDecodeError) as e:
        raise VerifyInputError(f"{topology}: cannot read the topology: {e}") from None
    t = data.get("topology") if isinstance(data, dict) else None
    if not isinstance(t, dict):
        raise VerifyInputError(f"{topology}: not a containerlab topology (no `topology:` mapping)")
    blocks = [t.get("defaults") or {}]
    for section in ("kinds", "groups", "nodes"):
        sec = t.get(section) or {}
        if isinstance(sec, dict):
            blocks += [v or {} for v in sec.values()]
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        for bind in b.get("binds") or []:
            if isinstance(bind, str) and ":" in bind:
                out.append(bind.split(":", 1)[0])
        sc = b.get("startup-config")
        if isinstance(sc, str) and "\n" not in sc:
            out.append(sc)
    return out


def config_dir(topology: Path, explicit: str | None) -> PurePosixPath:
    """The config directory, relative to the topology's folder: --config-dir, or the one folder every
    relative bind source is in ('.' when they sit next to the topology)."""
    if explicit is not None:
        rel = PurePosixPath(explicit.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise VerifyInputError(f"--config-dir must be a folder inside the topology's folder, got {explicit!r}")
        return rel
    rel_sources = [PurePosixPath(s) for s in bind_sources(topology) if not PurePosixPath(s).is_absolute()]
    if not rel_sources:
        raise VerifyInputError(f"{topology}: binds no config files by relative path; name the config folder with --config-dir")
    tops = {s.parts[0] if len(s.parts) > 1 else "." for s in rel_sources}
    if len(tops) != 1:
        raise VerifyInputError(f"{topology}: binds files from several folders ({', '.join(sorted(tops))}); name the one "
                               "--before/--after replace with --config-dir")
    return PurePosixPath(tops.pop())


def _inside(path: PurePosixPath, folder: PurePosixPath) -> bool:
    return str(folder) == "." or path.parts[:len(folder.parts)] == folder.parts


# ---------------------------------------------------------------------------------------------------------
# Sides
# ---------------------------------------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, binary: bool = False):
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=120, text=not binary)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise VerifyInputError(f"git {' '.join(args)}: {e}") from None
    if p.returncode != 0:
        err = p.stderr if not binary else p.stderr.decode("utf-8", "replace")
        raise VerifyInputError(f"git {' '.join(args)}: {' '.join(err.split())[:300] or f'exit {p.returncode}'}")
    return p.stdout


def _extract(tar_bytes: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
        for m in tf.getmembers():
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts or m.issym() or m.islnk() or m.isdev():
                if m.issym() or m.islnk():
                    continue   # a symlink in the repository is not followed
                raise VerifyInputError(f"git archive: refusing member {m.name!r}")
        tf.extractall(dest, members=[m for m in tf.getmembers() if not (m.issym() or m.islnk())])


def materialize(spec: str, label: str, topology: Path, cfg_rel: PurePosixPath, work: Path) -> tuple[Path, str, Path]:
    """Build one side's lab folder. Returns (its topology file, a description of the side, the folder the
    side's tree was read from: the directory itself, or the extracted git tree's root)."""
    topology = topology.resolve()
    topo_dir = topology.parent
    out = work / label
    out.mkdir(parents=True)
    side_dir = Path(spec)
    if side_dir.is_dir():
        root = side_dir.resolve()
        desc = f"directory {spec}"
        tree_root = root
        if str(cfg_rel) == "." and (root / topology.name).is_file() \
                and (root / topology.name).read_bytes() != topology.read_bytes():
            raise VerifyInputError(f"{label}: {root / topology.name} differs from {topology}; verify compares configs "
                                   "on one topology")
    else:
        repo = Path(str(_git(["rev-parse", "--show-toplevel"], topo_dir)).strip())
        try:
            commit = str(_git(["rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}"], repo)).strip()
        except VerifyInputError:
            raise VerifyInputError(f"--{label} {spec!r} is neither a directory nor a git ref in {repo}") from None
        tree_root = work / f"{label}-tree"
        tree_root.mkdir()
        _extract(_git(["archive", "--format=tar", commit], repo, binary=True), tree_root)
        try:
            rel = topology.relative_to(repo.resolve())
        except ValueError:
            raise VerifyInputError(f"{topology} is not inside the git repository {repo}") from None
        ref_topo = tree_root / rel
        if not ref_topo.is_file():
            raise VerifyInputError(f"{label} ({spec}): the topology {rel.as_posix()} doesn't exist in that ref; verify "
                                   "compares configs on one topology")
        if ref_topo.read_bytes() != topology.read_bytes():
            raise VerifyInputError(f"{label} ({spec}): the topology {rel.as_posix()} differs from {topology}; verify "
                                   "compares configs on one topology")
        root = ref_topo.parent / Path(*cfg_rel.parts) if str(cfg_rel) != "." else ref_topo.parent
        desc = f"git ref {spec} ({commit[:12]})"
        if not root.is_dir():
            raise VerifyInputError(f"{label} ({spec}): the config folder {cfg_rel} doesn't exist in that ref")
    target = out if str(cfg_rel) == "." else out / Path(*cfg_rel.parts)
    shutil.copytree(root, target, dirs_exist_ok=True, symlinks=False)
    shutil.copyfile(topology, out / topology.name)
    for src in bind_sources(topology):
        p = PurePosixPath(src)
        if p.is_absolute():
            if _inside(PurePosixPath(Path(src).as_posix()), PurePosixPath((topo_dir / Path(*cfg_rel.parts)).as_posix())):
                raise VerifyInputError(f"the topology binds {src} by absolute path inside the config folder, so both "
                                       "sides would use the same file; bind it by relative path")
            continue
        dest = out / Path(*p.parts)
        if _inside(p, cfg_rel):
            if not dest.exists():
                raise VerifyInputError(f"{label} ({desc}): {src} is missing (the topology binds it)")
            continue
        orig = topo_dir / Path(*p.parts)
        if not orig.exists():
            raise VerifyInputError(f"the topology binds {src}, which doesn't exist")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if orig.is_dir():
            shutil.copytree(orig, dest, dirs_exist_ok=True)
        else:
            shutil.copyfile(orig, dest)
    return out / topology.name, desc, tree_root


# ---------------------------------------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------------------------------------

def classify_nodes(lab: Lab, overrides: dict[str, str], unobserved: list[str]) -> dict[str, str]:
    """node -> driver ("frr"), or "" for a node verify doesn't snapshot. Every other node is an error:
    verify 0.4 is FRR only, and a node it can't classify could hide a change."""
    unknown = sorted(set(unobserved) - set(lab.nodes))
    if unknown:
        raise VerifyInputError(f"--unobserved names node(s) not in the topology: {', '.join(unknown)}")
    out = {}
    for name, node in lab.nodes.items():
        if name in unobserved or node.kind in HOST_KINDS:
            out[name] = ""
            continue
        drv = overrides.get(name)
        if drv is None:
            try:
                drv = detect(node)
            except DriverError:
                raise VerifyInputError(f"cannot tell what runs on node {name} (kind {node.kind!r}, image {node.image!r}); "
                                       f"set nodes.{name}.driver: frr in the guards file, or pass --unobserved {name} "
                                       "if it is a host without a routing stack") from None
        if drv not in DRIVERS:
            raise VerifyInputError(f"node {name}: unknown driver {drv!r}")
        if drv != "frr":
            raise VerifyInputError(f"node {name} runs {drv}; verify 0.4 snapshots FRR nodes only (other drivers follow)")
        out[name] = drv
    return out


def collect(lab: Lab, nodes: dict[str, str]) -> Snapshot:
    def exec_fn(node, argv):
        r = lab.exec(node, argv, timeout=60)
        return r.rc, r.stdout, r.stderr
    snaps = {n: FrrCollector(n, exec_fn).collect() for n, drv in sorted(nodes.items()) if drv == "frr"}
    reasons = {n: ("named --unobserved or a host/bridge kind: no routing driver") for n, d in nodes.items() if not d}
    return Snapshot(snaps, reasons)


@contextmanager
def deployed(topology: Path, setup: dict[str, list[str]], keep: bool, log: Callable[[str], None]):
    from ..runner import _ACTIVE, _signals_deferred

    lab = Lab(topology)
    lab.check_tools()
    lab.acquire_lock()
    started = False
    try:
        existing = lab.existing_containers()
        if existing:
            raise LabError(f"a lab named '{lab.name}' is already running ({len(existing)} container(s)); verify won't "
                           f"redeploy or destroy it. Remove it with: containerlab destroy -t <topology> --cleanup")
        started = True
        if not keep:
            _ACTIVE.add(lab)
        log(f"Deploying lab {lab.name} ({len(lab.nodes)} nodes)...")
        lab.deploy()
        missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
        if missing:
            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
        for node, cmds in setup.items():
            lab.run_setup(node, cmds, log=log)
        yield lab
    finally:
        with _signals_deferred():
            if started and not keep:
                log("Destroying lab...")
                try:
                    lab.destroy()
                except Exception as e:   # cleanup trouble must never hide the result
                    log(f"warning: lab cleanup failed: {e}")
            elif started:
                log(f"Lab {lab.name} left running (--keep); destroy with: containerlab destroy -t {topology} --cleanup")
            _ACTIVE.discard(lab)
            lab.release_lock()


def real_side(*, nodes: dict[str, str], setup: dict, settle: float, timeout: float, keep_after: bool,
              log: Callable[[str], None]):
    """The default way to get one side's snapshot: deploy, wait for a stable snapshot, run `on_up` (the
    guards, on the after lab), destroy."""
    def side(label: str, topology: Path, on_up=None):
        t0 = time.monotonic()
        with deployed(topology, setup, keep_after and label == "after", log) as lab:
            log(f"[{label}] waiting for a stable snapshot (settle {settle:g}s, timeout {timeout:g}s)...")
            snap = stable_snapshot(lambda: collect(lab, nodes), settle=settle, timeout=timeout, log=log)
            extra = on_up(lab, topology) if on_up is not None and isinstance(snap, Snapshot) else None
        return snap, round(time.monotonic() - t0, 1), extra
    return side


# ---------------------------------------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------------------------------------

def run_guards(cfg, topology: Path, settle: float, hold: float, log) -> dict:
    from ..runner import run

    rep = run(replace(cfg, lab=topology), deploy=False, keep=True, settle=settle, hold=hold, log=log)
    return {"status": rep.status, "passed": rep.passed, "failed": rep.failed, "error": rep.error or None,
            "failures": [{"check": r.check.name, "node": r.check.params.get("node"), "reason": str(r.detail)}
                         for r in rep.results if not r.passed]}


def load_guards(path: str, before_spec: str, before_tree: Path | None, repo_rel: Path | None):
    """The standing guards. With a git ref as --before, they are read from that ref (the base branch),
    never from the working tree; with a directory, from the path given."""
    from ..runner import load_config

    if before_tree is not None and repo_rel is not None:
        p = before_tree / repo_rel
        if p.is_dir():
            p = p / "netdryrun.yml"
        if not p.is_file():
            raise VerifyInputError(f"--guards {path}: not in the before ref ({before_spec}); the standing guards are "
                                   "read from the base, never from the change")
        return load_config(p), f"{repo_rel.as_posix()} at {before_spec}"
    return load_config(path), str(path)


# ---------------------------------------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------------------------------------

def verify(topology: str, before: str, after: str, intent_path: str, *, guards: str | None = None,
           config_dir_name: str | None = None, unobserved: list[str] = (), settle: float = 15.0,
           timeout: float = 300.0, hold: float = 10.0, allow_unhealthy_baseline: bool = False, keep: bool = False,
           log: Callable[[str], None] = lambda _: None, side_fn=None) -> VerifyResult:
    res = VerifyResult(status="error", topology=str(topology), before_spec=before, after_spec=after,
                       run_id=uuid.uuid4().hex[:12], started=_now())
    work = Path(tempfile.mkdtemp(prefix="netdryrun-verify-"))
    try:
        res.intent = load_intent(intent_path)
        if res.intent.allow:
            res.warnings.append(ALLOW_WARNING)
        topo = Path(topology)
        if not topo.is_file():
            raise VerifyInputError(f"{topology}: topology not found")
        lab = Lab(topo)
        res.containers = {n: nd.container for n, nd in lab.nodes.items()}
        cfg_rel = config_dir(topo, config_dir_name)
        before_topo, bdesc, btree = materialize(before, "before", topo, cfg_rel, work)
        after_topo, adesc, _ = materialize(after, "after", topo, cfg_rel, work)
        res.before_spec, res.after_spec = f"{before}: {bdesc}", f"{after}: {adesc}"
        gcfg, gsource = None, None
        if guards:
            is_ref = not Path(before).is_dir()
            repo_rel = None
            if is_ref:
                repo = Path(str(_git(["rev-parse", "--show-toplevel"], topo.resolve().parent)).strip()).resolve()
                try:
                    repo_rel = Path(guards).resolve().relative_to(repo)
                except ValueError:
                    raise VerifyInputError(f"--guards {guards} is outside the git repository {repo}") from None
            gcfg, gsource = load_guards(guards, before, btree if is_ref else None, repo_rel)
        nodes = classify_nodes(lab, gcfg.drivers if gcfg else {}, list(unobserved))
        check_nodes(res.intent, nodes)
        side = side_fn or real_side(nodes=nodes, setup=gcfg.setup if gcfg else {}, settle=settle, timeout=timeout,
                                    keep_after=keep, log=log)

        snap_b, tb, _ = side("before", before_topo)
        res.timings["before_s"] = tb
        if isinstance(snap_b, Inconclusive):
            res.status, res.inconclusive, res.inconclusive_side = "inconclusive", snap_b, "before"
            return res
        res.before = snap_b
        res.baseline_problems = baseline_problems(snap_b)
        if res.baseline_problems and not allow_unhealthy_baseline:
            res.status = "unhealthy_baseline"
            return res
        res.baseline_overridden = bool(res.baseline_problems)

        on_up = (lambda _lab, t: {**run_guards(gcfg, t, settle, hold, log), "source": gsource}) if gcfg else None
        snap_a, ta, gres = side("after", after_topo, on_up)
        res.timings["after_s"] = ta
        if isinstance(snap_a, Inconclusive):
            res.status, res.inconclusive, res.inconclusive_side = "inconclusive", snap_a, "after"
            return res
        res.after = snap_a
        res.guards = gres

        m = match(snap_b, snap_a, res.intent)
        res.match = m
        res.status = m.status
        if m.undeclared:
            res.failed_because.append("undeclared")
        if m.not_happened:
            res.failed_because.append("not_happened")
        if gres is not None:
            if gres["status"] == "failed":
                res.failed_because.append("guards")
                res.status = "failed"
            elif gres["status"] != "passed" and res.status != "failed":
                res.status = "inconclusive" if gres["status"] == "inconclusive" else "error"
                res.error = f"the standing guards ended with {gres['status']}: {gres.get('error') or 'no verdict'}"
        return res
    except SnapshotError as e:
        res.status, res.error = "error", f"unreadable snapshot: {e}"
        return res
    except IntentError as e:
        res.status, res.error = "error", f"intent error: {e}"
        return res
    except ConfigError as e:
        res.status, res.error = "error", f"guards config error: {e}"
        return res
    except (VerifyInputError, VerifyError, LabError, DriverError) as e:
        res.status, res.error = "error", str(e)
        return res
    except OSError as e:
        res.status, res.error = "error", f"cannot prepare the labs: {e}"
        return res
    finally:
        res.finished = _now()
        shutil.rmtree(work, ignore_errors=True)
