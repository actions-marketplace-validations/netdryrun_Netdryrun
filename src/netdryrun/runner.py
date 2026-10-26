"""Orchestrate one dry run: deploy, check, collect evidence, destroy."""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import __version__
from .checks import Result, converge_then_hold, is_post_convergence, run_check
from .config import Config
from .drivers import DriverError, for_node
from .lab import Lab, LabError


@dataclass
class RunReport:
    config: Config
    lab_name: str = ""
    started: str = ""
    finished: str = ""
    results: list[Result] = field(default_factory=list)
    error: str = ""
    environment: dict = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def failed(self) -> int:
        return sum(not r.passed for r in self.results)

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        return "passed" if self.results and self.failed == 0 else "failed"

    @property
    def exit_code(self) -> int:
        return {"passed": 0, "failed": 1}.get(self.status, 2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(config: Config, *, deploy: bool = True, keep: bool = False, keep_on_failure: bool = False,
        settle: float = 10.0, hold: float = 10.0,
        on_result: Callable[[Result], None] | None = None, log: Callable[[str], None] = lambda _: None) -> RunReport:
    report = RunReport(config=config, started=_now())
    lab = None
    try:
        lab = Lab(config.lab)
        report.lab_name = lab.name
        lab.check_tools()
        report.environment = {
            "netdryrun": __version__,
            "containerlab": lab.version(),
            "python": platform.python_version(),
            "host": platform.platform(),
            "nodes": {n.name: {"kind": n.kind, "image": n.image} for n in lab.nodes.values()},
        }
        if deploy:
            log(f"Deploying lab {lab.name} ({len(lab.nodes)} nodes)...")
            lab.deploy()
        missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
        if missing:
            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")

        drivers = {}
        for check in config.checks:
            if check.node not in drivers:
                drivers[check.node] = for_node(lab, check.node, config.drivers.get(check.node))

        positives = [c for c in config.checks if not is_post_convergence(c)]
        negatives = [c for c in config.checks if is_post_convergence(c)]
        for check in positives:
            res = run_check(check, drivers[check.node])
            report.results.append(res)
            if on_result:
                on_result(res)
        if negatives:
            if not positives:
                # nothing has proven convergence yet; give the control plane time to come up
                settle = max(settle, 30.0)
            log(f"Convergence checks done; settling {settle:g}s before post-convergence checks...")
            time.sleep(settle)
            for check in negatives:
                res = converge_then_hold(check, drivers[check.node], hold=hold)
                report.results.append(res)
                if on_result:
                    on_result(res)
        # Keep the report in the order the user wrote the checks
        order = {id(c): i for i, c in enumerate(config.checks)}
        report.results.sort(key=lambda r: order[id(r.check)])
    except (LabError, DriverError) as e:
        report.error = str(e)
    finally:
        keep_now = keep or (keep_on_failure and report.status != "passed")
        if lab is not None and deploy and not keep_now:
            log("Destroying lab...")
            try:
                d = lab.destroy()
                if d.rc != 0:
                    log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
            except Exception as e:  # cleanup trouble must never hide the test results
                log(f"warning: lab cleanup failed: {e}")
        elif lab is not None and deploy:
            log(f"Lab {lab.name} left running for debugging; destroy with: containerlab destroy -t {lab.topology} --cleanup")
        report.finished = _now()
    return report
