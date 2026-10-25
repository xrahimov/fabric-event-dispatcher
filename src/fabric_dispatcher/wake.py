"""Start the dispatcher notebook on demand, unless it is already running."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .jobs import FabricJobs

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WakeTarget:
    """Fixed at deploy time, so a caller can't point the wake at another item."""

    workspace_id: str
    notebook_id: str


@dataclass
class WakeResult:
    outcome: str  # "started" | "already_running" | "failed"
    detail: str = ""


def wake(jobs: FabricJobs, target: WakeTarget, reason: str = "") -> WakeResult:
    """Never raises: a failed wake must not fail the user's save."""
    log.info("wake requested: %s", reason[:200])
    try:
        if jobs.is_active(target.workspace_id, target.notebook_id):
            return WakeResult("already_running")
        res = jobs.start(target.workspace_id, target.notebook_id, "RunNotebook")
    except Exception as exc:  # noqa: BLE001
        log.warning("wake failed: %s", exc)
        return WakeResult("failed", str(exc))
    if res.started:
        return WakeResult("started", res.instance_url or "")
    return WakeResult("failed", f"HTTP {res.status_code}")
