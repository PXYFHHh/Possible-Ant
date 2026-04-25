"""
RAG 元数据数据库模块 —— SQLite 持久化层

管理文档、分块、父块、入库任务四类元数据。
使用 WAL 模式 + RLock 保证线程安全，支持并发读写。

表结构：
  documents      —— 文档元信息（doc_id, source, content_hash, chunk_count, vector_indexed）
  chunks         —— 叶分块（L3），包含文本和层级关系
  parent_chunks  —— 父分块（L1/L2），用于 Auto-merging
  ingest_jobs    —— 入库任务状态追踪
"""

import hashlib
import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .config import (
    RAG_DB_PATH,
    FILES_DIR,
    LEGACY_METADATA_PATH,
)


def _now_str() -> str:
    """返回当前时间的格式化字符串（YYYY-MM-DD HH:MM:SS）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sha256_file(file_path: Path) -> str:
    """计算文件的 SHA256 哈希值，按 1MB 块读取避免内存溢出"""
    digest = hashlib.sha256()
    with file_path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Database:
    """
    SQLite 数据库管理类。
    
    线程安全：使用 RLock + 每次操作创建新连接，支持多线程并发访问。
    性能优化：WAL 模式 + NORMAL 同步 + 64MB 缓存 + 内存临时存储。
    """
    
    def __init__(self, db_path: Path = RAG_DB_PATH, logger: Optional[logging.Logger] = None):
        """
        Args:
            db_path: SQLite 数据库文件路径
            logger: 日志记录器
        """
        self.db_path = db_path
        self._lock = threading.RLock()
        self.logger = logger or logging.getLogger("agent.rag.database")
        self._ensure_database()
    
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """
        获取数据库连接的上下文管理器。

        自动提交/回滚，设置 WAL 模式和外键约束。
        每次操作创建新连接，避免多线程共享连接的问题。
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")
            conn.execute("PRAGMA temp_store = MEMORY")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
    
    def _ensure_database(self) -> None:
        """初始化数据库表结构和索引（幂等操作，重复调用安全）"""
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    vector_indexed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_uid TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    page INTEGER,
                    chunk_id TEXT NOT NULL,
                    parent_chunk_id TEXT NOT NULL DEFAULT '',
                    root_chunk_id TEXT NOT NULL DEFAULT '',
                    chunk_level INTEGER NOT NULL DEFAULT 3,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS parent_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    text TEXT NOT NULL,
                    page INTEGER,
                    parent_chunk_id TEXT NOT NULL DEFAULT '',
                    root_chunk_id TEXT NOT NULL DEFAULT '',
                    chunk_level INTEGER NOT NULL DEFAULT 1,
                    chunk_idx INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_jobs (
                    job_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    total_chunks INTEGER NOT NULL DEFAULT 0,
                    embedded_chunks INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_chunk_level ON chunks(chunk_level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_parent_chunk_id ON chunks(parent_chunk_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_chunks_source ON parent_chunks(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_chunks_parent_chunk_id ON parent_chunks(parent_chunk_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ingest_jobs_started_at ON ingest_jobs(started_at)")

            for col in ("total_chunks", "embedded_chunks"):
                try:
                    conn.execute(f"ALTER TABLE ingest_jobs ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0")
                except Exception:
                    pass
    
    def count_documents(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(1) AS cnt FROM documents").fetchone()
        return int(row["cnt"] if row else 0)
    
    def count_chunks(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(1) AS cnt FROM chunks").fetchone()
        return int(row["cnt"] if row else 0)

    def get_chunk_length_stats(self) -> Dict[str, Any]:
        """统计分块文本长度分布，返回最小/最大/平均值和分段分布"""
        with self._conn() as conn:
            rows = conn.execute("SELECT LENGTH(text) AS len FROM chunks").fetchall()
        lengths = [row["len"] for row in rows if row["len"] is not None]
        if not lengths:
            return {"total": 0, "min": 0, "max": 0, "avg": 0, "distribution": []}
        total = len(lengths)
        min_len = min(lengths)
        max_len = max(lengths)
        avg_len = sum(lengths) / total
        bins = [(0, 100), (100, 200), (200, 300), (300, 500), (500, 800), (800, 1200), (1200, 2000), (2000, 999999)]
        distribution = []
        for low, high in bins:
            count = sum(1 for l in lengths if low <= l < high)
            if count > 0:
                label = f"{low}-{high}" if high < 999999 else f"{low}+"
                distribution.append({"range": label, "count": count, "min": low, "max": high})
        return {"total": total, "min": min_len, "max": max_len, "avg": round(avg_len, 1), "distribution": distribution}
    
    def count_vector_documents(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(1) AS cnt FROM documents WHERE vector_indexed=1").fetchone()
        return int(row["cnt"] if row else 0)
    
    def fetch_sources(self) -> set:
        with self._conn() as conn:
            rows = conn.execute("SELECT source FROM documents").fetchall()
        return {row["source"] for row in rows}
    
    def list_documents(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT source, chunk_count, updated_at
                FROM documents
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_ingest_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM ingest_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_ingest_total(self, job_id: str, total: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE ingest_jobs SET total_chunks = ? WHERE job_id = ?",
                (total, job_id),
            )

    def update_ingest_progress(self, job_id: str, embedded: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE ingest_jobs SET embedded_chunks = ? WHERE job_id = ?",
                (embedded, job_id),
            )
    
    def get_document_by_source(self, source: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE source = ?",
                (source,),
            ).fetchone()
        if row:
            return dict(row)
        return None
    
    def get_document_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
        if row:
            return dict(row)
        return None
    
    def insert_document(self, doc_data: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (
                    doc_id, source, file_path, content_hash, file_size, chunk_count,
                    vector_indexed, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_data["doc_id"],
                    doc_data["source"],
                    doc_data["file_path"],
                    doc_data["content_hash"],
                    doc_data.get("file_size", 0),
                    doc_data.get("chunk_count", 0),
                    doc_data.get("vector_indexed", 0),
                    doc_data.get("created_at", _now_str()),
                    doc_data.get("updated_at", _now_str()),
                ),
            )
    
    def delete_document(self, doc_id: str) -> List[str]:
        """
        删除文档及其所有分块（含父块），级联删除。

        Args:
            doc_id: 文档 ID

        Returns:
            被删除的 chunk_uid 列表（用于同步清理向量索引）
        """
        with self._conn() as conn:
            chunk_rows = conn.execute(
                "SELECT chunk_uid FROM chunks WHERE doc_id = ?",
                (doc_id,),
            ).fetchall()
            chunk_ids = [r["chunk_uid"] for r in chunk_rows]
            
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM parent_chunks WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        
        return chunk_ids
    
    def insert_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        if not chunks:
            return
        
        with self._conn() as conn:
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO chunks (
                        chunk_uid, doc_id, source, chunk_index, text, page,
                        chunk_id, parent_chunk_id, root_chunk_id, chunk_level,
                        metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk["chunk_uid"],
                        chunk["doc_id"],
                        chunk["source"],
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk.get("page"),
                        chunk["chunk_id"],
                        chunk.get("parent_chunk_id", ""),
                        chunk.get("root_chunk_id", ""),
                        chunk.get("chunk_level", 3),
                        json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                        _now_str(),
                    ),
                )
    
    def insert_parent_chunks(self, parent_chunks: List[Dict[str, Any]]) -> None:
        if not parent_chunks:
            return
        
        with self._conn() as conn:
            for chunk in parent_chunks:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO parent_chunks (
                        chunk_id, doc_id, source, text, page,
                        parent_chunk_id, root_chunk_id, chunk_level, chunk_idx, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk["chunk_id"],
                        chunk["doc_id"],
                        chunk["source"],
                        chunk["text"],
                        chunk.get("page"),
                        chunk.get("parent_chunk_id", ""),
                        chunk.get("root_chunk_id", ""),
                        chunk.get("chunk_level", 1),
                        chunk.get("chunk_idx", 0),
                        _now_str(),
                    ),
                )
    
    def get_parent_chunks_by_ids(self, chunk_ids: List[str]) -> Dict[str, Dict]:
        if not chunk_ids:
            return {}
        
        ids = [item for item in chunk_ids if item]
        if not ids:
            return {}
        
        with self._conn() as conn:
            placeholders = ",".join(["?"] * len(ids))
            rows = conn.execute(
                f"""
                SELECT chunk_id, text, source, page, parent_chunk_id, root_chunk_id, chunk_level, chunk_idx
                FROM parent_chunks
                WHERE chunk_id IN ({placeholders})
                """,
                tuple(ids),
            ).fetchall()
        
        return {
            row["chunk_id"]: {
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "source": row["source"],
                "page": row["page"],
                "parent_chunk_id": row["parent_chunk_id"],
                "root_chunk_id": row["root_chunk_id"],
                "chunk_level": row["chunk_level"],
                "chunk_idx": row["chunk_idx"],
            }
            for row in rows
        }
    
    def get_leaf_chunks(self, leaf_level: int = 3) -> List[Dict[str, Any]]:
        """
        获取指定层级的叶分块，用于构建 BM25 索引。

        Args:
            leaf_level: 叶节点层级（默认 3，即 L3）

        Returns:
            [{"id": chunk_uid, "text": str, "metadata": dict}, ...]
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT chunk_uid, source, chunk_index, text, metadata_json, chunk_level
                FROM chunks
                WHERE chunk_level = ?
                ORDER BY source, chunk_index
                """,
                (leaf_level,),
            ).fetchall()
        
        chunks = []
        for row in rows:
            metadata = {}
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except Exception:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.setdefault("source", row["source"])
            metadata.setdefault("chunk_id", int(row["chunk_index"]))
            
            chunks.append({
                "id": row["chunk_uid"],
                "text": row["text"] or "",
                "metadata": metadata,
            })
        
        return chunks
    
    def existing_chunk_ids(self, chunk_ids: List[str]) -> set:
        """批量检查哪些 chunk_uid 在数据库中已存在，用于过滤向量检索中的脏数据"""
        if not chunk_ids:
            return set()
        
        with self._conn() as conn:
            placeholders = ",".join(["?"] * len(chunk_ids))
            rows = conn.execute(
                f"SELECT chunk_uid FROM chunks WHERE chunk_uid IN ({placeholders})",
                tuple(chunk_ids),
            ).fetchall()
        
        return {row["chunk_uid"] for row in rows}
    
    def create_ingest_job(self, job_id: str, source: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ingest_jobs (job_id, source, status, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (job_id, source, "running", _now_str()),
            )
    
    def finish_ingest_job(
        self,
        job_id: str,
        status: str,
        chunk_count: int = 0,
        error_message: str = "",
        duration_ms: int = 0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE ingest_jobs
                SET finished_at = ?, status = ?, chunk_count = ?, error_message = ?, duration_ms = ?
                WHERE job_id = ?
                """,
                (_now_str(), status, chunk_count, error_message, duration_ms, job_id),
            )
    
    def list_ingest_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT job_id, source, status, started_at, finished_at, duration_ms, chunk_count, error_message
                FROM ingest_jobs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        
        return [dict(row) for row in rows]
    
    def update_document_chunk_count(self, doc_id: str, chunk_count: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET chunk_count = ?, updated_at = ? WHERE doc_id = ?",
                (chunk_count, _now_str(), doc_id),
            )
    
    def set_document_vector_indexed(self, doc_id: str, indexed: bool = True) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET vector_indexed = ?, updated_at = ? WHERE doc_id = ?",
                (1 if indexed else 0, _now_str(), doc_id),
            )
