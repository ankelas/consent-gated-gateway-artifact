from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from telemetry import Telemetry


class StateStore:
    """Minimal storage model for exercising telemetry and event idempotency."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS inbound_events_v2 (
                    caller_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (caller_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS telemetry_spans_v1 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    span_id TEXT NOT NULL UNIQUE,
                    task_id TEXT,
                    operation TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    duration_ms REAL NOT NULL,
                    status TEXT NOT NULL,
                    failure_category TEXT,
                    attributes_json TEXT NOT NULL DEFAULT '{}'
                );
            """)
        self.telemetry = Telemetry(self.record_telemetry)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_telemetry(self, record: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("""INSERT INTO telemetry_spans_v1(
                trace_id, span_id, task_id, operation, duration_ms,
                status, failure_category, attributes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (record["trace_id"], record["span_id"], record.get("task_id"), record["operation"],
             record["duration_ms"], record["status"], record.get("failure_category"),
             json.dumps(record.get("attributes") or {}, separators=(",", ":"))))

    def telemetry_summary(self, operation: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT operation, status, COUNT(*) AS count, AVG(duration_ms) AS mean_ms FROM telemetry_spans_v1"
        params: tuple[Any, ...] = ()
        if operation:
            query += " WHERE operation = ?"
            params = (operation,)
        query += " GROUP BY operation, status ORDER BY operation, status"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def claim_event(self, caller_id: str, message_id: str) -> tuple[str, dict[str, Any] | None]:
        with self._connect() as conn:
            cursor = conn.execute("""INSERT OR IGNORE INTO inbound_events_v2(
                caller_id, message_id, response_json, status) VALUES (?, ?, '{}', 'processing')""",
                (caller_id, message_id))
            if cursor.rowcount == 1:
                return "claimed", None
            row = conn.execute("""SELECT response_json, status FROM inbound_events_v2
                WHERE caller_id = ? AND message_id = ?""", (caller_id, message_id)).fetchone()
            if row and row["status"] == "completed":
                return "completed", json.loads(row["response_json"])
            return "processing", None

    def save_event_response(self, caller_id: str, message_id: str, response: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("""INSERT INTO inbound_events_v2(caller_id, message_id, response_json, status)
                VALUES (?, ?, ?, 'completed') ON CONFLICT(caller_id, message_id) DO UPDATE SET
                response_json=excluded.response_json, status='completed', updated_at=CURRENT_TIMESTAMP""",
                (caller_id, message_id, json.dumps(response, ensure_ascii=False)))

    def release_event(self, caller_id: str, message_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM inbound_events_v2 WHERE caller_id=? AND message_id=? AND status='processing'",
                         (caller_id, message_id))
