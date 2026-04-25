"""
会话数据库模块 —— 对话历史持久化

管理用户与 Agent 的对话记录，包括：
  - conversations 表：对话元信息（ID、标题、创建/更新时间、是否活跃）
  - messages 表：消息内容（角色、文本、分段、Token 统计、排序）

消息分段 (segments) 设计：
  每条 assistant 消息由多个 segment 组成，存储为 JSON 数组：
    - {"type": "text", "content": "..."}          文本内容
    - {"type": "tool_call", "name": "...", "args": {...}, "result": "..."}  工具调用

线程安全：使用 RLock + 每次操作创建新连接。
容量限制：每个对话最多 200 条消息，超出时自动裁剪最早的消息。
"""

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

CHAT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chat"  # 会话数据目录
CHAT_DB_PATH = CHAT_DATA_DIR / "chat_history.sqlite3"                            # 数据库文件路径

MAX_CONVERSATIONS = 50                    # 最大对话数量
MAX_MESSAGES_PER_CONVERSATION = 200       # 每个对话最大消息数量


def _now_ts() -> float:
    """返回当前时间戳"""
    return datetime.now().timestamp()


def _make_id() -> str:
    """生成 16 位十六进制随机 ID"""
    return uuid.uuid4().hex[:16]


class ChatDatabase:
    """
    会话数据库管理类。
    
    提供对话和消息的 CRUD 操作，支持分段式消息更新（流式追加文本、工具调用）。
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Args:
            db_path: 数据库文件路径，默认使用 data/chat/chat_history.sqlite3
        """
        self.db_path = db_path or CHAT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.logger = logging.getLogger("agent.chat.database")
        self._ensure_tables()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """获取数据库连接的上下文管理器，自动提交/回滚"""
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
        """初始化数据库表结构和索引（幂等操作）"""
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
        """获取对话列表，按更新时间降序排列"""
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
        """获取单个对话的元信息"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at, active FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_conversation(self, title: str = "新对话") -> Dict[str, Any]:
        """创建新对话，自动设为活跃状态"""
        now = _now_ts()
        conv_id = _make_id()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, active) VALUES (?, ?, ?, ?, 1)",
                (conv_id, title, now, now),
            )
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

    def update_conversation_title(self, conv_id: str, title: str) -> None:
        """更新对话标题"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, _now_ts(), conv_id),
            )

    def touch_conversation(self, conv_id: str) -> None:
        """更新对话的 updated_at 时间戳"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (_now_ts(), conv_id)
            )

    def set_active_conversation(self, conv_id: str) -> None:
        """设置活跃对话（同时取消其他对话的活跃状态）"""
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET active = 0")
            conn.execute("UPDATE conversations SET active = 1, updated_at = ? WHERE id = ?", (_now_ts(), conv_id))

    def get_active_conversation_id(self) -> Optional[str]:
        """获取当前活跃对话的 ID"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE active = 1 LIMIT 1"
            ).fetchone()
        return dict(row)["id"] if row else None

    def delete_conversation(self, conv_id: str) -> None:
        """删除对话及其所有消息"""
        with self._conn() as conn:
            conn.execute("DELETE FROM messages WHERE conv_id = ?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))

    def delete_conversations_batch(self, conv_ids: List[str]) -> int:
        """批量删除对话，返回实际删除数量"""
        if not conv_ids:
            return 0
        placeholders = ",".join(["?"] * len(conv_ids))
        with self._conn() as conn:
            cursor = conn.execute(
                f"DELETE FROM conversations WHERE id IN ({placeholders})", tuple(conv_ids)
            )
        return cursor.rowcount

    def count_all_messages(self, conv_id: str) -> int:
        """统计对话中的消息总数"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS cnt FROM messages WHERE conv_id = ?", (conv_id,)
            ).fetchone()
        return int(row["cnt"] if row else 0)

    # ========== Messages ==========

    def get_messages(self, conv_id: str, limit: int = MAX_MESSAGES_PER_CONVERSATION) -> List[Dict[str, Any]]:
        """
        获取对话中的消息列表。
        
        自动将 segments_json 和 token_stats_json 反序列化为 Python 对象。
        """
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
        """追加用户消息，自动更新对话时间戳"""
        now = _now_ts()
        order = self.count_all_messages(conv_id)
        msg_id = self._trim_and_insert(conv_id, "user", content, [], {}, order, now)
        self.touch_conversation(conv_id)
        return {"role": "user", "content": content, "sort_order": order}

    def create_assistant_message(self, conv_id: str) -> Dict[str, Any]:
        """创建空的 assistant 消息（后续通过 segment 方法逐步填充内容）"""
        now = _now_ts()
        order = self.count_all_messages(conv_id)
        msg_id = self._trim_and_insert(conv_id, "assistant", "", [], {}, order, now)
        self.touch_conversation(conv_id)
        return {"id": msg_id, "role": "assistant", "segments": [], "sort_order": order}

    def append_text_segment(self, conv_id: str, msg_db_id: int, content: str) -> None:
        """
        追加文本分段到 assistant 消息。
        
        如果最后一个 segment 也是 text 类型，则合并内容（流式输出优化）；
        否则创建新的 text segment。
        """
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

    def append_reasoning_segment(self, conv_id: str, msg_db_id: int, content: str) -> None:
        """
        追加思考过程分段到 assistant 消息。
        
        如果最后一个 segment 也是 reasoning 类型，则合并内容；
        否则创建新的 reasoning segment。
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT segments_json FROM messages WHERE id = ? AND conv_id = ?", (msg_db_id, conv_id)
            ).fetchone()
            if not row:
                return
            segments = json.loads(row["segments_json"] or "[]")
            if segments and segments[-1].get("type") == "reasoning":
                segments[-1]["content"] += content
            else:
                segments.append({"type": "reasoning", "content": content})
            conn.execute(
                "UPDATE messages SET segments_json = ? WHERE id = ?",
                (json.dumps(segments, ensure_ascii=False), msg_db_id),
            )

    def add_tool_call_segment(self, conv_id: str, msg_db_id: int, name: str, args: dict) -> None:
        """添加工具调用分段到 assistant 消息（result 初始为空，后续通过 update_tool_result 填充）"""
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
        """更新最后一个工具调用分段的执行结果"""
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
        """设置消息的 Token 消耗统计"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE messages SET token_stats_json = ? WHERE id = ? AND conv_id = ?",
                (json.dumps(stats), msg_db_id, conv_id),
            )

    def get_last_assistant_msg_id(self, conv_id: str) -> Optional[int]:
        """获取对话中最后一条 assistant 消息的数据库 ID"""
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
        """
        插入消息并自动裁剪超出容量的旧消息。
        
        当消息数超过 MAX_MESSAGES_PER_CONVERSATION 时，
        删除最早的 excess 条消息并调整剩余消息的 sort_order。
        
        Returns:
            新插入消息的数据库 ID
        """
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
    """获取全局 ChatDatabase 单例（双重检查锁，线程安全）"""
    global _global_chat_db
    if _global_chat_db is None:
        with _chat_db_lock:
            if _global_chat_db is None:
                _global_chat_db = ChatDatabase()
    return _global_chat_db
