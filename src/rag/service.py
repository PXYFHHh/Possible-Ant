import json
import os
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except Exception:
    from langchain_community.embeddings import HuggingFaceEmbeddings


warnings.filterwarnings(
    "ignore",
    message=r"Accessing `__path__` from `\.models\..*",
    category=FutureWarning,
)


BASE_DIR = Path(__file__).resolve().parents[2]
FILES_DIR = BASE_DIR / "files"
RAG_DIR = BASE_DIR / "src" / "rag"
CHROMA_DIR = RAG_DIR / "chroma_db"
METADATA_PATH = RAG_DIR / "rag_metadata.json"
MODEL_CACHE_DIR = RAG_DIR / "model_cache"

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
EMBEDDING_MODELSCOPE_ID = os.getenv("RAG_EMBEDDING_MODELSCOPE_ID", EMBEDDING_MODEL)
RERANK_MODELSCOPE_ID = os.getenv("RAG_RERANK_MODELSCOPE_ID", RERANK_MODEL)
USE_MODELSCOPE = os.getenv("RAG_USE_MODELSCOPE", "1") != "0"


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text.lower())


def _download_modelscope_model(model_id: str) -> str:
    from modelscope import snapshot_download

    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return snapshot_download(model_id=model_id, cache_dir=str(MODEL_CACHE_DIR))


def _resolve_model_path(default_model: str, modelscope_model_id: str) -> str:
    if Path(default_model).exists():
        return default_model

    if USE_MODELSCOPE:
        return _download_modelscope_model(modelscope_model_id)

    return default_model


class RagService:
    def __init__(self):
        self._ensure_dirs()
        self.embedding = None
        self.vectorstore = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=900,
            chunk_overlap=120,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        )

        self._metadata = self._load_metadata()
        self._bm25 = None
        self._bm25_chunks: List[dict] = []
        self._reranker = None
        self._reranker_disabled = False

    def _get_vectorstore(self) -> Chroma:
        if self.vectorstore is not None:
            return self.vectorstore

        try:
            embed_model = _resolve_model_path(EMBEDDING_MODEL, EMBEDDING_MODELSCOPE_ID)
            model_kwargs = {"local_files_only": Path(embed_model).exists()}
            self.embedding = HuggingFaceEmbeddings(
                model_name=embed_model,
                model_kwargs=model_kwargs,
                encode_kwargs={"normalize_embeddings": True},
            )
            self.vectorstore = Chroma(
                collection_name="agent_knowledge",
                persist_directory=str(CHROMA_DIR),
                embedding_function=self.embedding,
            )
            return self.vectorstore
        except ModuleNotFoundError as exc:
            if "torchvision" in str(exc):
                raise RuntimeError(
                    "缺少 torchvision 依赖，无法初始化向量模型。"
                    "请在 conda 环境中安装: pip install torchvision"
                ) from exc
            raise RuntimeError(f"向量模型初始化失败: {exc}") from exc
        except OSError as exc:
            raise RuntimeError(
                "向量模型加载失败。当前默认通过 ModelScope 下载模型，"
                f"请检查网络或模型ID: {EMBEDDING_MODELSCOPE_ID}。"
                f"原始错误: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"向量模型初始化失败: {exc}") from exc

    def _ensure_dirs(self) -> None:
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        RAG_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _load_metadata(self) -> Dict:
        if METADATA_PATH.exists():
            try:
                return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"documents": {}}

    def _save_metadata(self) -> None:
        METADATA_PATH.write_text(
            json.dumps(self._metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _invalidate_indexes(self) -> None:
        self._bm25 = None
        self._bm25_chunks = []

    def _build_bm25(self) -> None:
        if self._bm25 is not None:
            return

        all_chunks: List[dict] = []
        for _, doc_item in self._metadata.get("documents", {}).items():
            all_chunks.extend(doc_item.get("chunks", []))

        self._bm25_chunks = all_chunks
        tokenized = [_tokenize(item.get("text", "")) for item in all_chunks]
        if tokenized:
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None

    def _load_document(self, file_path: Path):
        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            return TextLoader(str(file_path), encoding="utf-8").load()
        if suffix == ".pdf":
            return PyPDFLoader(str(file_path)).load()
        if suffix == ".docx":
            return Docx2txtLoader(str(file_path)).load()
        raise ValueError("仅支持 txt/md/pdf/docx 文档")

    def list_documents(self) -> List[dict]:
        docs = self._metadata.get("documents", {})
        result = []
        for name, item in docs.items():
            result.append(
                {
                    "source": name,
                    "chunk_count": item.get("chunk_count", 0),
                    "updated_at": item.get("updated_at", ""),
                }
            )
        return sorted(result, key=lambda x: x["source"])

    def delete_document(self, source: str) -> dict:
        source = source.strip()
        if not source:
            return {"ok": False, "message": "source 不能为空"}

        doc_info = self._metadata.get("documents", {}).get(source)
        if not doc_info:
            return {"ok": False, "message": f"未找到文档: {source}"}

        ids = [item.get("id") for item in doc_info.get("chunks", []) if item.get("id")]
        if ids:
            try:
                vs = self._get_vectorstore()
                vs.delete(ids=ids)
                if hasattr(vs, "persist"):
                    vs.persist()
            except Exception:
                pass

        self._metadata["documents"].pop(source, None)
        self._save_metadata()
        self._invalidate_indexes()
        return {"ok": True, "message": f"已删除文档: {source}"}

    def ingest_file(self, filename: str) -> dict:
        filename = filename.strip()
        file_path = (FILES_DIR / filename).resolve()

        if not file_path.exists() or not file_path.is_file():
            return {"ok": False, "message": f"文件不存在: {filename}"}

        if not str(file_path).startswith(str(FILES_DIR.resolve())):
            return {"ok": False, "message": "仅允许上传 files 目录中的文件"}

        try:
            self.delete_document(filename)
            docs = self._load_document(file_path)
            chunks = self.text_splitter.split_documents(docs)

            if not chunks:
                return {"ok": False, "message": "文档切片结果为空"}

            ids = []
            chunk_items = []
            for idx, chunk in enumerate(chunks):
                chunk_uid = f"{filename}::chunk::{idx}"
                chunk.metadata["source"] = filename
                chunk.metadata["chunk_id"] = idx
                chunk.metadata["chunk_uid"] = chunk_uid
                ids.append(chunk_uid)
                chunk_items.append(
                    {
                        "id": chunk_uid,
                        "text": chunk.page_content,
                        "metadata": {
                            "source": filename,
                            "chunk_id": idx,
                        },
                    }
                )

            vs = self._get_vectorstore()
            vs.add_documents(chunks, ids=ids)
            if hasattr(vs, "persist"):
                vs.persist()

            self._metadata.setdefault("documents", {})[filename] = {
                "chunk_count": len(chunks),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "chunks": chunk_items,
            }
            self._save_metadata()
            self._invalidate_indexes()

            return {
                "ok": True,
                "message": f"文档入库成功: {filename}",
                "chunk_count": len(chunks),
            }
        except Exception as exc:
            return {"ok": False, "message": f"入库失败: {exc}"}

    def _dynamic_params(self, query: str, top_k: int) -> dict:
        q_len = len(query.strip())
        q_tokens = len(_tokenize(query))

        if q_len <= 12 or q_tokens <= 6:
            w_bm25, w_vec = 0.62, 0.38
        elif q_len >= 40 or q_tokens >= 18:
            w_bm25, w_vec = 0.35, 0.65
        else:
            w_bm25, w_vec = 0.5, 0.5

        base_k = max(top_k * 4, 12)
        if q_len <= 10:
            base_k += 6
        elif q_len >= 60:
            base_k += 10
        base_k = min(base_k, 40)

        return {"w_bm25": w_bm25, "w_vec": w_vec, "candidate_k": base_k}

    def _normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        if not scores:
            return {}
        vals = list(scores.values())
        min_v = min(vals)
        max_v = max(vals)
        if max_v - min_v < 1e-12:
            return {k: 1.0 for k in scores}
        return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}

    def _get_reranker(self) -> Optional[object]:
        if self._reranker_disabled:
            return None
        if self._reranker is not None:
            return self._reranker

        try:
            from sentence_transformers import CrossEncoder

            rerank_model = _resolve_model_path(RERANK_MODEL, RERANK_MODELSCOPE_ID)
            self._reranker = CrossEncoder(
                rerank_model,
                local_files_only=Path(rerank_model).exists(),
            )
            return self._reranker
        except Exception:
            self._reranker_disabled = True
            return None

    def query(self, query: str, top_k: int = 5) -> dict:
        query = query.strip()
        if not query:
            return {"ok": False, "message": "query 不能为空", "results": []}

        docs = self._metadata.get("documents", {})
        if not docs:
            return {"ok": False, "message": "知识库为空，请先上传并入库文档", "results": []}

        self._build_bm25()
        params = self._dynamic_params(query, top_k)
        candidate_k = params["candidate_k"]

        candidate_map: Dict[str, dict] = {}
        bm25_raw_scores: Dict[str, float] = {}
        vec_raw_scores: Dict[str, float] = {}

        if self._bm25 is not None and self._bm25_chunks:
            q_tokens = _tokenize(query)
            score_arr = self._bm25.get_scores(q_tokens)
            top_idx = sorted(
                range(len(score_arr)),
                key=lambda i: score_arr[i],
                reverse=True,
            )[:candidate_k]

            for idx in top_idx:
                chunk = self._bm25_chunks[idx]
                chunk_id = chunk.get("id")
                if not chunk_id:
                    continue
                bm25_score = float(score_arr[idx])
                bm25_raw_scores[chunk_id] = bm25_score
                candidate_map.setdefault(
                    chunk_id,
                    {
                        "id": chunk_id,
                        "source": chunk.get("metadata", {}).get("source", "未知来源"),
                        "chunk_id": chunk.get("metadata", {}).get("chunk_id", -1),
                        "text": chunk.get("text", ""),
                        "bm25_score": 0.0,
                        "vector_score": 0.0,
                        "hybrid_score": 0.0,
                        "rerank_score": None,
                    },
                )

        vector_available = True
        try:
            vs = self._get_vectorstore()
            vector_results = vs.similarity_search_with_score(query, k=candidate_k)
            for doc, distance in vector_results:
                chunk_uid = doc.metadata.get("chunk_uid")
                if not chunk_uid:
                    source = doc.metadata.get("source", "")
                    chunk_num = doc.metadata.get("chunk_id", -1)
                    chunk_uid = f"{source}::chunk::{chunk_num}"

                similarity = 1.0 / (1.0 + float(distance))
                vec_raw_scores[chunk_uid] = similarity

                candidate_map.setdefault(
                    chunk_uid,
                    {
                        "id": chunk_uid,
                        "source": doc.metadata.get("source", "未知来源"),
                        "chunk_id": doc.metadata.get("chunk_id", -1),
                        "text": doc.page_content,
                        "bm25_score": 0.0,
                        "vector_score": 0.0,
                        "hybrid_score": 0.0,
                        "rerank_score": None,
                    },
                )
        except Exception:
            vector_available = False
            params["w_bm25"] = 1.0
            params["w_vec"] = 0.0

        bm25_norm = self._normalize_scores(bm25_raw_scores)
        vec_norm = self._normalize_scores(vec_raw_scores)

        for chunk_uid, item in candidate_map.items():
            b = bm25_norm.get(chunk_uid, 0.0)
            v = vec_norm.get(chunk_uid, 0.0)
            item["bm25_score"] = b
            item["vector_score"] = v
            item["hybrid_score"] = params["w_bm25"] * b + params["w_vec"] * v

        merged = sorted(candidate_map.values(), key=lambda x: x["hybrid_score"], reverse=True)
        rerank_pool = merged[: max(top_k * 3, 10)]

        reranker = self._get_reranker()
        if reranker and rerank_pool:
            pairs = [[query, item["text"]] for item in rerank_pool]
            rerank_scores = reranker.predict(pairs)
            for item, score in zip(rerank_pool, rerank_scores):
                item["rerank_score"] = float(score)
            rerank_pool.sort(key=lambda x: x["rerank_score"], reverse=True)

        final_results = rerank_pool[:top_k]

        return {
            "ok": True,
            "message": "检索完成",
            "results": final_results,
            "weights": {
                "bm25": params["w_bm25"],
                "vector": params["w_vec"],
            },
            "candidate_k": candidate_k,
            "reranker_enabled": reranker is not None,
            "vector_available": vector_available,
        }


_SERVICE: Optional[RagService] = None


def get_rag_service() -> RagService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RagService()
    return _SERVICE
