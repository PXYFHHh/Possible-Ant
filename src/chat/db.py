import json
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

CHAT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chat"
CHAT_DB_PATH = CHAT_DATA_DIR / "chat_history.sqlite3"

MAX_CONVERSATIONS = 50
MAX_MESSAGES_PER_CONVERSATION = 200


def _now_ts() -> float:
    return datetime.now().timestamp()


def _make_id() -> str:
    return uuid.uuid4().hex[:16]


class ChatDatabase:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or CHAT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.logger = logging.getLogger("agent.chat.database")
        self._ensure_tables()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _ensure_tables(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '新对话',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    segments_json TEXT DEFAULT '[]',
                    token_stats_json TEXT DEFAULT '{}',
                    sort_order INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(conv_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conv_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_sort_order ON messages(conv_id, sort_order)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC)"
            )

    # ========== Conversations ==========

    def list_conversations(self, limit: int = MAX_CONVERSATIONS) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at, active
                FROM conversations ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at, active FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_conversation(self, title: str = "新对话") -> Dict[str, Any]:
        now = _now_ts()
        conv_id = _make_id()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, active) VALUES (?, ?, ?, ?, 1)",
                (conv_id, title, now, now),
            )
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

    def update_conversation_title(self, conv_id: str, title: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now_ts(), conv_id),
            )

    def touch_conversation(self, conv_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (_now_ts(), conv_id)
            )

    def set_active_conversation(self, conv_id: str) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET active = 0")
            conn.execute("UPDATE conversations SET active = 1, updated_at = ? WHERE id = ?", (_now_ts(), conv_id))

    def get_active_conversation_id(self) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE active = 1 LIMIT 1"
            ).fetchone()
        return dict(row)["id"] if row else None

    def delete_conversation(self, conv_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conv_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    def delete_conversations_batch(self, conv_ids: List[str]) -> int:
        if not conv_ids:
            return 0
        placeholders = ",".join(["?"] * len(conv_ids))
        with self._conn() as conn:
            cursor = conn.execute(
                f"DELETE FROM conversations WHERE id IN ({placeholders})", tuple(conv_ids)
            )
        return cursor.rowcount

    def count_all_messages(self, conv_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS cnt FROM messages WHERE conv_id = ?", (conv_id,)
            ).fetchone()
        return int(row["cnt"] if row else 0)

    # ========== Messages ==========

    def get_messages(self, conv_id: str, limit: int = MAX_MESSAGES_PER_CONVERSATION) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, conv_id, role, content, segments_json, token_stats_json, sort_order, created_at
                FROM messages WHERE conv_id = ?
                ORDER BY sort_order ASC LIMIT ?
                """,
                (conv_id, limit),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["segments"] = json.loads(d.pop("segments_json", "[]"))
            except Exception:
                d["segments"] = []
            try:
                d["token_stats"] = json.loads(d.pop("token_stats_json", "{}"))
            except Exception:
                d["token_stats"] = {}
            result.append(d)
        return result

    def append_user_message(self, conv_id: str, content: str) -> Dict[str, Any]:
        now = _now_ts()
        order = self.count_all_messages(conv_id)
        msg_id = self._trim_and_insert(conv_id, "user", content, [], {}, order, now)
        self.touch_conversation(conv_id)
        return {"role": "user", "content": content, "sort_order": order}

    def create_assistant_message(self, conv_id: str) -> Dict[str, Any]:
        now = _now_ts()
        order = self.count_all_messages(conv_id)
        msg_id = self._trim_and_insert(conv_id, "assistant", "", [], {}, order, now)
        self.touch_conversation(conv_id)
        return {"id": msg_id, "role": "assistant", "segments": [], "sort_order": order}

    def append_text_segment(self, conv_id: str, msg_db_id: int, content: str) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT segments_json FROM messages WHERE id = ? AND conv_id = ?", (msg_db_id, conv_id)
            ).fetchone()
            if not row:
                return
            segments = json.loads(row["segments_json"] or "[]")
            if segments and segments[-1].get("type") == "text":
                segments[-1]["content"] += content
            else:
                segments.append({"type": "text", "content": content})
            conn.execute(
                "UPDATE messages SET segments_json = ? WHERE id = ?",
                (json.dumps(segments, ensure_ascii=False), msg_db_id),
            )

    def add_tool_call_segment(self, conv_id: str, msg_db_id: int, name: str, args: dict) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT segments_json FROM messages WHERE id = ? AND conv_id = ?", (msg_db_id, conv_id)
            ).fetchone()
            if not row:
                return
            segments = json.loads(row["segments_json"] or "[]")
            segments.append({"type": "tool_call", "name": name, "args": args, "result": ""})
            conn.execute(
                "UPDATE messages SET segments_json = ? WHERE id = ?",
                (json.dumps(segments, ensure_ascii=False), msg_db_id),
            )

    def update_tool_result(self, conv_id: str, msg_db_id: int, result: str) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT segments_json FROM messages WHERE id = ? AND conv_id = ?", (msg_db_id, conv_id)
            ).fetchone()
            if not row:
                return
            segments = json.loads(row["segments_json"] or "[]")
            for seg in reversed(segments):
                if seg.get("type") == "tool_call":
                    seg["result"] = result
                    break
            conn.execute(
                "UPDATE messages SET segments_json = ? WHERE id = ?",
                (json.dumps(segments, ensure_ascii=False), msg_db_id),
            )

    def set_token_stats(self, conv_id: str, msg_db_id: int, stats: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE messages SET token_stats_json = ? WHERE id = ? AND conv_id = ?",
                (json.dumps(stats), msg_db_id, conv_id),
            )

    def get_last_assistant_msg_id(self, conv_id: str) -> Optional[int]:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM messages WHERE conv_id = ? AND role = 'assistant'
                ORDER BY sort_order DESC LIMIT 1
                """,
                (conv_id,),
            ).fetchone()
        return row["id"] if row else None

    def _trim_and_insert(
        self, conv_id: str, role: str, content: str, segments: list, token_stats: dict, order: int, now: float
    ) -> int:
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(1) AS cnt FROM messages WHERE conv_id = ?", (conv_id,)
            ).fetchone()["cnt"]
            if total >= MAX_MESSAGES_PER_CONVERSATION:
                excess = total - MAX_MESSAGES_PER_CONVERSATION + 1
                old_ids = conn.execute(
                    f"""
                    SELECT id FROM messages WHERE conv_id = ?
                    ORDER BY sort_order ASC LIMIT {excess}
                    """,
                    (conv_id,),
                ).fetchall()
                for oid in old_ids:
                    conn.execute("DELETE FROM messages WHERE id = ?", (oid["id"],))
                conn.execute(
                    f"""
                    UPDATE messages SET sort_order = sort_order - {excess}
                    WHERE conv_id = ?
                    """,
                    (conv_id,),
                )
                order -= excess
            cursor = conn.execute(
                """
                INSERT INTO messages (conv_id, role, content, segments_json, token_stats_json, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conv_id,
                    role,
                    content,
                    json.dumps(segments, ensure_ascii=False),
                    json.dumps(token_stats),
                    order,
                    now,
                ),
            )
        return cursor.lastrowid


_global_chat_db: Optional[ChatDatabase] = None
_chat_db_lock = threading.Lock()


def get_chat_db() -> ChatDatabase:
    global _global_chat_db
    if _global_chat_db is None:
        with _chat_db_lock:
            if _global_chat_db is None:
                _global_chat_db = ChatDatabase()
    return _global_chat_db
