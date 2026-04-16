import hashlib
import json
import logging
import os
import threading
import time
import uuid
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """RAG 统一服务：入库、查询、删除、健康检查。支持三层分块和Auto-merging。"""

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
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        RAG_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _build_doc_id(self, source: str, content_hash: str) -> str:
        seed = f"{source}::{content_hash}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

    def _invalidate_indexes(self) -> None:
        self._bm25.invalidate()
        
        if self._parent_chunk_cache:
            self._parent_chunk_cache.clear()

    def health_status(self, job_limit: int = 5, probe_models: bool = False) -> dict:
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
        return self._delete_document_internal(source=source, ignore_missing=False)

    def _delete_document_internal(self, source: str, ignore_missing: bool = False) -> dict:
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
            batch_size = self._embedding.detect_batch_size(vs)
            embedded = 0

            for i in range(0, len(all_chunks), batch_size):
                batch = all_chunks[i:i + batch_size]
                texts = [c["text"] for c in batch]
                metas = []
                for j, c in enumerate(batch):
                    chunk_uid = f"{doc_id}::chunk::{i + j}"
                    metas.append({
                        "source": source, "doc_id": doc_id, "chunk_id": c["chunk_id"],
                        "chunk_uid": chunk_uid, "page": c.get("page_number"),
                        "parent_chunk_id": c.get("parent_chunk_id", ""),
                        "root_chunk_id": c.get("root_chunk_id", ""),
                        "chunk_level": c.get("chunk_level", 3),
                    })
                vs.add_texts(texts=texts, metadatas=metas)
                embedded += len(batch)
                self._db.update_ingest_progress(job_id, embedded)

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

    def query(self, query: str, top_k: int = 5) -> dict:
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

        params = self._retriever.dynamic_params(query, top_k)
        candidate_k = params["candidate_k"]
        query_id = str(uuid.uuid4())

        candidate_map: Dict[str, dict] = {}
        bm25_raw_scores: Dict[str, float] = {}
        vec_raw_scores: Dict[str, float] = {}
        timing_ms = {"bm25": 0, "vector": 0, "rerank": 0, "auto_merge": 0, "total": 0}

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
            params["w_bm25"] = 1.0
            params["w_vec"] = 0.0
            self.logger.warning("Vector retrieval fallback to BM25, reason: %s", exc)
        timing_ms["vector"] = int((time.perf_counter() - vector_started) * 1000)

        if not candidate_map:
            timing_ms["total"] = int((time.perf_counter() - started_total) * 1000)
            return {
                "ok": True,
                "message": "未命中相关片段",
                "query_id": query_id,
                "results": [],
                "weights": {"bm25": params["w_bm25"], "vector": params["w_vec"]},
                "candidate_k": candidate_k,
                "candidate_count": 0,
                "reranker_enabled": False,
                "vector_available": vector_available,
                "vector_error": vector_error,
                "timing_ms": timing_ms,
                "documents_count": documents_count,
                "auto_merge_enabled": AUTO_MERGE_ENABLED,
                "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
                "hybrid_mode": HYBRID_MODE,
            }

        bm25_sorted = sorted(bm25_raw_scores.items(), key=lambda x: x[1], reverse=True)
        vec_sorted = sorted(vec_raw_scores.items(), key=lambda x: x[1], reverse=True)

        if RRF_ENABLED and HYBRID_MODE == "rrf" and bm25_sorted and vec_sorted:
            hybrid_scores = self._retriever.reciprocal_rank_fusion(
                bm25_sorted, vec_sorted, k=RRF_K
            )
            fusion_mode = "rrf"
        else:
            hybrid_scores = self._retriever.linear_fusion(
                bm25_raw_scores, vec_raw_scores,
                params["w_bm25"], params["w_vec"]
            )
            fusion_mode = "linear"

        for chunk_uid, item in candidate_map.items():
            item["bm25_score"] = bm25_raw_scores.get(chunk_uid, 0.0)
            item["vector_score"] = vec_raw_scores.get(chunk_uid, 0.0)
            item["hybrid_score"] = hybrid_scores.get(chunk_uid, 0.0)

        merged = sorted(candidate_map.values(), key=lambda x: x["hybrid_score"], reverse=True)
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
            query_id, top_k, len(candidate_map), documents_count,
            timing_ms["total"], vector_available, reranker_enabled,
            merge_meta.get("auto_merge_applied", False), fusion_mode,
        )

        return {
            "ok": True,
            "message": "检索完成",
            "query_id": query_id,
            "results": final_results,
            "weights": {"bm25": params["w_bm25"], "vector": params["w_vec"]},
            "candidate_k": candidate_k,
            "candidate_count": len(candidate_map),
            "reranker_enabled": reranker_enabled,
            "vector_available": vector_available,
            "vector_error": vector_error,
            "timing_ms": timing_ms,
            "documents_count": documents_count,
            "auto_merge_enabled": AUTO_MERGE_ENABLED,
            "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
            "auto_merge_applied": merge_meta.get("auto_merge_applied", False),
            "auto_merge_replaced_chunks": merge_meta.get("auto_merge_replaced_chunks", 0),
            "leaf_retrieve_level": LEAF_RETRIEVE_LEVEL,
            "fusion_mode": fusion_mode,
            "rrf_k": RRF_K if fusion_mode == "rrf" else None,
        }


_SERVICE: Optional[RagService] = None


def get_rag_service() -> RagService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RagService()
    return _SERVICE
