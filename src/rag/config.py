"""
RAG 配置模块 —— 所有可调参数的集中管理

每个配置项均支持通过环境变量覆盖，格式为 RAG_<大写变量名>。
未设置环境变量时使用代码中的默认值。
"""

import os
from pathlib import Path

# ==================== 目录路径 ====================

BASE_DIR = Path(__file__).resolve().parents[2]       # 项目根目录
FILES_DIR = BASE_DIR / "files"                        # 上传文件存储目录
RAG_DIR = BASE_DIR / "src" / "rag"                    # RAG 模块目录
CHROMA_DIR = RAG_DIR / "chroma_db"                    # Chroma 向量库持久化目录
LEGACY_METADATA_PATH = RAG_DIR / "rag_metadata.json"  # 旧版元数据文件（已弃用）
MODEL_CACHE_DIR = RAG_DIR / "model_cache"             # 模型本地缓存目录

# ==================== 模型配置 ====================

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"            # 嵌入模型名称（中文小型模型）
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"              # 重排模型名称（多语言 Cross-Encoder）
EMBEDDING_MODELSCOPE_ID = os.getenv("RAG_EMBEDDING_MODELSCOPE_ID", EMBEDDING_MODEL)  # ModelScope 嵌入模型 ID
RERANK_MODELSCOPE_ID = os.getenv("RAG_RERANK_MODELSCOPE_ID", RERANK_MODEL)          # ModelScope 重排模型 ID
USE_MODELSCOPE = os.getenv("RAG_USE_MODELSCOPE", "1") != "0"                        # 是否使用 ModelScope 下载模型

# ==================== 分块参数（旧版兼容） ====================

DEFAULT_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "900"))       # 默认分块大小（字符数）
DEFAULT_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120")) # 默认分块重叠（字符数）

# ==================== 入库参数 ====================

DEFAULT_INGEST_BATCH_SIZE = int(os.getenv("RAG_INGEST_BATCH_SIZE", "1000"))  # 向量化入库批次大小
DEFAULT_EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", "32"))      # 嵌入计算批次大小

# ==================== 日志与数据库 ====================

RAG_DB_PATH = Path(os.getenv("RAG_DB_PATH", str(RAG_DIR / "rag_registry.sqlite3")))  # SQLite 数据库路径
RAG_LOG_PATH = Path(os.getenv("RAG_LOG_PATH", str(RAG_DIR / "rag_service.log")))     # 日志文件路径
RAG_LOG_LEVEL = os.getenv("RAG_LOG_LEVEL", "INFO").upper()                            # 日志级别
RERANK_RETRY_COOLDOWN_SECONDS = int(os.getenv("RAG_RERANK_RETRY_COOLDOWN_SECONDS", "300"))  # 重排失败冷却时间（秒）

# ==================== 三层分块参数 ====================
# L1 (大块) → L2 (中块) → L3 (小块)，每层独立配置大小和重叠

LEVEL_1_CHUNK_SIZE = int(os.getenv("RAG_LEVEL_1_CHUNK_SIZE", "1200"))       # L1 大块大小
LEVEL_1_CHUNK_OVERLAP = int(os.getenv("RAG_LEVEL_1_CHUNK_OVERLAP", "120"))  # L1 大块重叠
LEVEL_2_CHUNK_SIZE = int(os.getenv("RAG_LEVEL_2_CHUNK_SIZE", "600"))        # L2 中块大小
LEVEL_2_CHUNK_OVERLAP = int(os.getenv("RAG_LEVEL_2_CHUNK_OVERLAP", "60"))   # L2 中块重叠
LEVEL_3_CHUNK_SIZE = int(os.getenv("RAG_LEVEL_3_CHUNK_SIZE", "300"))        # L3 小块大小（叶节点，用于向量检索）
LEVEL_3_CHUNK_OVERLAP = int(os.getenv("RAG_LEVEL_3_CHUNK_OVERLAP", "30"))   # L3 小块重叠

# ==================== Auto-merging 配置 ====================

AUTO_MERGE_ENABLED = os.getenv("RAG_AUTO_MERGE_ENABLED", "true").lower() != "false"   # 是否启用自动合并
AUTO_MERGE_THRESHOLD = int(os.getenv("RAG_AUTO_MERGE_THRESHOLD", "2"))                 # 触发合并的最小子块命中数
LEAF_RETRIEVE_LEVEL = int(os.getenv("RAG_LEAF_RETRIEVE_LEVEL", "3"))                   # 叶节点检索层级（默认 L3）

# ==================== 混合检索配置 ====================

RRF_ENABLED = os.getenv("RAG_RRF_ENABLED", "true").lower() != "false"  # 是否启用 RRF 融合
RRF_K = int(os.getenv("RAG_RRF_K", "60"))                              # RRF 平滑常数（越大排名差异影响越小）
HYBRID_MODE = os.getenv("RAG_HYBRID_MODE", "rrf")                      # 融合模式：rrf | linear

# ==================== 缓存配置 ====================

CACHE_ENABLED = os.getenv("RAG_CACHE_ENABLED", "true").lower() != "false"  # 是否启用父块缓存
CACHE_MAX_SIZE = int(os.getenv("RAG_CACHE_MAX_SIZE", "5000"))              # LRU 缓存最大条目数
CACHE_TTL_SECONDS = int(os.getenv("RAG_CACHE_TTL_SECONDS", "3600"))       # 缓存过期时间（秒）

# ==================== BM25 配置 ====================

BM25_PERSIST_ENABLED = os.getenv("RAG_BM25_PERSIST_ENABLED", "true").lower() != "false"  # 是否持久化 BM25 索引状态
BM25_STATE_PATH = Path(os.getenv("RAG_BM25_STATE_PATH", str(RAG_DIR / "bm25_state.json")))  # BM25 状态文件路径

# ==================== 配置校验 ====================

_REQUIRED_ENV_VARS = [
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
]

_OPTIONAL_ENV_VARS_WITH_DEFAULTS = {
    "RAG_EMBEDDING_MODEL": EMBEDDING_MODEL,
    "RAG_EMBEDDING_MODELSCOPE_ID": EMBEDDING_MODEL,
    "RAG_RERANK_MODELSCOPE_ID": RERANK_MODEL,
    "RAG_INGEST_BATCH_SIZE": "1000",
    "RAG_EMBED_BATCH_SIZE": "32",
    "RAG_LEVEL_1_CHUNK_SIZE": "1200",
    "RAG_LEVEL_1_CHUNK_OVERLAP": "120",
    "RAG_LEVEL_2_CHUNK_SIZE": "600",
    "RAG_LEVEL_2_CHUNK_OVERLAP": "60",
    "RAG_LEVEL_3_CHUNK_SIZE": "300",
    "RAG_LEVEL_3_CHUNK_OVERLAP": "30",
    "RAG_AUTO_MERGE_THRESHOLD": "2",
    "RAG_RRF_K": "60",
    "RAG_RRF_ENABLED": "true",
    "RAG_HYBRID_MODE": "rrf",
    "RAG_CACHE_ENABLED": "true",
    "RAG_CACHE_MAX_SIZE": "5000",
    "RAG_CACHE_TTL_SECONDS": "3600",
    "RAG_RERANK_RETRY_COOLDOWN_SECONDS": "300",
    "RAG_DB_PATH": str(RAG_DIR / "rag_registry.sqlite3"),
    "RAG_LOG_PATH": str(RAG_DIR / "rag_service.log"),
    "RAG_LOG_LEVEL": "INFO",
    "RAG_BM25_PERSIST_ENABLED": "true",
    "RAG_BM25_STATE_PATH": str(RAG_DIR / "bm25_state.json"),
}


def validate_rag_config() -> list[str]:
    """
    校验 RAG 相关环境变量配置，返回所有警告信息列表。

    检查项目：
      1. 核心 LLM 环境变量是否已设置
      2. RAG 可选变量中与非默认值差异过大的值（如极端的 chunk_size）
      3. 目录是否已存在、是否可访问
      4. 数值型参数的合法性

    Returns:
        警告信息列表，为空时表示所有配置正常
    """
    import os as _os
    import dotenv

    dotenv.load_dotenv()

    warnings: list[str] = []

    for var in _REQUIRED_ENV_VARS:
        if not _os.getenv(var, "").strip():
            warnings.append(f"缺少环境变量 {var}，LLM 将无法初始化")

    int_vars = {
        "RAG_INGEST_BATCH_SIZE": int(os.getenv("RAG_INGEST_BATCH_SIZE", "1000")),
        "RAG_EMBED_BATCH_SIZE": int(os.getenv("RAG_EMBED_BATCH_SIZE", "32")),
        "RAG_LEVEL_1_CHUNK_SIZE": LEVEL_1_CHUNK_SIZE,
        "RAG_LEVEL_1_CHUNK_OVERLAP": LEVEL_1_CHUNK_OVERLAP,
        "RAG_LEVEL_2_CHUNK_SIZE": LEVEL_2_CHUNK_SIZE,
        "RAG_LEVEL_2_CHUNK_OVERLAP": LEVEL_2_CHUNK_OVERLAP,
        "RAG_LEVEL_3_CHUNK_SIZE": LEVEL_3_CHUNK_SIZE,
        "RAG_LEVEL_3_CHUNK_OVERLAP": LEVEL_3_CHUNK_OVERLAP,
        "RAG_AUTO_MERGE_THRESHOLD": AUTO_MERGE_THRESHOLD,
        "RAG_RRF_K": RRF_K,
        "RAG_CACHE_MAX_SIZE": CACHE_MAX_SIZE,
        "RAG_CACHE_TTL_SECONDS": CACHE_TTL_SECONDS,
        "RAG_RERANK_RETRY_COOLDOWN_SECONDS": RERANK_RETRY_COOLDOWN_SECONDS,
    }

    for var_name, value in int_vars.items():
        if value < 1:
            warnings.append(f"{var_name}={value} 值非法，应为正整数")

    if LEVEL_3_CHUNK_OVERLAP >= LEVEL_3_CHUNK_SIZE:
        warnings.append(
            f"RAG_LEVEL_3_CHUNK_OVERLAP({LEVEL_3_CHUNK_OVERLAP}) >= "
            f"RAG_LEVEL_3_CHUNK_SIZE({LEVEL_3_CHUNK_SIZE})，overlap 不应大于 chunk_size"
        )

    hybird_mode = os.getenv("RAG_HYBRID_MODE", "rrf").lower()
    if hybird_mode not in ("rrf", "linear"):
        warnings.append(f"RAG_HYBRID_MODE={hybird_mode} 不支持，应为 rrf 或 linear")

    files_path = _os.getenv("RAG_FILES_DIR", str(FILES_DIR))
    if not _os.path.exists(files_path):
        warnings.append(f"RAG 文档目录不存在: {files_path}")

    return warnings
