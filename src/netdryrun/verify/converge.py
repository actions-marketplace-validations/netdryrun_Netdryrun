"""The convergence-stable snapshot: two full snapshots `settle` seconds apart must be identical.

Identical means every item and the derived facts (prefix counts per session): sessions established or
stably not, prefix counts stable, every route and path unchanged. A node whose RIB is still empty (zebra
not up, interfaces not configured yet) is not ready, whatever it repeats.

A command that fails (vtysh can't reach a daemon that is still starting) is retried until the timeout;
then the snapshot is unreadable, an error (exit 2), never "nothing changed". Output that doesn't match the
schema stops at once. If the snapshots never repeat within `timeout`, the result is Inconclusive, naming
what kept moving.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .frr import CommandFailed
from .snapshot import Snapshot, SnapshotError

POLL = 3.0


@dataclass
class Inconclusive:
    reason: str
    moving: list[str]


class SnapshotUnreadable(SnapshotError):
    pass


def _moving(prev: Snapshot, cur: Snapshot, limit: int = 20) -> list[str]:
    a, b = prev.stability_view(), cur.stability_view()
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            what = "appeared" if k not in a else "disappeared" if k not in b else "changed"
            out.append(f"{k.where()} {what}")
            if len(out) >= limit:
                out.append("...")
                break
    return out


def _not_ready(snap: Snapshot) -> list[str]:
    return [f"{n}: no routes in its RIB yet" for n, ns in sorted(snap.nodes.items())
            if not any(k.kind == "rib" for k in ns.items)]


def stable_snapshot(collect: Callable[[], Snapshot], *, settle: float, timeout: float,
                    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                    log: Callable[[str], None] = lambda _: None) -> Snapshot | Inconclusive:
    t0 = clock()
    prev: Snapshot | None = None
    moving: list[str] = []
    last_failure = ""
    while True:
        try:
            cur = collect()
        except CommandFailed as e:
            prev, last_failure = None, str(e)
            if clock() - t0 >= timeout:
                raise SnapshotUnreadable(f"could not read the snapshot within {timeout:g}s: {e}") from None
            sleep(POLL)
            continue
        last_failure = ""
        waiting = _not_ready(cur)
        if waiting:
            prev, moving = None, waiting
        elif prev is not None and prev.stability_view() == cur.stability_view():
            log(f"  snapshot stable ({len(cur.items())} items, {clock() - t0:.0f}s)")
            return cur
        elif prev is not None:
            moving = _moving(prev, cur)
            log(f"  still converging: {len(moving)} difference(s) since the last snapshot")
        if clock() - t0 + settle > timeout:
            what = "never became ready" if waiting else "kept moving"
            return Inconclusive(f"the lab's state {what} within {timeout:g}s (two snapshots {settle:g}s apart "
                                "never matched). Retry at most once, then escalate: this says nothing about the change",
                                moving or ([last_failure] if last_failure else []))
        if not waiting:
            prev = cur
        sleep(settle if not waiting else POLL)
