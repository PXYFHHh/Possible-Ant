"""
RAG 统一服务模块 —— 文档入库、检索查询、删除、健康检查的入口

本模块是 RAG 系统的核心服务层，协调各子模块完成完整的 RAG 流程：
  文档入库: ingest_file → 分块(chunker) → 向量化(embedding) → 持久化(database+chroma)
  检索查询: query → 多路召回(BM25+向量) → 混合融合(RRF/线性) → 重排(reranker) → Auto-merging

关键特性：
  - 三层嵌套分块 (L1→L2→L3) + Auto-merging 自动合并
  - 混合检索 (BM25 稀疏 + 向量密集) + RRF/线性融合
  - 查询改写 (多变体生成 + 加权融合)
  - 异步入库 (线程池 + 进度追踪)
"""

import hashlib
import json
import logging
import os
import threading
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cache import LruCache
from .chunker import Chunker
from .config import (
    AUTO_MERGE_ENABLED,
    AUTO_MERGE_THRESHOLD,
    BASE_DIR,
    BM25_PERSIST_ENABLED,
    CACHE_ENABLED,
    CACHE_MAX_SIZE,
    CACHE_TTL_SECONDS,
    CHROMA_DIR,
    FILES_DIR,
    HYBRID_MODE,
    LEAF_RETRIEVE_LEVEL,
    LEGACY_METADATA_PATH,
    RAG_DB_PATH,
    RAG_LOG_LEVEL,
    RAG_LOG_PATH,
    RRF_ENABLED,
    RRF_K,
)
from .database import Database, _sha256_file
from .embedding import EmbeddingService
from .reranker import RerankerService
from .bm25_index import BM25Index
from .query_rewriter import build_variant_weights
from .retriever import Retriever

warnings.filterwarnings(
    "ignore",
    message=r"Accessing `__path__`.*",
    category=FutureWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r".*Behavior may be different.*",
    category=FutureWarning,
)


class RagService:
    """
    RAG 统一服务：入库、查询、删除、健康检查。支持三层分块和Auto-merging。

    子模块协调关系：
      Chunker         → 文档分块（三层嵌套 + Markdown 结构感知）
      EmbeddingService → 向量嵌入 + Chroma 向量库
      BM25Index       → BM25 稀疏索引
      RerankerService → Cross-Encoder 重排序
      Database        → SQLite 元数据管理
      Retriever       → 混合检索 + RRF/线性融合 + Auto-merging
      LruCache        → 父块缓存
    """

    def __init__(self):
        self._ensure_dirs()
        self.logger = self._build_logger()

        self._db = Database(logger=self.logger)
        self._embedding = EmbeddingService(logger=self.logger)
        self._reranker = RerankerService(logger=self.logger)
        self._bm25 = BM25Index(logger=self.logger)
        self._chunker = Chunker()
        
        self._parent_chunk_cache = LruCache(
            max_size=CACHE_MAX_SIZE,
            ttl_seconds=CACHE_TTL_SECONDS,
        ) if CACHE_ENABLED else None
        
        self._retriever = Retriever(
            database=self._db,
            parent_chunk_cache=self._parent_chunk_cache,
        )
        
        if BM25_PERSIST_ENABLED:
            self._bm25.load_state(self._db.count_chunks())

        self._active_jobs: Dict[str, threading.Thread] = {}

    def _build_logger(self) -> logging.Logger:
        """构建 RAG 模块专用的文件日志记录器，输出到 RAG_LOG_PATH"""
        logger = logging.getLogger("agent.rag")
        if logger.handlers:
            return logger

        level = getattr(logging, RAG_LOG_LEVEL, logging.INFO)
        logger.setLevel(level)
        logger.propagate = False

        RAG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(RAG_LOG_PATH, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def _ensure_dirs(self) -> None:
        """确保文件存储、向量库、数据库等目录存在"""
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        RAG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _build_doc_id(self, source: str, content_hash: str) -> str:
        """根据文件名和内容哈希生成唯一文档 ID（SHA256 前32位）"""
        seed = f"{source}::{content_hash}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

    def _invalidate_indexes(self) -> None:
        """使 BM25 索引和父块缓存失效（文档变更后调用）"""
        self._bm25.invalidate()
        
        if self._parent_chunk_cache:
            self._parent_chunk_cache.clear()

    def health_status(self, job_limit: int = 5, probe_models: bool = False) -> dict:
        """
        获取 RAG 系统健康状态摘要。

        Args:
            job_limit: 返回的最近入库任务数量
            probe_models: 是否探测模型加载状态（会触发首次加载）

        Returns:
            包含各子模块状态的字典
        """
        vector_ready = self._embedding._vectorstore is not None
        vector_error = ""
        if probe_models and not vector_ready:
            try:
                self._embedding.get_vectorstore()
                vector_ready = True
            except Exception as exc:
                vector_error = str(exc)

        cache_stats = None
        if self._parent_chunk_cache:
            cache_stats = self._parent_chunk_cache.stats()

        return {
            "ok": True,
            "db_path": str(RAG_DB_PATH),
            "log_path": str(RAG_LOG_PATH),
            "documents": self._db.count_documents(),
            "chunks": self._db.count_chunks(),
            "vector_indexed_documents": self._db.count_vector_documents(),
            "vectorstore_ready": vector_ready,
            "vectorstore_error": vector_error,
            "reranker_disabled": self._reranker.is_disabled,
            "reranker_last_error": self._reranker.last_error,
            "auto_merge_enabled": AUTO_MERGE_ENABLED,
            "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
            "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
            "rrf_enabled": RRF_ENABLED,
            "rrf_k": RRF_K,
            "hybrid_mode": HYBRID_MODE,
            "cache_enabled": CACHE_ENABLED,
            "cache_stats": cache_stats,
            "bm25_persist_enabled": BM25_PERSIST_ENABLED,
            "bm25_doc_count": self._bm25.doc_count,
            "recent_jobs": self._db.list_ingest_jobs(limit=job_limit),
        }

    def list_documents(self) -> List[Dict[str, Any]]:
        return self._db.list_documents()

    def get_chunk_stats(self) -> Dict[str, Any]:
        return self._db.get_chunk_length_stats()

    def list_ingest_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._db.list_ingest_jobs(limit=limit)

    def delete_document(self, source: str) -> dict:
        """
        删除指定文档及其所有分块和向量索引。

        Args:
            source: 文件名

        Returns:
            {"ok": bool, "message": str, "deleted_chunks": int}
        """
        return self._delete_document_internal(source=source, ignore_missing=False)

    def _delete_document_internal(self, source: str, ignore_missing: bool = False) -> dict:
        """
        内部删除文档实现。

        Args:
            source: 文件名
            ignore_missing: 文档不存在时是否静默跳过（入库时先删旧版本用）

        Returns:
            操作结果字典
        """
        doc = self._db.get_document_by_source(source)
        if not doc:
            if ignore_missing:
                return {"ok": True, "message": "文档不存在，跳过删除"}
            return {"ok": False, "message": f"文档不存在: {source}"}

        doc_id = doc["doc_id"]
        chunk_ids = self._db.delete_document(doc_id)

        if chunk_ids:
            try:
                vs = self._embedding.get_vectorstore()
                vs.delete(ids=chunk_ids)
            except Exception as exc:
                self.logger.warning("Vector delete failed for %s: %s", source, exc)

        self._invalidate_indexes()
        return {"ok": True, "message": f"已删除文档: {source}", "deleted_chunks": len(chunk_ids)}

    def ingest_file(self, filename: str) -> dict:
        """
        异步入库文件。

        启动后台线程执行入库流程，立即返回任务 ID。
        入库流程：删除旧版本 → 分块 → 写入数据库 → 向量化 → 更新索引

        Args:
            filename: 文件名（须位于 files 目录下）

        Returns:
            {"ok": bool, "message": str, "job_id": str, "source": str, "status": str}
        """
        source = str(filename).strip()
        if not source:
            return {"ok": False, "message": "filename 不能为空"}

        file_path = FILES_DIR / source
        if not file_path.exists():
            return {"ok": False, "message": f"文件不存在: {file_path}"}

        try:
            file_path.relative_to(FILES_DIR.resolve())
        except ValueError:
            return {"ok": False, "message": "仅允许上传 files 目录中的文件"}

        job_id = str(uuid.uuid4())
        self._db.create_ingest_job(job_id, source)

        if job_id in self._active_jobs and self._active_jobs[job_id].is_alive():
            return {"ok": False, "message": "该文档正在入库中，请稍候"}

        thread = threading.Thread(target=self._do_ingest, args=(job_id, source, file_path), daemon=True)
        self._active_jobs[job_id] = thread
        thread.start()

        return {
            "ok": True,
            "message": "已开始入库",
            "job_id": job_id,
            "source": source,
            "status": "running",
        }

    def _do_ingest(self, job_id: str, source: str, file_path: Path) -> None:
        """
        实际入库逻辑（在后台线程中执行）。

        流程：
          1. 删除同源旧文档
          2. 计算内容哈希，生成 doc_id
          3. 调用 Chunker 分块（三层嵌套）
          4. 写入 SQLite 元数据
          5. 批量向量化并写入 Chroma
          6. 更新索引和任务状态
        """
        started = time.perf_counter()
        try:
            delete_result = self._delete_document_internal(source=source, ignore_missing=True)
            if not delete_result.get("ok"):
                raise RuntimeError(delete_result.get("message", "删除旧文档失败"))

            content_hash = _sha256_file(file_path)
            doc_id = self._build_doc_id(source, content_hash)
            file_size = int(file_path.stat().st_size)

            all_chunks, all_parent_chunks = self._chunker.process_document(
                file_path=file_path, source=source, doc_id=doc_id,
            )

            if not all_chunks:
                raise RuntimeError("文档切片结果为空")

            total = len(all_chunks)
            self._db.set_ingest_total(job_id, total)

            self._db.insert_document({
                "doc_id": doc_id, "source": source, "file_path": str(file_path),
                "content_hash": content_hash, "file_size": file_size,
                "chunk_count": total, "vector_indexed": 0,
            })

            chunk_records = []
            for idx, chunk in enumerate(all_chunks):
                chunk_records.append({
                    "chunk_uid": f"{doc_id}::chunk::{idx}", "doc_id": doc_id,
                    "source": source, "chunk_index": idx, "text": chunk["text"],
                    "page": chunk.get("page_number"), "chunk_id": chunk["chunk_id"],
                    "parent_chunk_id": chunk.get("parent_chunk_id", ""),
                    "root_chunk_id": chunk.get("root_chunk_id", ""),
                    "chunk_level": chunk.get("chunk_level", 3), "metadata": chunk,
                })

            self._db.insert_chunks(chunk_records)
            self._db.insert_parent_chunks(all_parent_chunks)

            vs = self._embedding.get_vectorstore()
            chroma_batch_size = self._embedding.detect_batch_size(vs)
            embedding = self._embedding.get_embedding()
            all_texts = [c["text"] for c in all_chunks]
            embed_batch_size = self._embedding.estimate_embed_batch_size(all_texts)

            ids = []
            metas = []
            for i, c in enumerate(all_chunks):
                chunk_uid = f"{doc_id}::chunk::{i}"
                ids.append(chunk_uid)
                metas.append({
                    "source": source, "doc_id": doc_id, "chunk_id": c["chunk_id"],
                    "chunk_uid": chunk_uid, "page": c.get("page_number"),
                    "parent_chunk_id": c.get("parent_chunk_id", ""),
                    "root_chunk_id": c.get("root_chunk_id", ""),
                    "chunk_level": c.get("chunk_level", 3),
                })

            collection = getattr(vs, "_collection", None)
            if collection is None:
                raise RuntimeError("Chroma collection not available")

            all_embeddings = []
            for i in range(0, len(all_chunks), embed_batch_size):
                batch_texts = all_texts[i:i + embed_batch_size]
                batch_embeddings = embedding.embed_documents(batch_texts)
                all_embeddings.extend(batch_embeddings)
                self._db.update_ingest_progress(job_id, len(all_embeddings))

            for i in range(0, len(all_embeddings), chroma_batch_size):
                batch_ids = ids[i:i + chroma_batch_size]
                batch_embeddings = all_embeddings[i:i + chroma_batch_size]
                batch_metas = metas[i:i + chroma_batch_size]
                collection.add(ids=batch_ids, embeddings=batch_embeddings, metadatas=batch_metas)

            self._db.set_document_vector_indexed(doc_id, True)
            self._invalidate_indexes()

            duration_ms = int((time.perf_counter() - started) * 1000)
            self._db.finish_ingest_job(job_id, "done", total, duration_ms=duration_ms)

            self.logger.info(
                "Ingest done: source=%s chunks=%d parent_chunks=%d duration_ms=%d",
                source, total, len(all_parent_chunks), duration_ms
            )

        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            error_msg = str(exc)
            self._db.finish_ingest_job(job_id, "failed", 0, error_msg, duration_ms)
            self.logger.exception("Ingest failed: source=%s", source)
        finally:
            self._active_jobs.pop(job_id, None)

    def get_job_status(self, job_id: str) -> dict:
        job = self._db.get_ingest_job(job_id)
        if not job:
            return {"ok": False, "message": "任务不存在"}
        is_running = job_id in self._active_jobs and self._active_jobs[job_id].is_alive()
        return {
            "ok": True,
            "job_id": job["job_id"],
            "source": job["source"],
            "status": "running" if is_running else job["status"],
            "total_chunks": job.get("total_chunks", 0),
            "embedded_chunks": job.get("embedded_chunks", 0),
            "chunk_count": job.get("chunk_count", 0),
            "error_message": job.get("error_message", ""),
            "started_at": job.get("started_at", ""),
            "finished_at": job.get("finished_at", ""),
        }

    def get_active_jobs(self) -> list:
        active = []
        for jid, thread in list(self._active_jobs.items()):
            if thread.is_alive():
                status = self.get_job_status(jid)
                if status.get("ok"):
                    active.append(status)
        return active

    def _retrieve_candidates(self, query: str, candidate_k: int) -> Dict[str, Any]:
        """
        多路召回候选文档片段。

        同时执行 BM25 稀疏检索和向量密集检索，合并候选集。
        向量检索失败时自动降级为纯 BM25 模式。

        Args:
            query: 查询文本
            candidate_k: 每路召回的候选数量

        Returns:
            {
                "candidate_map":  {chunk_uid: chunk_info_dict},
                "bm25_raw_scores": {chunk_uid: score},
                "vec_raw_scores":  {chunk_uid: score},
                "vector_available": bool,
                "vector_error": str,
                "timing_ms": {"bm25": int, "vector": int},
            }
        """
        candidate_map: Dict[str, dict] = {}
        bm25_raw_scores: Dict[str, float] = {}
        vec_raw_scores: Dict[str, float] = {}
        timing_ms = {"bm25": 0, "vector": 0}

        bm25_started = time.perf_counter()
        if self._bm25.is_built:
            bm25_results = self._bm25.search(query, candidate_k)
            for chunk, score in bm25_results:
                chunk_id = chunk.get("id")
                if not chunk_id:
                    continue
                metadata = chunk.get("metadata", {})
                bm25_raw_scores[chunk_id] = score
                candidate_map.setdefault(
                    chunk_id,
                    {
                        "id": chunk_id,
                        "doc_id": metadata.get("doc_id"),
                        "source": metadata.get("source", "未知来源"),
                        "chunk_id": metadata.get("chunk_id", -1),
                        "page": metadata.get("page"),
                        "text": chunk.get("text", ""),
                        "parent_chunk_id": metadata.get("parent_chunk_id", ""),
                        "root_chunk_id": metadata.get("root_chunk_id", ""),
                        "chunk_level": metadata.get("chunk_level", 3),
                        "bm25_score": 0.0,
                        "vector_score": 0.0,
                        "hybrid_score": 0.0,
                        "rerank_score": None,
                    },
                )
        timing_ms["bm25"] = int((time.perf_counter() - bm25_started) * 1000)

        vector_available = True
        vector_error = ""
        source_set = self._db.fetch_sources()
        vector_started = time.perf_counter()
        try:
            vs = self._embedding.get_vectorstore()
            vector_results = vs.similarity_search_with_score(query, k=candidate_k)

            parsed_vectors = []
            for doc, distance in vector_results:
                source = doc.metadata.get("source", "")
                if source_set and source and source not in source_set:
                    continue

                chunk_uid = doc.metadata.get("chunk_uid")
                if not chunk_uid:
                    chunk_num = doc.metadata.get("chunk_id", -1)
                    chunk_uid = f"{source}::chunk::{chunk_num}"

                parsed_vectors.append((chunk_uid, doc, distance, source))

            existing_ids = self._db.existing_chunk_ids([item[0] for item in parsed_vectors])
            for chunk_uid, doc, distance, source in parsed_vectors:
                if chunk_uid not in existing_ids:
                    continue

                similarity = 1.0 / (1.0 + float(distance))
                vec_raw_scores[chunk_uid] = similarity
                candidate_map.setdefault(
                    chunk_uid,
                    {
                        "id": chunk_uid,
                        "doc_id": doc.metadata.get("doc_id"),
                        "source": source or "未知来源",
                        "chunk_id": doc.metadata.get("chunk_id", -1),
                        "page": doc.metadata.get("page"),
                        "text": doc.page_content,
                        "parent_chunk_id": doc.metadata.get("parent_chunk_id", ""),
                        "root_chunk_id": doc.metadata.get("root_chunk_id", ""),
                        "chunk_level": doc.metadata.get("chunk_level", 3),
                        "bm25_score": 0.0,
                        "vector_score": 0.0,
                        "hybrid_score": 0.0,
                        "rerank_score": None,
                    },
                )
        except Exception as exc:
            vector_available = False
            vector_error = str(exc)
            self.logger.warning("Vector retrieval fallback to BM25, reason: %s", exc)

        timing_ms["vector"] = int((time.perf_counter() - vector_started) * 1000)
        return {
            "candidate_map": candidate_map,
            "bm25_raw_scores": bm25_raw_scores,
            "vec_raw_scores": vec_raw_scores,
            "vector_available": vector_available,
            "vector_error": vector_error,
            "timing_ms": timing_ms,
        }

    def _compute_hybrid_scores(
        self,
        bm25_raw_scores: Dict[str, float],
        vec_raw_scores: Dict[str, float],
        params: Dict[str, float],
    ) -> Tuple[Dict[str, float], str]:
        """
        计算混合检索分数。

        根据 HYBRID_MODE 配置选择融合策略：
          - "rrf":    使用 RRF (Reciprocal Rank Fusion) 融合，需要两路结果均非空
          - "linear": 使用线性加权融合 (w_bm25 * bm25_norm + w_vec * vec_norm)

        Args:
            bm25_raw_scores: BM25 原始分数 {chunk_uid: score}
            vec_raw_scores:  向量检索原始分数 {chunk_uid: score}
            params: 动态参数 {"w_bm25": float, "w_vec": float}

        Returns:
            (hybrid_scores, fusion_mode) 混合分数字典和使用的融合模式名
        """
        bm25_sorted = sorted(bm25_raw_scores.items(), key=lambda x: x[1], reverse=True)
        vec_sorted = sorted(vec_raw_scores.items(), key=lambda x: x[1], reverse=True)

        if RRF_ENABLED and HYBRID_MODE == "rrf" and bm25_sorted and vec_sorted:
            hybrid_scores = self._retriever.reciprocal_rank_fusion(bm25_sorted, vec_sorted, k=RRF_K)
            return hybrid_scores, "rrf"

        hybrid_scores = self._retriever.linear_fusion(
            bm25_raw_scores,
            vec_raw_scores,
            params["w_bm25"],
            params["w_vec"],
        )
        return hybrid_scores, "linear"

    def query(self, query: str, top_k: int = 5, query_variants: Optional[List[str]] = None) -> dict:
        """
        RAG 检索查询主入口。

        完整流程：
          1. 查询预处理 + 多变体生成（查询改写）
          2. 对每个变体执行多路召回（BM25 + 向量）
          3. 混合融合（RRF / 线性加权 / 多查询加权 RRF）
          4. Cross-Encoder 重排序
          5. Auto-merging 自动合并（L3→L2→L1）
          6. 返回 top_k 结果及详细元信息

        Args:
            query: 用户查询文本
            top_k: 返回结果数量（1-20）
            query_variants: 额外的查询变体列表（可选）

        Returns:
            {
                "ok": bool,
                "results": [...],           # 检索结果列表
                "fusion_mode": str,         # 使用的融合模式
                "query_variants": [...],    # 实际使用的查询变体
                "timing_ms": {...},         # 各阶段耗时
                ...
            }
        """
        started_total = time.perf_counter()
        query = query.strip()

        if not query:
            return {"ok": False, "message": "query 不能为空", "results": []}

        try:
            top_k = int(top_k)
        except Exception:
            top_k = 5
        top_k = max(1, min(top_k, 20))

        documents_count = self._db.count_documents()
        if documents_count <= 0:
            return {"ok": False, "message": "知识库为空，请先上传并入库文档", "results": []}

        if not self._bm25.is_built:
            chunks = self._db.get_leaf_chunks(LEAF_RETRIEVE_LEVEL)
            self._bm25.build(chunks)
        query_id = str(uuid.uuid4())

        variants = []
        seen_variants = set()
        for item in [query] + list(query_variants or []):
            text = str(item or "").strip()
            if not text or text in seen_variants:
                continue
            seen_variants.add(text)
            variants.append(text)

        timing_ms = {"bm25": 0, "vector": 0, "rerank": 0, "auto_merge": 0, "total": 0}
        variant_weights = build_variant_weights(len(variants))
        variant_reports: List[Dict[str, Any]] = []
        aggregate_candidate_map: Dict[str, dict] = {}
        aggregate_rankings: List[List[Tuple[str, float]]] = []
        aggregate_ranking_weights: List[float] = []
        aggregate_vector_available = False
        vector_errors: List[str] = []
        max_candidate_k = 0
        params = self._retriever.dynamic_params(query, top_k)
        per_variant_fusion_mode = "linear"

        for idx, variant_query in enumerate(variants):
            variant_params = self._retriever.dynamic_params(variant_query, top_k)
            max_candidate_k = max(max_candidate_k, variant_params["candidate_k"])

            raw = self._retrieve_candidates(variant_query, variant_params["candidate_k"])
            timing_ms["bm25"] += raw["timing_ms"]["bm25"]
            timing_ms["vector"] += raw["timing_ms"]["vector"]

            if raw["vector_available"]:
                aggregate_vector_available = True
            else:
                variant_params["w_bm25"] = 1.0
                variant_params["w_vec"] = 0.0
                if raw["vector_error"] and raw["vector_error"] not in vector_errors:
                    vector_errors.append(raw["vector_error"])

            hybrid_scores, per_variant_fusion_mode = self._compute_hybrid_scores(
                raw["bm25_raw_scores"],
                raw["vec_raw_scores"],
                variant_params,
            )

            ranking = sorted(hybrid_scores.items(), key=lambda x: x[1], reverse=True)
            if ranking:
                aggregate_rankings.append(ranking)
                aggregate_ranking_weights.append(variant_weights[idx])

            for chunk_uid, item in raw["candidate_map"].items():
                existing = aggregate_candidate_map.get(chunk_uid)
                if existing is None:
                    aggregate_candidate_map[chunk_uid] = dict(item)
                    existing = aggregate_candidate_map[chunk_uid]
                existing["bm25_score"] = max(existing.get("bm25_score", 0.0), raw["bm25_raw_scores"].get(chunk_uid, 0.0))
                existing["vector_score"] = max(existing.get("vector_score", 0.0), raw["vec_raw_scores"].get(chunk_uid, 0.0))

            variant_reports.append(
                {
                    "query": variant_query,
                    "weight": variant_weights[idx],
                    "candidate_count": len(raw["candidate_map"]),
                    "vector_available": raw["vector_available"],
                    "fusion_mode": per_variant_fusion_mode,
                }
            )

        if not aggregate_candidate_map:
            timing_ms["total"] = int((time.perf_counter() - started_total) * 1000)
            return {
                "ok": True,
                "message": "未命中相关片段",
                "query_id": query_id,
                "results": [],
                "weights": {"bm25": params["w_bm25"], "vector": params["w_vec"]},
                "candidate_k": max_candidate_k,
                "candidate_count": 0,
                "reranker_enabled": False,
                "vector_available": aggregate_vector_available,
                "vector_error": "; ".join(vector_errors),
                "timing_ms": timing_ms,
                "documents_count": documents_count,
                "auto_merge_enabled": AUTO_MERGE_ENABLED,
                "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
                "hybrid_mode": HYBRID_MODE,
                "query_variants": variants,
                "rewrite_enabled": len(variants) > 1,
                "variant_reports": variant_reports,
            }

        if len(aggregate_rankings) > 1:
            hybrid_scores = self._retriever.weighted_reciprocal_rank_fusion(
                aggregate_rankings,
                k=RRF_K,
                weights=aggregate_ranking_weights,
            )
            fusion_mode = "multi_query_rrf"
        elif aggregate_rankings:
            hybrid_scores = dict(aggregate_rankings[0])
            fusion_mode = per_variant_fusion_mode
        else:
            hybrid_scores = {}
            fusion_mode = per_variant_fusion_mode

        for chunk_uid, item in aggregate_candidate_map.items():
            item["hybrid_score"] = hybrid_scores.get(chunk_uid, 0.0)

        merged = sorted(aggregate_candidate_map.values(), key=lambda x: x["hybrid_score"], reverse=True)
        rerank_pool = merged[: max(top_k * 3, 10)]

        rerank_started = time.perf_counter()
        reranker_enabled = not self._reranker.is_disabled
        if reranker_enabled and rerank_pool:
            rerank_pool, rerank_error = self._reranker.rerank(query, rerank_pool)
            if rerank_error:
                reranker_enabled = False
        timing_ms["rerank"] = int((time.perf_counter() - rerank_started) * 1000)

        auto_merge_started = time.perf_counter()
        final_results, merge_meta = self._retriever.auto_merge_documents(rerank_pool, top_k)
        timing_ms["auto_merge"] = int((time.perf_counter() - auto_merge_started) * 1000)

        for item in final_results:
            item["citation"] = {
                "doc_id": item.get("doc_id"),
                "source": item.get("source"),
                "chunk_id": item.get("chunk_id"),
                "page": item.get("page"),
            }
            item["scores"] = {
                "bm25": item.get("bm25_score", 0.0),
                "vector": item.get("vector_score", 0.0),
                "hybrid": item.get("hybrid_score", 0.0),
                "rerank": item.get("rerank_score"),
            }

        timing_ms["total"] = int((time.perf_counter() - started_total) * 1000)
        self.logger.info(
            "Query done: query_id=%s top_k=%s candidates=%s docs=%s total_ms=%s vector_ok=%s reranker=%s auto_merge=%s fusion=%s",
            query_id, top_k, len(aggregate_candidate_map), documents_count,
            timing_ms["total"], aggregate_vector_available, reranker_enabled,
            merge_meta.get("auto_merge_applied", False), fusion_mode,
        )

        return {
            "ok": True,
            "message": "检索完成",
            "query_id": query_id,
            "results": final_results,
            "weights": {"bm25": params["w_bm25"], "vector": params["w_vec"]},
            "candidate_k": max_candidate_k,
            "candidate_count": len(aggregate_candidate_map),
            "reranker_enabled": reranker_enabled,
            "vector_available": aggregate_vector_available,
            "vector_error": "; ".join(vector_errors),
            "timing_ms": timing_ms,
            "documents_count": documents_count,
            "auto_merge_enabled": AUTO_MERGE_ENABLED,
            "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
            "auto_merge_applied": merge_meta.get("auto_merge_applied", False),
            "auto_merge_replaced_chunks": merge_meta.get("auto_merge_replaced_chunks", 0),
            "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
            "fusion_mode": fusion_mode,
            "rrf_k": RRF_K if fusion_mode in {"rrf", "multi_query_rrf"} else None,
            "query_variants": variants,
            "rewrite_enabled": len(variants) > 1,
            "variant_reports": variant_reports,
        }


_SERVICE: Optional[RagService] = None


def get_rag_service() -> RagService:
    """获取全局 RagService 单例（懒加载）"""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RagService()
    return _SERVICE
