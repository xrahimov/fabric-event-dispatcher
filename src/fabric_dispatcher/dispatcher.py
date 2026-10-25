"""One dispatcher pass, and the decision to chain another one."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .jobs import FabricJobs
from .store import RequestStore

log = logging.getLogger(__name__)

DONE = {"Completed"}
FAILED = {"Failed", "Cancelled", "Deduped"}


@dataclass
class Route:
    """Where an action goes: a pipeline (or any job) in a workspace."""

    workspace_id: str
    item_id: str
    job_type: str = "Pipeline"


@dataclass
class PassResult:
    started: list[int] = field(default_factory=list)
    finished: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    open_work: bool = False


def run_pass(
    store: RequestStore,
    jobs: FabricJobs,
    routes: dict[str, Route],
    on_finished: Callable[[RequestStore, int], None] | None = None,
) -> PassResult:
    result = PassResult()

    for req in store.running():
        if not req.job_instance_url:
            continue
        status = jobs.get_instance(req.job_instance_url).get("status")
        if status in DONE:
            store.set_status(req.id, "succeeded")
            result.finished.append(req.id)
            if on_finished:
                on_finished(store, req.id)  # e.g. queue a follow-up publish
        elif status in FAILED:
            store.set_status(req.id, "failed", message=f"job {status}")
            result.failed.append(req.id)

    for req in store.pending():
        if not store.claim(req.id):
            result.skipped.append(req.id)  # another pass has it
            continue
        route = routes.get(req.action)
        if route is None:
            store.set_status(req.id, "failed", message=f"unknown action {req.action}")
            result.failed.append(req.id)
            continue
        res = jobs.start(route.workspace_id, route.item_id, route.job_type)
        if res.started:
            store.set_status(req.id, "running", job_instance_url=res.instance_url)
            result.started.append(req.id)
        else:
            store.set_status(req.id, "failed", message=f"start HTTP {res.status_code}")
            result.failed.append(req.id)

    result.open_work = store.open_work_exists()
    return result


def should_chain(open_work: bool, chain_depth: int, max_depth: int) -> bool:
    return open_work and chain_depth + 1 < max_depth


def chain_next(
    jobs: FabricJobs,
    workspace_id: str,
    notebook_id: str,
    params: dict[str, object],
    chain_depth: int,
) -> bool:
    """Queue the next pass before this one ends.

    The wake's "already running?" check then never sees a gap. Every parameter
    is passed forward, because one left out reverts to its default.
    """
    nxt = {**params, "chain_depth": chain_depth + 1}
    res = jobs.start(workspace_id, notebook_id, "RunNotebook", nxt)
    if not res.started:
        log.warning("chain stopped: HTTP %s", res.status_code)
    return res.started
