"""HTTP wake endpoint as an Azure Function (Python v2 model).

Your app calls POST /api/wake after it writes a request row. The function runs
as its managed identity, which needs Contributor (or higher) on the workspace.
Workspace and notebook IDs come from app settings, never from the caller.
"""

import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential

from fabric_dispatcher import FabricJobs, WakeTarget, wake

log = logging.getLogger(__name__)
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
_credential = DefaultAzureCredential()
_target = WakeTarget(os.environ["DISPATCHER_WORKSPACE_ID"], os.environ["DISPATCHER_NOTEBOOK_ID"])


def _token() -> str:
    return _credential.get_token("https://api.fabric.microsoft.com/.default").token


@app.route(route="wake", methods=["POST"])
def wake_dispatcher(req: func.HttpRequest) -> func.HttpResponse:
    try:
        reason = str((req.get_json() or {}).get("reason", ""))
    except ValueError:
        reason = ""
    result = wake(FabricJobs(_token), _target, reason)
    log.info("wake: %s %s", result.outcome, result.detail)
    return func.HttpResponse(
        json.dumps({"outcome": result.outcome}),
        status_code=200,  # the caller shows a note; it never fails a save
        mimetype="application/json",
    )
