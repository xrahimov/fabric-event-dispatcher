"""Request queue on any DB-API connection that uses the qmark (?) paramstyle.

pyodbc (Fabric SQL database, Azure SQL) and sqlite3 (tests) both do. The SQL
avoids engine-specific functions; timestamps come from Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

OPEN_STATES = ("pending", "claimed", "running")


@dataclass
class Request:
    id: int
    action: str
    target: str
    status: str
    job_instance_url: str | None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RequestStore:
    def __init__(self, conn, open_window: timedelta = timedelta(hours=24)):
        self.conn = conn
        self.open_window = open_window

    def _rows(self, sql: str, params: tuple = ()) -> list[Request]:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return [Request(*row) for row in cur.fetchall()]

    def _cutoff(self) -> datetime:
        return utcnow() - self.open_window

    def pending(self) -> list[Request]:
        return self._rows(
            "SELECT id, action, target, status, job_instance_url FROM dispatch_request "
            "WHERE status = 'pending' AND requested_at >= ? ORDER BY id",
            (self._cutoff(),),
        )

    def running(self) -> list[Request]:
        return self._rows(
            "SELECT id, action, target, status, job_instance_url FROM dispatch_request "
            "WHERE status = 'running' ORDER BY id"
        )

    def claim(self, request_id: int) -> bool:
        """Conditional update: only one overlapping pass can win a request."""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE dispatch_request SET status = 'claimed', updated_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (utcnow(), request_id),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def set_status(
        self,
        request_id: int,
        status: str,
        job_instance_url: str | None = None,
        message: str | None = None,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE dispatch_request SET status = ?, "
            "job_instance_url = COALESCE(?, job_instance_url), "
            "message = COALESCE(?, message), updated_at = ? WHERE id = ?",
            (status, job_instance_url, message, utcnow(), request_id),
        )
        self.conn.commit()

    def open_work_exists(self) -> bool:
        """Open requests in the window, or a setting not yet applied."""
        cur = self.conn.cursor()
        marks = ", ".join("?" for _ in OPEN_STATES)
        cur.execute(
            f"SELECT COUNT(*) FROM dispatch_request WHERE status IN ({marks}) AND requested_at >= ?",
            (*OPEN_STATES, self._cutoff()),
        )
        if cur.fetchone()[0]:
            return True
        cur.execute(
            "SELECT COUNT(*) FROM dispatch_setting "
            "WHERE actual_value IS NULL OR desired_value <> actual_value"
        )
        return cur.fetchone()[0] > 0
