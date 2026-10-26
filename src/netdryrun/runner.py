"""Orchestrate one dry run: deploy, check, collect evidence, destroy."""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import __version__
from .checks import Result, hold_together, is_post_convergence, run_round_robin
from .config import Config, Scenario
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
        # Every node a check or a fault names must exist, before anything is deployed
        wanted = {c.node for c in config.checks} | {c.node for sc in config.scenarios for c in sc.checks}             | {f.node for sc in config.scenarios for f in sc.faults}
        unknown = sorted(wanted - set(lab.nodes))
        if unknown:
            raise LabError(f"unknown node(s) {', '.join(unknown)}; the topology has {', '.join(lab.nodes)}")
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
        report.results += run_round_robin(positives, drivers, on_result=on_result)
        if negatives:
            if not positives:
                # nothing has proven convergence yet; give the control plane time to come up
                settle = max(settle, 30.0)
            log(f"Convergence checks done; settling {settle:g}s before post-convergence checks...")
            time.sleep(settle)
            report.results += hold_together(negatives, drivers, hold=hold, on_result=on_result)
        # Keep the report in the order the user wrote the checks
        order = {id(c): i for i, c in enumerate(config.checks)}
        report.results.sort(key=lambda r: order[id(r.check)])

        for sc in config.scenarios:
            for check in sc.checks:
                if check.node not in drivers:
                    drivers[check.node] = for_node(lab, check.node, config.drivers.get(check.node))
            report.results += run_scenario(lab, sc, drivers, settle=settle, hold=hold, on_result=on_result, log=log)
            # Before the next scenario, prove the network recovered (not just slept): the main
            # positive checks must pass again.
            if positives and not all(r.passed for r in run_round_robin(positives, drivers)):
                raise LabError(f"the network did not recover after scenario '{sc.name}'; later scenarios skipped")
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


def run_scenario(lab: Lab, sc: Scenario, drivers: dict, *, settle: float, hold: float,
                 on_result=None, log=lambda _: None) -> list[Result]:
    """Inject the scenario's faults, run its checks, then restore the links and let the network re-converge."""
    downed: list[tuple[str, str]] = []
    results: list[Result] = []
    log(f"Scenario: {sc.name}")
    try:
        for f in sc.faults:
            lab._require_linux_links(f.node)
            ifaces = [f.interface] if f.kind == "link_down" else lab.data_interfaces(f.node)
            for iface in ifaces:
                downed.append((f.node, iface))   # recorded first: restore even if this call half-fails
                lab.set_link(f.node, iface, up=False)
        positives = [c for c in sc.checks if not is_post_convergence(c)]
        negatives = [c for c in sc.checks if is_post_convergence(c)]
        results += run_round_robin(positives, drivers, on_result=on_result)
        if negatives:
            time.sleep(settle)
            results += hold_together(negatives, drivers, hold=hold, on_result=on_result)
    finally:
        not_restored = []
        for node, iface in downed:
            try:
                lab.set_link(node, iface, up=True)
            except LabError as e:
                not_restored.append(f"{node} {iface}: {e}")
        if not_restored:
            # A link left down silently would corrupt every later result: stop the run instead
            raise LabError("could not restore links after scenario: " + "; ".join(not_restored))
        if downed:
            log(f"Restored {len(downed)} link(s); settling {settle:g}s")
            time.sleep(settle)
    return results
