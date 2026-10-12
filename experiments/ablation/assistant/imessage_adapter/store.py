from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any


class StateStore:
    """Persistent state, always partitioned by trusted caller_id."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS inbound_events_v2 (
                  caller_id TEXT NOT NULL,
                  message_id TEXT NOT NULL,
                  response_json TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (caller_id, message_id)
                );
                CREATE TABLE IF NOT EXISTS photon_callers_v1 (
                  caller_id TEXT PRIMARY KEY,
                  photon_sender_id TEXT NOT NULL UNIQUE,
                  display_name TEXT NOT NULL DEFAULT '',
                  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_photon_callers_sender
                  ON photon_callers_v1(photon_sender_id);
                CREATE TABLE IF NOT EXISTS caller_conversations_v2 (
                  caller_id TEXT NOT NULL,
                  chat_guid TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  local_task_id TEXT,
                  upstream_task_id TEXT,
                  upstream_session_id TEXT,
                  upstream_state TEXT,
                  summary TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (caller_id, chat_guid)
                );
                CREATE TABLE IF NOT EXISTS pending_agent_choices_v1 (
                  caller_id TEXT NOT NULL,
                  chat_guid TEXT NOT NULL,
                  query_text TEXT NOT NULL,
                  candidates_json TEXT NOT NULL,
                  discovery_reply TEXT NOT NULL DEFAULT '',
                  expires_at INTEGER NOT NULL,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (caller_id, chat_guid)
                );
                CREATE INDEX IF NOT EXISTS idx_pending_agent_choices_expiry
                  ON pending_agent_choices_v1(expires_at);
                CREATE TABLE IF NOT EXISTS task_contexts_v2 (
                  caller_id TEXT NOT NULL,
                  task_id TEXT NOT NULL,
                  context_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (caller_id, task_id)
                );
                CREATE TABLE IF NOT EXISTS conversation_messages_v2 (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  caller_id TEXT NOT NULL,
                  chat_guid TEXT NOT NULL,
                  direction TEXT NOT NULL CHECK(direction IN ('user', 'assistant')),
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_messages_by_conversation
                  ON conversation_messages_v2(caller_id, chat_guid, id DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_photon_caller(self, caller_id: str, photon_sender_id: str, display_name: str = "") -> None:
        """Persist the Photon identity after the bridge has verified its webhook."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO photon_callers_v1(caller_id, photon_sender_id, display_name)
                VALUES (?, ?, ?)
                ON CONFLICT(caller_id) DO UPDATE SET
                  photon_sender_id=excluded.photon_sender_id,
                  display_name=CASE
                    WHEN excluded.display_name <> '' THEN excluded.display_name
                    ELSE photon_callers_v1.display_name
                  END,
                  last_seen_at=CURRENT_TIMESTAMP
                """,
                (caller_id, photon_sender_id, display_name.strip()),
            )

    def photon_caller(self, caller_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM photon_callers_v1 WHERE caller_id = ?", (caller_id,)
            ).fetchone()
        return dict(row) if row else None

    def event_response(self, caller_id: str, message_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response_json FROM inbound_events_v2 WHERE caller_id = ? AND message_id = ?",
                (caller_id, message_id),
            ).fetchone()
        return json.loads(row["response_json"]) if row else None

    def save_event_response(self, caller_id: str, message_id: str, response: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO inbound_events_v2(caller_id, message_id, response_json) VALUES (?, ?, ?)",
                (caller_id, message_id, json.dumps(response, ensure_ascii=False)),
            )

    def conversation(self, caller_id: str, chat_guid: str) -> dict[str, Any] | None:
        # STAGING ABLATION ONLY: ABLATION_SHARED_SESSION=1 collapses the
        # (caller_id, chat_guid) partition into one shared namespace.
        if os.getenv("ABLATION_SHARED_SESSION") == "1":
            caller_id, chat_guid = "shared", "shared"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM caller_conversations_v2 WHERE caller_id = ? AND chat_guid = ?",
                (caller_id, chat_guid),
            ).fetchone()
        return dict(row) if row else None

    def save_conversation(self, caller_id: str, chat_guid: str, **values: Any) -> None:
        if os.getenv("ABLATION_SHARED_SESSION") == "1":
            caller_id, chat_guid = "shared", "shared"
        current = self.conversation(caller_id, chat_guid) or {}
        merged = {**current, **values}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO caller_conversations_v2(
                  caller_id, chat_guid, session_id, local_task_id, upstream_task_id,
                  upstream_session_id, upstream_state, summary, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(caller_id, chat_guid) DO UPDATE SET
                  session_id=excluded.session_id, local_task_id=excluded.local_task_id,
                  upstream_task_id=excluded.upstream_task_id,
                  upstream_session_id=excluded.upstream_session_id,
                  upstream_state=excluded.upstream_state, summary=excluded.summary,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    caller_id, chat_guid, merged.get("session_id", ""),
                    merged.get("local_task_id"), merged.get("upstream_task_id"),
                    merged.get("upstream_session_id"), merged.get("upstream_state"),
                    merged.get("summary", ""),
                ),
            )

    def save_task_context(self, caller_id: str, task_id: str, context: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_contexts_v2(caller_id, task_id, context_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(caller_id, task_id) DO UPDATE SET
                  context_json=excluded.context_json, updated_at=CURRENT_TIMESTAMP
                """,
                (caller_id, task_id, json.dumps(context, ensure_ascii=False)),
            )

    def task_context(self, caller_id: str, task_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT context_json FROM task_contexts_v2 WHERE caller_id = ? AND task_id = ?",
                (caller_id, task_id),
            ).fetchone()
        return json.loads(row["context_json"]) if row else None

    def save_pending_agent_choices(
        self,
        caller_id: str,
        chat_guid: str,
        query_text: str,
        candidates: list[dict[str, Any]],
        discovery_reply: str,
        expires_at: int,
    ) -> None:
        if os.getenv("ABLATION_SHARED_SESSION") == "1":
            caller_id, chat_guid = "shared", "shared"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_agent_choices_v1(
                  caller_id, chat_guid, query_text, candidates_json, discovery_reply, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(caller_id, chat_guid) DO UPDATE SET
                  query_text=excluded.query_text, candidates_json=excluded.candidates_json,
                  discovery_reply=excluded.discovery_reply, expires_at=excluded.expires_at,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (caller_id, chat_guid, query_text, json.dumps(candidates, ensure_ascii=False), discovery_reply, expires_at),
            )

    def pending_agent_choices(self, caller_id: str, chat_guid: str, now_epoch: int) -> dict[str, Any] | None:
        if os.getenv("ABLATION_SHARED_SESSION") == "1":
            caller_id, chat_guid = "shared", "shared"
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM pending_agent_choices_v1
                WHERE caller_id = ? AND chat_guid = ? AND expires_at > ?
                """,
                (caller_id, chat_guid, now_epoch),
            ).fetchone()
            if row is None:
                conn.execute(
                    "DELETE FROM pending_agent_choices_v1 WHERE caller_id = ? AND chat_guid = ? AND expires_at <= ?",
                    (caller_id, chat_guid, now_epoch),
                )
        if row is None:
            return None
        value = dict(row)
        value["candidates"] = json.loads(value.pop("candidates_json"))
        return value

    def clear_pending_agent_choices(self, caller_id: str, chat_guid: str) -> None:
        if os.getenv("ABLATION_SHARED_SESSION") == "1":
            caller_id, chat_guid = "shared", "shared"
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pending_agent_choices_v1 WHERE caller_id = ? AND chat_guid = ?",
                (caller_id, chat_guid),
            )

    def add_message(self, caller_id: str, chat_guid: str, direction: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversation_messages_v2(caller_id, chat_guid, direction, content) VALUES (?, ?, ?, ?)",
                (caller_id, chat_guid, direction, content),
            )

    def history(self, caller_id: str, chat_guid: str, limit: int) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT direction, content FROM conversation_messages_v2
                WHERE caller_id = ? AND chat_guid = ?
                ORDER BY id DESC LIMIT ?
                """,
                (caller_id, chat_guid, limit),
            ).fetchall()
        return [{"role": "user" if row["direction"] == "user" else "assistant", "content": row["content"]} for row in reversed(rows)]
