"""
检索服务模块 —— 混合检索、分数融合、Auto-merging

核心功能：
  - RRF (Reciprocal Rank Fusion) 融合：基于排名的融合，对分数分布不敏感
  - 加权 RRF：支持多路查询变体的加权融合
  - 线性加权融合：归一化后按权重线性组合
  - Auto-merging：当同一父块下的子块命中数 >= 阈值时，自动替换为父块
  - 动态参数：根据查询长度和 Token 数自动调整 BM25/向量权重和候选数量
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .cache import LruCache
from .config import (
    AUTO_MERGE_ENABLED,
    AUTO_MERGE_THRESHOLD,
    RRF_ENABLED,
    RRF_K,
    HYBRID_MODE,
    CACHE_ENABLED,
    CACHE_MAX_SIZE,
    CACHE_TTL_SECONDS,
)
from .database import Database


class Retriever:
    """
    检索服务：负责分数融合、Auto-merging 和动态参数计算。
    
    不直接执行检索（由 RagService._retrieve_candidates 完成），
    而是提供融合算法和后处理逻辑。
    """
    
    def __init__(
        self,
        database: Database,
        parent_chunk_cache: Optional[LruCache] = None,
    ):
        """
        Args:
            database: SQLite 数据库实例，用于查询父块
            parent_chunk_cache: 父块 LRU 缓存，避免频繁查库
        """
        self._db = database
        self._cache = parent_chunk_cache
    
    def normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """
        Min-Max 归一化：将分数缩放到 [0, 1] 区间。

        所有值相同时统一返回 1.0，避免除零。
        """
        if not scores:
            return {}
        vals = list(scores.values())
        min_v = min(vals)
        max_v = max(vals)
        if max_v - min_v < 1e-12:
            return {k: 1.0 for k in scores}
        return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}
    
    def reciprocal_rank_fusion(
        self,
        bm25_results: List[Tuple[str, float]],
        vector_results: List[Tuple[str, float]],
        k: int = 60,
    ) -> Dict[str, float]:
        """
        RRF (Reciprocal Rank Fusion) 融合算法
        
        公式：RRF_score(doc) = Σ 1 / (k + rank_i(doc))
        
        优点：对分数分布不敏感，仅依赖排名顺序，适合融合不同量纲的检索结果。
        
        Args:
            bm25_results: BM25 排序结果 [(chunk_id, score), ...]
            vector_results: 向量检索排序结果 [(chunk_id, score), ...]
            k: 平滑常数，越大则排名差异的影响越小（默认60）
        
        Returns:
            {chunk_id: rrf_score} 融合后的分数字典
        """
        rrf_scores: Dict[str, float] = defaultdict(float)
        
        for rank, (chunk_id, _) in enumerate(bm25_results, start=1):
            rrf_scores[chunk_id] += 1.0 / (k + rank)
        
        for rank, (chunk_id, _) in enumerate(vector_results, start=1):
            rrf_scores[chunk_id] += 1.0 / (k + rank)
        
        return dict(rrf_scores)

    def weighted_reciprocal_rank_fusion(
        self,
        rankings: List[List[Tuple[str, float]]],
        k: int = 60,
        weights: Optional[List[float]] = None,
    ) -> Dict[str, float]:
        """
        对多路排序结果执行加权 RRF 融合。

        用于多查询变体场景，每个变体产生一路排序，按权重融合。
        公式：WRRF_score(doc) = Σ weight_i / (k + rank_i(doc))

        Args:
            rankings: 多路排序结果列表，每路为 [(chunk_id, score), ...]
            k: RRF 平滑常数
            weights: 各路权重，默认等权

        Returns:
            {chunk_id: fused_score} 融合后的分数字典
        """
        if not rankings:
            return {}

        weights = weights or [1.0] * len(rankings)
        fused_scores: Dict[str, float] = defaultdict(float)

        for ranking, weight in zip(rankings, weights):
            if not ranking or weight <= 0:
                continue
            for rank, (chunk_id, _) in enumerate(ranking, start=1):
                fused_scores[chunk_id] += float(weight) / (k + rank)

        return dict(fused_scores)
    
    def linear_fusion(
        self,
        bm25_scores: Dict[str, float],
        vec_scores: Dict[str, float],
        w_bm25: float,
        w_vec: float,
    ) -> Dict[str, float]:
        """
        线性加权融合：归一化后按权重组合两路分数。

        公式：hybrid_score = w_bm25 * bm25_norm + w_vec * vec_norm

        Args:
            bm25_scores: BM25 原始分数
            vec_scores: 向量检索原始分数
            w_bm25: BM25 权重
            w_vec: 向量检索权重

        Returns:
            {chunk_id: hybrid_score} 融合后的分数字典
        """
        all_keys = set(bm25_scores.keys()) | set(vec_scores.keys())
        bm25_norm = self.normalize_scores(bm25_scores)
        vec_norm = self.normalize_scores(vec_scores)
        
        hybrid_scores = {}
        for key in all_keys:
            b = bm25_norm.get(key, 0.0)
            v = vec_norm.get(key, 0.0)
            hybrid_scores[key] = w_bm25 * b + w_vec * v
        
        return hybrid_scores
    
    def get_parent_chunks_by_ids(self, chunk_ids: List[str]) -> Dict[str, Dict]:
        """
        根据 chunk_id 批量获取父块数据（带 LRU 缓存）。

        Args:
            chunk_ids: 父块 chunk_id 列表

        Returns:
            {chunk_id: chunk_data_dict}
        """
        if not chunk_ids:
            return {}
        
        ids = [item for item in chunk_ids if item]
        if not ids:
            return {}
        
        result: Dict[str, Dict] = {}
        uncached_ids: List[str] = []
        
        if self._cache:
            for chunk_id in ids:
                cached = self._cache.get(f"parent:{chunk_id}")
                if cached is not None:
                    result[chunk_id] = cached
                else:
                    uncached_ids.append(chunk_id)
        else:
            uncached_ids = ids
        
        if uncached_ids:
            db_results = self._db.get_parent_chunks_by_ids(uncached_ids)
            for chunk_id, chunk_data in db_results.items():
                result[chunk_id] = chunk_data
                if self._cache:
                    self._cache.set(f"parent:{chunk_id}", chunk_data)
        
        return result
    
    def merge_to_parent_level(
        self,
        docs: List[Dict],
        threshold: int = 2,
    ) -> Tuple[List[Dict], int]:
        """
        将满足条件的子块合并到父块。

        当同一父块下的子块命中数量 >= threshold 时，用父块替换这些子块，
        提供更完整的上下文。

        Args:
            docs: 待合并的文档片段列表
            threshold: 触发合并的最小子块数量

        Returns:
            (merged_docs, merged_count) 合并后的列表和被替换的子块数
        """
        groups: Dict[str, List[Dict]] = defaultdict(list)
        for doc in docs:
            parent_id = (doc.get("parent_chunk_id") or "").strip()
            if parent_id:
                groups[parent_id].append(doc)

        merge_parent_ids = [
            parent_id for parent_id, children in groups.items()
            if len(children) >= threshold
        ]
        
        if not merge_parent_ids:
            return docs, 0

        parent_docs = self.get_parent_chunks_by_ids(merge_parent_ids)
        
        merged_docs: List[Dict] = []
        merged_count = 0
        
        for doc in docs:
            parent_id = (doc.get("parent_chunk_id") or "").strip()
            if not parent_id or parent_id not in parent_docs:
                merged_docs.append(doc)
                continue
            
            parent_doc = dict(parent_docs[parent_id])
            score = doc.get("score") or doc.get("hybrid_score") or doc.get("rerank_score")
            if score is not None:
                parent_doc["score"] = max(float(parent_doc.get("score", score)), float(score))
            parent_doc["merged_from_children"] = True
            parent_doc["merged_child_count"] = len(groups[parent_id])
            merged_docs.append(parent_doc)
            merged_count += 1

        deduped: List[Dict] = []
        seen = set()
        for item in merged_docs:
            key = item.get("chunk_id") or item.get("id")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            deduped.append(item)

        return deduped, merged_count
    
    def auto_merge_documents(
        self,
        docs: List[Dict],
        top_k: int,
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        两段自动合并：先 L3→L2，再 L2→L1。

        Auto-merging 策略：当检索命中的子块集中在同一父块下时，
        说明该父块整体相关，应提供更完整的上下文而非碎片化的子块。

        Args:
            docs: 排序后的候选文档列表
            top_k: 最终返回数量

        Returns:
            (final_docs, merge_meta) 合并后的结果和合并元信息
        """
        if not AUTO_MERGE_ENABLED or not docs:
            return docs[:top_k], {
                "auto_merge_enabled": AUTO_MERGE_ENABLED,
                "auto_merge_applied": False,
                "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
                "auto_merge_replaced_chunks": 0,
                "auto_merge_steps": 0,
            }

        merge_pool_size = max(top_k * 2, 10)
        merge_pool = docs[:merge_pool_size]

        merged_docs, merged_count_l3_l2 = self.merge_to_parent_level(merge_pool, threshold=AUTO_MERGE_THRESHOLD)
        merged_docs, merged_count_l2_l1 = self.merge_to_parent_level(merged_docs, threshold=AUTO_MERGE_THRESHOLD)

        remaining = docs[merge_pool_size:]
        for doc in remaining:
            if doc not in merged_docs:
                merged_docs.append(doc)

        merged_docs.sort(key=lambda item: item.get("score") or item.get("hybrid_score") or 0.0, reverse=True)
        merged_docs = merged_docs[:top_k]

        replaced_count = merged_count_l3_l2 + merged_count_l2_l1
        return merged_docs, {
            "auto_merge_enabled": AUTO_MERGE_ENABLED,
            "auto_merge_applied": replaced_count > 0,
            "auto_merge_threshold": AUTO_MERGE_THRESHOLD,
            "auto_merge_replaced_chunks": replaced_count,
            "auto_merge_steps": int(merged_count_l3_l2 > 0) + int(merged_count_l2_l1 > 0),
        }
    
    def dynamic_params(self, query: str, top_k: int) -> dict:
        """
        根据查询特征动态调整检索参数。

        策略：
          - 短查询（≤12字符/≤6 Token）：BM25 权重更高（0.62），关键词匹配更精准
          - 长查询（≥40字符/≥18 Token）：向量权重更高（0.65），语义匹配更合适
          - 中等查询：均衡权重（0.5/0.5）
          - 候选数量 = top_k * 4，短查询额外 +6，长查询额外 +10

        Args:
            query: 查询文本
            top_k: 期望返回数量

        Returns:
            {"w_bm25": float, "w_vec": float, "candidate_k": int}
        """
        from .bm25_index import _tokenize
        
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
