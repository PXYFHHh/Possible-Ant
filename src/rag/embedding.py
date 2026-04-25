"""
向量嵌入服务模块 —— 模型加载、向量库管理、批次检测

核心功能：
  - 模型路径解析：优先本地缓存 → ModelScope 下载 → HuggingFace 自动下载
  - 向量库管理：Chroma 持久化存储，懒加载
  - 设备检测：自动选择 CUDA / CPU
  - 批次大小检测：适配不同 Chroma 版本的批次限制
"""

import logging
import os
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
    """
    解析模型路径，按优先级查找：
      1. 本地绝对路径直接使用
      2. MODEL_CACHE_DIR 下的缓存目录
      3. ModelScope 缓存目录
      4. ModelScope 下载（需要联网）
      5. 回退到原始模型名（由 HuggingFace 自动下载）
    """
    if Path(model_name).exists():
        return model_name

    if USE_MODELSCOPE:
        cache_dir = MODEL_CACHE_DIR / model_name.replace("/", "_")
        if cache_dir.exists() and cache_dir.is_dir():
            resolved = _find_model_in_dir(cache_dir, model_name)
            if resolved:
                return resolved

        modelscope_cache_name = modelscope_id.replace(".", "___")
        modelscope_cache_dir = MODEL_CACHE_DIR / modelscope_cache_name.replace("/", os.sep)
        if modelscope_cache_dir.exists():
            resolved = _find_model_in_dir(modelscope_cache_dir, model_name)
            if resolved:
                return resolved

        parent_dir = MODEL_CACHE_DIR / model_name.split("/")[0]
        if parent_dir.exists():
            parts = model_name.split("/")
            if len(parts) == 2:
                org, model = parts
                model_normalized = model.replace(".", "___")
                for child in parent_dir.iterdir():
                    if child.is_dir():
                        resolved = _find_model_in_dir(child, model_name)
                        if resolved:
                            return resolved

        try:
            from modelscope import snapshot_download

            cache_dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(modelscope_id, cache_dir=str(cache_dir))
            return str(cache_dir)
        except Exception:
            pass

    return model_name


def _find_model_in_dir(base_dir: Path, model_name: str) -> Optional[str]:
    """在目录中递归查找模型目录，匹配 org/model 格式的模型名"""
    parts = model_name.split("/")
    if len(parts) != 2:
        return None
    org, model = parts
    model_normalized = model.replace(".", "___")

    def matches(child_name: str) -> bool:
        return child_name.replace("___", ".") == model or child_name == model_normalized

    if matches(base_dir.name):
        if _is_valid_model_dir(base_dir):
            return str(base_dir)

    for child in base_dir.iterdir():
        if child.is_dir():
            if matches(child.name):
                if _is_valid_model_dir(child):
                    return str(child)
            found = _find_model_in_dir(child, model_name)
            if found:
                return found

    return None


def _is_valid_model_dir(path: Path) -> bool:
    """检查目录是否是有效的模型目录（至少包含 config.json 和模型权重文件）"""
    if not path.is_dir():
        return False
    required_files = ["config.json", "model.safetensors", "pytorch_model.bin"]
    has_model = any((path / f).exists() for f in required_files if f != "pytorch_model.bin" or not (path / "model.safetensors").exists())
    return has_model or (path / "config.json").exists()


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
        
        for obj in (collection, client):
            if obj is None:
                continue
            for attr in ("_batch_size", "batch_size"):
                if hasattr(obj, attr):
                    val = getattr(obj, attr)
                    if isinstance(val, int) and val > 0:
                        candidates.append(val)
        
        return max(candidates) if candidates else DEFAULT_INGEST_BATCH_SIZE
