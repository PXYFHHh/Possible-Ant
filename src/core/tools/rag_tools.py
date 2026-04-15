import os
import re

from langchain_core.tools import tool


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


RAG_QUERY_MAX_ATTEMPTS = max(1, min(_env_int("RAG_QUERY_MAX_ATTEMPTS", 3), 5))
RAG_QUERY_MIN_HITS = max(1, min(_env_int("RAG_QUERY_MIN_HITS", 2), 10))
RAG_QUERY_LOW_SCORE_THRESHOLD = _env_float("RAG_QUERY_LOW_SCORE_THRESHOLD", 0.12)


def _dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _rewrite_query_candidates(query: str, max_attempts: int):
    base = re.sub(r"\s+", " ", str(query or "").strip())
    if not base:
        return []

    variants = [base]

    normalized = re.sub(r"[，。！？；：、,.!?;:()（）\[\]{}\"'“”‘’`]+", " ", base)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized:
        variants.append(normalized)

    compact = normalized or base
    compact = re.sub(
        r"(请问|麻烦|帮我|帮忙|我想知道|告诉我|请你|可以|能否|能不能|有没有|一下|一下子|这个|那个)",
        " ",
        compact,
    )
    compact = re.sub(r"\s+", " ", compact).strip(" ?？")
    if compact:
        variants.append(compact)

    if re.search(r"(是什么|含义|定义|概念|原理)", base):
        variants.append(f"{compact or base} 定义 概念".strip())
    elif re.search(r"(怎么|如何|怎样|步骤|流程)", base):
        variants.append(f"{compact or base} 方法 步骤".strip())
    elif re.search(r"(区别|差异|对比)", base):
        variants.append(f"{compact or base} 区别 对比".strip())

    candidates = _dedupe_keep_order(variants)
    return candidates[:max_attempts]


def _result_hit_count(result: dict) -> int:
    rows = result.get("results") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        return 0
    return len(rows)


def _result_top_score(result: dict) -> float:
    rows = result.get("results") if isinstance(result, dict) else None
    if not isinstance(rows, list) or not rows:
        return 0.0

    best = 0.0
    for item in rows:
        if not isinstance(item, dict):
            continue
        score = item.get("rerank_score")
        if score is None:
            score = item.get("hybrid_score")
        try:
            best = max(best, float(score or 0.0))
        except (TypeError, ValueError):
            continue
    return best


def _should_retry(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if not result.get("ok"):
        return False

    hit_count = _result_hit_count(result)
    if hit_count == 0:
        return True

    if hit_count < RAG_QUERY_MIN_HITS and _result_top_score(result) < RAG_QUERY_LOW_SCORE_THRESHOLD:
        return True

    return False


def _is_better_result(candidate: dict, current_best: dict) -> bool:
    if not isinstance(candidate, dict):
        return False
    if not isinstance(current_best, dict):
        return True

    candidate_ok = bool(candidate.get("ok"))
    current_ok = bool(current_best.get("ok"))
    if candidate_ok != current_ok:
        return candidate_ok

    candidate_hits = _result_hit_count(candidate)
    current_hits = _result_hit_count(current_best)
    if candidate_hits != current_hits:
        return candidate_hits > current_hits

    return _result_top_score(candidate) > _result_top_score(current_best)


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

    params:
        query: 查询问题
        top_k: 返回片段数量（默认5）

    return:
        检索结果文本（包含来源和片段）
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

        query_candidates = _rewrite_query_candidates(query, RAG_QUERY_MAX_ATTEMPTS)
        if not query_candidates:
            return "❌ query 不能为空"

        attempts = []
        best_result = None
        best_query = ""

        for idx, candidate_query in enumerate(query_candidates):
            result = service.query(query=candidate_query, top_k=top_k)
            attempts.append((candidate_query, result))

            if _is_better_result(result, best_result):
                best_result = result
                best_query = candidate_query

            has_more_candidates = idx < len(query_candidates) - 1
            if not has_more_candidates or not _should_retry(best_result):
                break

        result = best_result or {"ok": False, "message": "检索失败", "results": []}

        if not result.get("ok"):
            return f"❌ {result.get('message', '检索失败')}"

        rows = []
        weights = result.get("weights", {})
        rows.append(f"最终查询: {best_query or query}")
        rows.append(f"命中数量: {_result_hit_count(result)}")

        if len(attempts) > 1:
            rows.append(f"自动改写检索: 已尝试 {len(attempts)} 次")
            for i, (attempt_query, attempt_result) in enumerate(attempts, 1):
                hit_count = _result_hit_count(attempt_result)
                rows.append(f"- 第{i}次 | 命中={hit_count} | query={attempt_query}")

        rows.append(
            "检索策略: "
            f"BM25权重={weights.get('bm25', 0):.2f}, "
            f"向量权重={weights.get('vector', 0):.2f}, "
            f"候选数={result.get('candidate_k', 0)}, "
            f"重排={'开启' if result.get('reranker_enabled') else '关闭'}"
        )
        if not result.get("vector_available", True):
            rows.append("提示: 当前未启用向量检索，仅使用 BM25 检索（请检查向量模型依赖）")
        rows.append("")
        rows.append("命中片段:")

        result_items = result.get("results", [])
        if not result_items:
            rows.append("（无命中）")

        for idx, item in enumerate(result_items, 1):
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
