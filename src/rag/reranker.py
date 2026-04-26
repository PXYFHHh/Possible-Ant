"""
重排序服务模块 —— Cross-Encoder 模型加载与重排序

核心功能：
  - 模型路径解析：与 embedding.py 相同的优先级策略（本地缓存 → ModelScope → HuggingFace）
  - 冷却机制：重排失败后自动禁用，冷却期（默认 300 秒）后重试
  - 懒加载：首次调用时才加载模型

重排序流程：
  1. 将 (query, doc_text) 对输入 CrossEncoder
  2. 获取相关性分数
  3. 按分数降序排列
"""

import logging
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
    """解析重排模型路径，委托到公共 model_utils 模块"""
    from .model_utils import _resolve_model_path as _do_resolve
    return _do_resolve(model_name, modelscope_id, USE_MODELSCOPE, MODEL_CACHE_DIR)


class RerankerService:
    """
    重排序服务。
    
    使用 Cross-Encoder 模型对检索结果进行精排。
    内置冷却机制：加载或推理失败后自动禁用，冷却期后自动重试。
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger("agent.rag.reranker")
        self._reranker = None
        self._disabled = False
        self._last_error = ""
        self._last_error_at = 0.0
    
    def get(self) -> Optional[object]:
        """
        获取 CrossEncoder 实例（懒加载）。
        
        冷却期内返回 None，冷却期过后自动重试加载。
        """
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
        对文档列表进行 Cross-Encoder 重排序。

        Args:
            query: 查询文本
            docs: 待重排的文档列表
            text_key: 文档中文本内容的键名

        Returns:
            (reranked_docs, error_message) —— 重排后的文档和可能的错误信息
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
        """重排服务是否处于禁用状态（冷却期内）"""
        return self._disabled
    
    @property
    def last_error(self) -> str:
        """最近一次重排错误信息"""
        return self._last_error
