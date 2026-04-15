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
    """在目录中递归查找模型目录"""
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
    """检查目录是否是有效的模型目录"""
    if not path.is_dir():
        return False
    required_files = ["config.json", "model.safetensors", "pytorch_model.bin"]
    has_model = any((path / f).exists() for f in required_files if f != "pytorch_model.bin" or not (path / "model.safetensors").exists())
    return has_model or (path / "config.json").exists()


class EmbeddingService:
    """向量嵌入服务"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("agent.rag.embedding")
        self._embedding = None
        self._vectorstore = None
        self._device = self._detect_device()
    
    def _detect_device(self) -> str:
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"
    
    def get_embedding(self):
        if self._embedding is None:
            model_path = _resolve_model_path(EMBEDDING_MODEL, EMBEDDING_MODELSCOPE_ID)
            self._embedding = HuggingFaceEmbeddings(
                model_name=model_path,
                model_kwargs={"device": self._device},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embedding
    
    def get_vectorstore(self) -> Chroma:
        if self._vectorstore is not None:
            return self._vectorstore
        
        self._vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=self.get_embedding(),
        )
        return self._vectorstore
    
    def reset_vectorstore(self) -> None:
        self._vectorstore = None
    
    def detect_batch_size(self, vs: Chroma) -> int:
        candidates = []
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
