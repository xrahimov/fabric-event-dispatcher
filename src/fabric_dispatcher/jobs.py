"""Thin client for the Fabric job scheduler REST API.

Only the three calls the pattern needs: list an item's job instances, start a
job, and read one job instance.
https://learn.microsoft.com/rest/api/fabric/core/job-scheduler
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import requests

FABRIC_API = "https://api.fabric.microsoft.com/v1"
ACTIVE_STATES = {"NotStarted", "InProgress"}


@dataclass
class StartResult:
    started: bool
    status_code: int
    instance_url: str | None = None


class FabricJobs:
    def __init__(
        self,
        token_provider: Callable[[], str],
        session: requests.Session | None = None,
        base_url: str = FABRIC_API,
        timeout: float = 30,
    ):
        self._token = token_provider
        self._http = session or requests.Session()
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    def _item_url(self, workspace_id: str, item_id: str) -> str:
        return f"{self._base}/workspaces/{workspace_id}/items/{item_id}/jobs/instances"

    def list_instances(self, workspace_id: str, item_id: str) -> list[dict]:
        r = self._http.get(
            self._item_url(workspace_id, item_id),
            headers=self._headers(),
            timeout=self._timeout,
        )
        r.raise_for_status()
        return r.json().get("value", [])

    def is_active(self, workspace_id: str, item_id: str) -> bool:
        return any(i.get("status") in ACTIVE_STATES for i in self.list_instances(workspace_id, item_id))

    def start(
        self,
        workspace_id: str,
        item_id: str,
        job_type: str,
        parameters: dict[str, object] | None = None,
    ) -> StartResult:
        """Start a job. Anything other than HTTP 202 counts as not started."""
        body = None
        if parameters:
            body = {"executionData": {"parameters": to_job_parameters(parameters)}}
        r = self._http.post(
            self._item_url(workspace_id, item_id),
            params={"jobType": job_type},
            headers=self._headers(),
            json=body,
            timeout=self._timeout,
        )
        return StartResult(
            started=r.status_code == 202,
            status_code=r.status_code,
            instance_url=r.headers.get("Location"),
        )

    def get_instance(self, instance_url: str) -> dict:
        r = self._http.get(instance_url, headers=self._headers(), timeout=self._timeout)
        r.raise_for_status()
        return r.json()


def to_job_parameters(values: dict[str, object]) -> dict[str, dict]:
    """Convert plain values to the {name: {value, type}} shape RunNotebook expects."""
    out = {}
    for name, value in values.items():
        if isinstance(value, bool):
            kind = "bool"
        elif isinstance(value, int):
            kind = "int"
        elif isinstance(value, float):
            kind = "float"
        else:
            kind, value = "string", str(value)
        out[name] = {"value": value, "type": kind}
    return out
