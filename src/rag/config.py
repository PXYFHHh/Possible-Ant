import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
FILES_DIR = BASE_DIR / "files"
RAG_DIR = BASE_DIR / "src" / "rag"
CHROMA_DIR = RAG_DIR / "chroma_db"
LEGACY_METADATA_PATH = RAG_DIR / "rag_metadata.json"
MODEL_CACHE_DIR = RAG_DIR / "model_cache"

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
EMBEDDING_MODELSCOPE_ID = os.getenv("RAG_EMBEDDING_MODELSCOPE_ID", EMBEDDING_MODEL)
RERANK_MODELSCOPE_ID = os.getenv("RAG_RERANK_MODELSCOPE_ID", RERANK_MODEL)
USE_MODELSCOPE = os.getenv("RAG_USE_MODELSCOPE", "1") != "0"

DEFAULT_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "900"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
DEFAULT_INGEST_BATCH_SIZE = int(os.getenv("RAG_INGEST_BATCH_SIZE", "1000"))
DEFAULT_EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", "32"))
RAG_DB_PATH = Path(os.getenv("RAG_DB_PATH", str(RAG_DIR / "rag_registry.sqlite3")))
RAG_LOG_PATH = Path(os.getenv("RAG_LOG_PATH", str(RAG_DIR / "rag_service.log")))
RAG_LOG_LEVEL = os.getenv("RAG_LOG_LEVEL", "INFO").upper()
RERANK_RETRY_COOLDOWN_SECONDS = int(os.getenv("RAG_RERANK_RETRY_COOLDOWN_SECONDS", "300"))

LEVEL_1_CHUNK_SIZE = int(os.getenv("RAG_LEVEL_1_CHUNK_SIZE", "1200"))
LEVEL_1_CHUNK_OVERLAP = int(os.getenv("RAG_LEVEL_1_CHUNK_OVERLAP", "240"))
LEVEL_2_CHUNK_SIZE = int(os.getenv("RAG_LEVEL_2_CHUNK_SIZE", "600"))
LEVEL_2_CHUNK_OVERLAP = int(os.getenv("RAG_LEVEL_2_CHUNK_OVERLAP", "120"))
LEVEL_3_CHUNK_SIZE = int(os.getenv("RAG_LEVEL_3_CHUNK_SIZE", "300"))
LEVEL_3_CHUNK_OVERLAP = int(os.getenv("RAG_LEVEL_3_CHUNK_OVERLAP", "60"))

AUTO_MERGE_ENABLED = os.getenv("RAG_AUTO_MERGE_ENABLED", "true").lower() != "false"
AUTO_MERGE_THRESHOLD = int(os.getenv("RAG_AUTO_MERGE_THRESHOLD", "2"))
LEAF_RETRIEVE_LEVEL = int(os.getenv("RAG_LEAF_RETRIEVE_LEVEL", "3"))

RRF_ENABLED = os.getenv("RAG_RRF_ENABLED", "true").lower() != "false"
RRF_K = int(os.getenv("RAG_RRF_K", "60"))
HYBRID_MODE = os.getenv("RAG_HYBRID_MODE", "rrf")

CACHE_ENABLED = os.getenv("RAG_CACHE_ENABLED", "true").lower() != "false"
CACHE_MAX_SIZE = int(os.getenv("RAG_CACHE_MAX_SIZE", "5000"))
CACHE_TTL_SECONDS = int(os.getenv("RAG_CACHE_TTL_SECONDS", "3600"))
BM25_PERSIST_ENABLED = os.getenv("RAG_BM25_PERSIST_ENABLED", "true").lower() != "false"
BM25_STATE_PATH = Path(os.getenv("RAG_BM25_STATE_PATH", str(RAG_DIR / "bm25_state.json")))
