# Fabric notebook source, Python (not Spark) kernel.
# Import as a notebook, or paste each "# CELL" block into its own cell.

# CELL: parameters (mark this cell as the parameter cell)
chain_depth = 0
max_chain_depth = 240  # ~5 hours at ~75 s per pass
sleep_seconds = 45
sql_server = ""  # Fabric SQL database: Settings > Connection strings
sql_database = ""

# CELL: install
# %pip install "git+https://github.com/xrahimov/fabric-event-dispatcher@v0.1.0"

# CELL: run one pass, then chain if work is still open
import struct
import time

import notebookutils  # available in Fabric notebooks
import pyodbc

from fabric_dispatcher import FabricJobs, RequestStore, Route, chain_next, run_pass, should_chain

ctx = notebookutils.runtime.context
workspace_id = ctx["currentWorkspaceId"]
notebook_id = ctx["currentNotebookId"]


def fabric_token() -> str:
    return notebookutils.credentials.getToken("https://api.fabric.microsoft.com")


def sql_connection():
    token = notebookutils.credentials.getToken("https://database.windows.net/").encode("utf-16-le")
    attrs = {1256: struct.pack(f"<I{len(token)}s", len(token), token)}  # SQL_COPT_SS_ACCESS_TOKEN
    return pyodbc.connect(
        f"Driver={{ODBC Driver 18 for SQL Server}};Server={sql_server};Database={sql_database};"
        "Encrypt=yes;TrustServerCertificate=no",
        attrs_before=attrs,
    )


# action name in dispatch_request -> job to start
ROUTES = {
    "refresh_workbook": Route(workspace_id, "<pipeline-item-id>"),
    "publish": Route(workspace_id, "<pipeline-item-id>"),
}


def queue_publish(store, request_id):
    """Example follow-up: a finished refresh queues a publish."""
    cur = store.conn.cursor()
    cur.execute(
        "INSERT INTO dbo.dispatch_request (action, target, requested_by) "
        "SELECT 'publish', target, 'dispatcher' FROM dbo.dispatch_request "
        "WHERE id = ? AND action = 'refresh_workbook'",
        (request_id,),
    )
    store.conn.commit()


jobs = FabricJobs(fabric_token)
with sql_connection() as conn:
    store = RequestStore(conn)
    result = run_pass(store, jobs, ROUTES, on_finished=queue_publish)

print(f"pass {chain_depth}: {result}")

if should_chain(result.open_work, chain_depth, max_chain_depth):
    time.sleep(sleep_seconds)
    chain_next(
        jobs,
        workspace_id,
        notebook_id,
        {
            "max_chain_depth": max_chain_depth,
            "sleep_seconds": sleep_seconds,
            "sql_server": sql_server,
            "sql_database": sql_database,
        },
        chain_depth,
    )
