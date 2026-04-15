import logging
import os
import time
import warnings
from pathlib import Path
from typing import List, Optional, Tuple

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
    RERANK_MODEL,
    RERANK_MODELSCOPE_ID,
    USE_MODELSCOPE,
    MODEL_CACHE_DIR,
    RERANK_RETRY_COOLDOWN_SECONDS,
)


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


class RerankerService:
    """重排序服务"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("agent.rag.reranker")
        self._reranker = None
        self._disabled = False
        self._last_error = ""
        self._last_error_at = 0.0
    
    def get(self) -> Optional[object]:
        now = time.time()
        if self._disabled and (now - self._last_error_at) < RERANK_RETRY_COOLDOWN_SECONDS:
            return None
        
        if self._reranker is not None:
            return self._reranker
        
        if self._disabled and (now - self._last_error_at) >= RERANK_RETRY_COOLDOWN_SECONDS:
            self._disabled = False
        
        try:
            from sentence_transformers import CrossEncoder
            
            rerank_model = _resolve_model_path(RERANK_MODEL, RERANK_MODELSCOPE_ID)
            self._reranker = CrossEncoder(
                rerank_model,
                local_files_only=Path(rerank_model).exists(),
            )
            return self._reranker
        except Exception as exc:
            self._disabled = True
            self._last_error_at = now
            self._last_error = str(exc)
            self.logger.warning("Reranker disabled for cooldown, reason: %s", exc)
            return None
    
    def rerank(
        self,
        query: str,
        docs: List[dict],
        text_key: str = "text",
    ) -> Tuple[List[dict], Optional[str]]:
        """
        对文档进行重排序
        
        Returns:
            (reranked_docs, error_message)
        """
        if not docs:
            return docs, None
        
        reranker = self.get()
        if reranker is None:
            return docs, self._last_error if self._disabled else None
        
        try:
            pairs = [[query, doc[text_key]] for doc in docs]
            scores = reranker.predict(pairs)
            
            for doc, score in zip(docs, scores):
                doc["rerank_score"] = float(score)
            
            docs.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
            return docs, None
        except Exception as exc:
            self._disabled = True
            self._last_error_at = time.time()
            self._last_error = str(exc)
            self.logger.warning("Rerank failed: %s", exc)
            return docs, str(exc)
    
    @property
    def is_disabled(self) -> bool:
        return self._disabled
    
    @property
    def last_error(self) -> str:
        return self._last_error
