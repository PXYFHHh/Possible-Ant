from langchain_core.tools import tool


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
        top_k = max(1, min(top_k, 10))
        service, err = _get_rag_service_safe()
        if err:
            return f"❌ {err}"
        result = service.query(query=query, top_k=top_k)

        if not result.get("ok"):
            return f"❌ {result.get('message', '检索失败')}"

        rows = []
        weights = result.get("weights", {})
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

        for idx, item in enumerate(result.get("results", []), 1):
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
