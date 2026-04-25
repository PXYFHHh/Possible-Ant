"""
BM25 稀疏索引模块 —— 关键词检索与持久化

核心功能：
  - 基于 rank_bm25.BM25Okapi 的稀疏检索
  - 中文单字分词 + 英文数字词分词，过滤停用词
  - 索引状态持久化到 JSON 文件，支持增量加载
  - 文档数量变化时自动检测过期状态并重建

分词策略：
  - 中文：逐字分词（[\u4e00-\u9fff]）
  - 英文/数字：按单词分词（[A-Za-z0-9_]+）
  - 过滤停用词后构建词频统计
"""

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

# 中文停用词集合（与 query_rewriter.py 共享语义，但独立维护以避免循环导入）
_STOPWORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就",
    "不", "人", "都", "一", "个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "什么", "怎么",
    "如何", "哪些", "哪个", "吗", "呢", "吧",
    "啊", "哦", "嗯", "关于", "对于", "根据", "按照",
    "中", "之", "以", "及", "其", "与", "或", "等",
    "被", "把", "对", "从", "向", "为", "由",
}


def _tokenize(text: str) -> List[str]:
    """
    分词函数：中文逐字分词，英文按单词分词，过滤停用词。
    
    例："RAG检索是什么" → ["r", "a", "g", "检", "索", "是", "什", "么"]（过滤后）
    """
    if not text:
        return []
    tokens = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


def _now_str() -> str:
    """返回当前时间的格式化字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BM25Index:
    """
    BM25 稀疏索引管理器。
    
    使用 BM25Okapi 算法进行关键词检索，支持索引构建、查询、持久化和过期检测。
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger("agent.rag.bm25")
        self._bm25: Optional[BM25Okapi] = None
        self._chunks: List[dict] = []
        self._doc_count: int = 0
        self._vocab_cache: Dict[str, int] = {}
    
    @property
    def is_built(self) -> bool:
        """索引是否已构建"""
        return self._bm25 is not None
    
    @property
    def doc_count(self) -> int:
        """已索引的文档数量"""
        return self._doc_count
    
    def build(self, chunks: List[dict]) -> None:
        """
        构建 BM25 索引。
        
        对每个分块文本分词后构建 BM25Okapi 索引，
        并在持久化启用时保存状态到文件。
        
        Args:
            chunks: 分块列表，每个元素需包含 "text" 字段
        """
        self._chunks = chunks
        tokenized = [_tokenize(item.get("text", "")) for item in chunks]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None
        self._doc_count = len(chunks)
        
        if BM25_PERSIST_ENABLED:
            self._save_state()
    
    def search(self, query: str, top_k: int) -> List[Tuple[dict, float]]:
        """
        BM25 关键词检索。

        Args:
            query: 查询文本
            top_k: 返回前 K 个结果

        Returns:
            [(chunk_dict, bm25_score), ...] 按 BM25 分数降序
        """
        if not self._bm25 or not self._chunks:
            return []
        
        q_tokens = _tokenize(query)
        scores = self._bm25.get_scores(q_tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        return [(self._chunks[i], float(scores[i])) for i in top_indices]
    
    def invalidate(self) -> None:
        """清除索引和持久化状态文件"""
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
        """
        保存 BM25 索引状态到 JSON 文件。
        
        保存内容：词表、文档频率、平均文档长度、分块 ID 列表。
        不保存完整分块文本，加载时需从数据库重新读取。
        """
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
        """
        从 JSON 文件加载 BM25 索引状态。

        仅当保存的文档数量与当前数据库一致时才加载，否则视为过期。

        Args:
            current_chunk_count: 当前数据库中的分块数量

        Returns:
            True 表示状态有效，False 表示需要重建
        """
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
