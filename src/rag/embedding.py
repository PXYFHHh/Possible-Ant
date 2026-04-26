"""
向量嵌入服务模块 —— 模型加载、向量库管理、批次检测

核心功能：
  - 模型路径解析：优先本地缓存 → ModelScope 下载 → HuggingFace 自动下载
  - 向量库管理：Chroma 持久化存储，懒加载
  - 设备检测：自动选择 CUDA / CPU
  - 批次大小检测：适配不同 Chroma 版本的批次限制
"""

import logging
import warnings
from pathlib import Path
from typing import Optional

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

from .config import (
    EMBEDDING_MODEL,
    EMBEDDING_MODELSCOPE_ID,
    USE_MODELSCOPE,
    MODEL_CACHE_DIR,
    CHROMA_DIR,
    DEFAULT_INGEST_BATCH_SIZE,
    DEFAULT_EMBED_BATCH_SIZE,
)

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except Exception:
    from langchain_community.embeddings import HuggingFaceEmbeddings

from langchain_community.vectorstores import Chroma


def _resolve_model_path(model_name: str, modelscope_id: str) -> str:
    """解析模型路径，委托到公共 model_utils 模块"""
    from .model_utils import _resolve_model_path as _do_resolve
    return _do_resolve(model_name, modelscope_id, USE_MODELSCOPE, MODEL_CACHE_DIR)


class EmbeddingService:
    """
    向量嵌入服务。
    
    懒加载策略：模型和向量库在首次使用时才初始化，避免启动时加载大模型。
    嵌入模型使用 normalize_embeddings=True，确保向量归一化后可用余弦相似度。
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger("agent.rag.embedding")
        self._embedding = None
        self._vectorstore = None
        self._device = self._detect_device()
    
    def _detect_device(self) -> str:
        """检测可用设备：优先 CUDA，回退 CPU"""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"
    
    def get_embedding(self):
        """获取嵌入模型实例（懒加载），首次调用时加载模型到内存"""
        if self._embedding is None:
            model_path = _resolve_model_path(EMBEDDING_MODEL, EMBEDDING_MODELSCOPE_ID)
            self._embedding = HuggingFaceEmbeddings(
                model_name=model_path,
                model_kwargs={"device": self._device},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embedding
    
    def get_vectorstore(self) -> Chroma:
        """获取 Chroma 向量库实例（懒加载），首次调用时创建或加载持久化数据"""
        if self._vectorstore is not None:
            return self._vectorstore
        
        self._vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=self.get_embedding(),
        )
        return self._vectorstore
    
    def reset_vectorstore(self) -> None:
        self._vectorstore = None

    def estimate_embed_batch_size(self, texts: list) -> int:
        """
        根据可用系统内存和文本总量，动态估算安全的 embed_documents 批次大小。

        策略：
          1. 尝试用 psutil 获取当前可用内存，无法获取时回退到保守默认值
          2. 预留 30% 可用内存用于嵌入计算
          3. 按文本平均长度 × 60 字节估算单条嵌入峰值内存
          4. 返回 max(32, min(2000, 可用内存/单条开销))
        """
        try:
            import psutil
            avail = psutil.virtual_memory().available
        except Exception:
            return 200

        usable = int(avail * 0.30)
        avg_chars = sum(len(t) for t in texts) / max(len(texts), 1)
        per_chunk_mem = int(avg_chars * 60)

        if per_chunk_mem <= 0:
            return 200

        dynamic = max(32, min(2000, usable // per_chunk_mem))
        if total := len(texts):
            dynamic = min(dynamic, total)
        self.logger.debug(
            "embed batch estimate: avail=%dMB usable=%dMB per_chunk=%dB calc=%d texts=%d",
            avail // 1048576, usable // 1048576, per_chunk_mem, dynamic, total,
        )
        return dynamic

    def _detect_chroma_batch_limit(self) -> int:
        """
        检测 Chroma 当前版本的最大批次限制。
        
        Chroma 0.4.x 限制单次写入 5461 条，0.5+ 版本可能更高。
        通过尝试写入测试批次来动态检测。
        """

    def detect_batch_size(self, vs: Chroma) -> int:
        """
        检测 Chroma 允许的最大批次大小。

        从大到小尝试写入测试数据，找到不报错的最大值。
        """
        collection = getattr(vs, "_collection", None)
        client = getattr(vs, "_client", None)
        candidates = []

        for obj in (collection, client):
            if obj is None:
                continue
            for attr in ("_batch_size", "batch_size"):
                if hasattr(obj, attr):
                    val = getattr(obj, attr)
                    if isinstance(val, int) and val > 0:
                        candidates.append(val)
        
        return max(candidates) if candidates else DEFAULT_INGEST_BATCH_SIZE
