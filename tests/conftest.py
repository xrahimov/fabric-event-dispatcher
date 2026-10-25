import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from fabric_dispatcher.jobs import StartResult

SQLITE_SCHEMA = """
CREATE TABLE dispatch_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    job_instance_url TEXT,
    message TEXT,
    requested_by TEXT,
    requested_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP
);
CREATE TABLE dispatch_setting (
    name TEXT PRIMARY KEY,
    desired_value TEXT NOT NULL,
    actual_value TEXT,
    updated_at TIMESTAMP
);
"""


sqlite3.register_adapter(datetime, lambda d: d.isoformat(" "))
sqlite3.register_converter("TIMESTAMP", lambda b: datetime.fromisoformat(b.decode()))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    c.executescript(SQLITE_SCHEMA)
    yield c
    c.close()


def add_request(conn, action="refresh", status="pending", age=timedelta(0), url=None):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO dispatch_request (action, status, requested_at, job_instance_url) VALUES (?, ?, ?, ?)",
        (action, status, datetime.now(timezone.utc).replace(tzinfo=None) - age, url),
    )
    conn.commit()
    return cur.lastrowid


class FakeJobs:
    """Stands in for FabricJobs in dispatcher and wake tests."""

    def __init__(self, active=False, start_code=202, instance_status=None):
        self.active = active
        self.start_code = start_code
        self.instance_status = instance_status or {}
        self.starts = []

    def is_active(self, workspace_id, item_id):
        if isinstance(self.active, Exception):
            raise self.active
        return self.active

    def start(self, workspace_id, item_id, job_type, parameters=None):
        self.starts.append((item_id, job_type, parameters))
        url = f"https://jobs/{item_id}/{len(self.starts)}"
        return StartResult(self.start_code == 202, self.start_code, url)

    def get_instance(self, url):
        return {"status": self.instance_status.get(url, "InProgress")}


@pytest.fixture
def add():
    return add_request
