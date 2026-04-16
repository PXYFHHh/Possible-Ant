import threading
from typing import Dict, List, Optional, Set

from langchain_core.tools import tool

from src.rag.query_rewriter import build_query_variants


_lock = threading.Lock()
_seen_chunks: Dict[str, Set[str]] = {}
_current_session: Optional[str] = None


def start_rag_session(session_id: str) -> None:
    """
    开始一个新的 RAG 检索会话，初始化去重缓存。
    每轮用户对话开始时调用，确保不同对话之间的去重状态隔离。
    """
    global _current_session
    with _lock:
        _current_session = session_id
        _seen_chunks[session_id] = set()


def end_rag_session(session_id: str) -> None:
    """
    结束 RAG 检索会话，清理去重缓存。
    """
    global _current_session
    with _lock:
        _seen_chunks.pop(session_id, None)
        if _current_session == session_id:
            _current_session = None


def _get_seen_set() -> Set[str]:
    """获取当前会话的去重集合"""
    if _current_session is None:
        return set()
    return _seen_chunks.get(_current_session, set())


def _mark_seen(chunk_id: str) -> None:
    """将 chunk_id 标记为已召回"""
    if _current_session is None:
        return
    with _lock:
        if _current_session in _seen_chunks:
            _seen_chunks[_current_session].add(chunk_id)


def _result_hit_count(result: dict) -> int:
    rows = result.get("results") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        return 0
    return len(rows)


def _get_rag_service_safe():
    try:
        from src.rag.service import get_rag_service

        return get_rag_service(), None
    except Exception as exc:
        return None, f"RAG 依赖未就绪，请先安装 requirements.txt 依赖。错误: {exc}"


@tool
def rag_ingest_document(filename: str) -> str:
    """
    将 files 文件夹中的文档切片后写入向量知识库。

    params:
        filename: 文件名（需位于 files 文件夹）

    return:
        入库结果
    """
    try:
        service, err = _get_rag_service_safe()
        if err:
            return f"❌ {err}"
        result = service.ingest_file(filename)
        if result.get("ok"):
            return f"✅ {result['message']}，共切片 {result.get('chunk_count', 0)} 个"
        return f"❌ {result.get('message', '入库失败')}"
    except Exception as exc:
        return f"❌ 文档入库失败: {exc}"


@tool
def rag_query(query: str, top_k: int = 5) -> str:
    """
    在知识库中执行 BM25 + 向量相似度 的混合检索，并对结果重排。
    同一轮对话中多次调用会自动去重：已召回过的片段不会重复返回。

    params:
        query: 查询问题
        top_k: 返回片段数量（默认5）

    return:
        检索结果文本（包含来源和片段），已去重
    """
    try:
        try:
            top_k = int(top_k)
        except (TypeError, ValueError):
            top_k = 5
        top_k = max(1, min(top_k, 10))
        service, err = _get_rag_service_safe()
        if err:
            return f"❌ {err}"

        query_variants = build_query_variants(query)
        if not query_variants:
            return "❌ query 不能为空"

        result = service.query(query=query_variants[0], top_k=top_k, query_variants=query_variants[1:])

        if not result.get("ok"):
            return f"❌ {result.get('message', '检索失败')}"

        result_items = result.get("results", [])

        # 去重：过滤已召回过的片段，只保留新片段
        seen = _get_seen_set()
        new_items = []
        dup_count = 0
        for item in result_items:
            chunk_id = str(item.get("chunk_id", ""))
            if chunk_id and chunk_id in seen:
                dup_count += 1
                continue
            new_items.append(item)
            if chunk_id:
                _mark_seen(chunk_id)

        # 构建输出
        rows = []
        weights = result.get("weights", {})
        rows.append(f"最终查询: {query_variants[0]}")
        rows.append(f"命中数量: {_result_hit_count(result)}")

        # 去重统计信息（放在 meta 区，不影响前端解析）
        total_seen = len(seen) + len(new_items)
        if dup_count > 0:
            rows.append(
                f"去重: 过滤 {dup_count} 个重复 | "
                f"本次返回 {len(new_items)} 个新片段 | "
                f"本轮累计召回 {total_seen} 个不同片段"
            )
        else:
            rows.append(f"本次返回 {len(new_items)} 个片段 | 本轮累计召回 {total_seen} 个不同片段")

        variant_reports = result.get("variant_reports") or []
        if len(variant_reports) > 1:
            rows.append(f"自动改写检索: 已融合 {len(variant_reports)} 个 query 视角")
            for i, variant in enumerate(variant_reports, 1):
                rows.append(
                    f"- 第{i}路 | 候选={variant.get('candidate_count', 0)} | "
                    f"权重={variant.get('weight', 0):.2f} | query={variant.get('query', '')}"
                )

        rows.append(
            "检索策略: "
            f"BM25权重={weights.get('bm25', 0):.2f}, "
            f"向量权重={weights.get('vector', 0):.2f}, "
            f"候选数={result.get('candidate_k', 0)}, "
            f"融合={result.get('fusion_mode', 'unknown')}, "
            f"重排={'开启' if result.get('reranker_enabled') else '关闭'}"
        )
        if not result.get("vector_available", True):
            rows.append("提示: 当前未启用向量检索，仅使用 BM25 检索（请检查向量模型依赖）")
        rows.append("")

        # 输出去重后的片段，保持 "命中片段:" 标识符让前端解析器能识别
        if not new_items:
            rows.append("命中片段:")
            rows.append("（无新增，所有命中片段已在之前召回中返回）")
        else:
            rows.append("命中片段:")
            for idx, item in enumerate(new_items, 1):
                text = item.get("text", "")
                if len(text) > 450:
                    text = text[:450] + " ..."
                rows.append(
                    f"{idx}. 来源: {item.get('source', '未知')} | "
                    f"chunk: {item.get('chunk_id', -1)} | "
                    f"hybrid: {item.get('hybrid_score', 0):.4f}"
                )
                rows.append(f"   内容: {text}")

        return "\n".join(rows)
    except Exception as exc:
        return f"❌ 检索失败: {exc}"


@tool
def rag_list_documents() -> str:
    """
    列出当前知识库中已入库的文档。

    return:
        文档列表
    """
    try:
        service, err = _get_rag_service_safe()
        if err:
            return f"❌ {err}"
        docs = service.list_documents()
        if not docs:
            return "知识库为空"

        lines = ["知识库文档列表:"]
        for i, item in enumerate(docs, 1):
            lines.append(
                f"{i}. {item['source']} | chunks={item['chunk_count']} | updated={item['updated_at']}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"❌ 读取知识库文档失败: {exc}"


@tool
def rag_delete_document(source: str) -> str:
    """
    从知识库删除指定来源文档及其全部切片。

    params:
        source: 文档来源名（一般为文件名）

    return:
        删除结果
    """
    try:
        service, err = _get_rag_service_safe()
        if err:
            return f"❌ {err}"
        result = service.delete_document(source)
        if result.get("ok"):
            return f"✅ {result['message']}"
        return f"❌ {result.get('message', '删除失败')}"
    except Exception as exc:
        return f"❌ 删除失败: {exc}"
