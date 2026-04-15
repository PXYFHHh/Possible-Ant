import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

from .config import (
    BM25_PERSIST_ENABLED,
    BM25_STATE_PATH,
    LEAF_RETRIEVE_LEVEL,
)


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text.lower())


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BM25Index:
    """BM25 索引管理"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("agent.rag.bm25")
        self._bm25: Optional[BM25Okapi] = None
        self._chunks: List[dict] = []
        self._doc_count: int = 0
        self._vocab_cache: Dict[str, int] = {}
    
    @property
    def is_built(self) -> bool:
        return self._bm25 is not None
    
    @property
    def doc_count(self) -> int:
        return self._doc_count
    
    def build(self, chunks: List[dict]) -> None:
        """构建BM25索引"""
        self._chunks = chunks
        tokenized = [_tokenize(item.get("text", "")) for item in chunks]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None
        self._doc_count = len(chunks)
        
        if BM25_PERSIST_ENABLED:
            self._save_state()
    
    def search(self, query: str, top_k: int) -> List[Tuple[dict, float]]:
        """
        搜索
        
        Returns:
            [(chunk, score), ...]
        """
        if not self._bm25 or not self._chunks:
            return []
        
        q_tokens = _tokenize(query)
        scores = self._bm25.get_scores(q_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        return [(self._chunks[i], float(scores[i])) for i in top_indices]
    
    def invalidate(self) -> None:
        """清除索引"""
        self._bm25 = None
        self._chunks = []
        self._doc_count = 0
        self._vocab_cache = {}
        
        if BM25_PERSIST_ENABLED and BM25_STATE_PATH.exists():
            try:
                BM25_STATE_PATH.unlink()
            except Exception:
                pass
    
    def _save_state(self) -> None:
        """保存BM25状态到文件"""
        if not self._bm25 or not self._chunks:
            return
        
        try:
            tokenized = [_tokenize(item.get("text", "")) for item in self._chunks]
            
            vocab: Dict[str, int] = {}
            doc_freq: Dict[str, int] = Counter()
            
            for tokens in tokenized:
                seen_in_doc = set()
                for token in tokens:
                    if token not in vocab:
                        vocab[token] = len(vocab)
                    if token not in seen_in_doc:
                        doc_freq[token] += 1
                        seen_in_doc.add(token)
            
            state = {
                "version": 1,
                "doc_count": len(self._chunks),
                "vocab": vocab,
                "doc_freq": dict(doc_freq),
                "avgdl": sum(len(t) for t in tokenized) / len(tokenized) if tokenized else 0,
                "chunk_ids": [item.get("id") for item in self._chunks],
                "saved_at": _now_str(),
            }
            
            BM25_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            BM25_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            self.logger.info("BM25 state saved: %d chunks, %d vocab", len(self._chunks), len(vocab))
        except Exception as exc:
            self.logger.warning("Failed to save BM25 state: %s", exc)
    
    def load_state(self, current_chunk_count: int) -> bool:
        """从文件加载BM25状态"""
        if not BM25_STATE_PATH.exists():
            return False
        
        try:
            state = json.loads(BM25_STATE_PATH.read_text(encoding="utf-8"))
            
            saved_doc_count = state.get("doc_count", 0)
            if saved_doc_count != current_chunk_count:
                self.logger.info(
                    "BM25 state stale: saved=%d current=%d, will rebuild",
                    saved_doc_count, current_chunk_count
                )
                return False
            
            self._vocab_cache = state.get("vocab", {})
            self._doc_count = saved_doc_count
            self.logger.info("BM25 state loaded: %d chunks", saved_doc_count)
            return True
        except Exception as exc:
            self.logger.warning("Failed to load BM25 state: %s", exc)
            return False
