"""
Flask Web 应用入口 —— 聊天 Agent + 知识库管理

路由分组：
  页面路由：
    GET  /                    聊天页面
    GET  /knowledge           知识库管理页面

  聊天 API (/api/chat/)：
    GET  /state               Agent 状态（内存、是否忙碌）
    POST /reset               重置会话
    POST /sync                同步对话历史到 Agent 内存
    GET  /conversations       对话列表
    POST /conversations       创建对话
    GET  /conversations/<id>  获取对话详情和消息
    POST /conversations/<id>/activate   激活对话
    DELETE /conversations/<id>          删除对话
    POST /conversations/batch-delete    批量删除对话
    POST /conversations/<id>/messages   追加消息
    PATCH /conversations/<id>/messages/<msg_id>  更新消息分段
    POST /conversations/<id>/touch      更新对话时间戳
    POST /conversations/<id>/title      更新对话标题
    POST /stream              SSE 流式聊天（核心接口）

  知识库 API (/api/kb/)：
    GET  /documents           文档列表
    GET  /health              健康检查
    POST /upload              上传并入库文档
    GET  /job/<job_id>        查询入库任务状态
    GET  /jobs/active         活跃任务列表
    GET  /chunks/stats        分块统计
    DELETE /documents/<source> 删除文档
"""

import json
import os
import re
import sys
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.chat.db import get_chat_db


BASE_DIR = Path(__file__).resolve().parent
FILES_DIR = BASE_DIR / "files"
VUE_DIR = BASE_DIR / "static-vue"

_UNSAFE_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str) -> str:
    """
    清理文件名中的危险字符，防止路径遍历攻击。
    
    移除 Windows/Unix 不允许的字符，合并连续点号，
    拒绝空文件名和 "." / ".."。
    """
    name = _UNSAFE_PATTERN.sub("", name).strip()
    name = re.sub(r'\.+', ".", name)
    if not name or name in (".", ".."):
        raise ValueError("invalid filename")
    return name


ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}

app = Flask(__name__, static_folder="static")

# 启动时校验 RAG 配置
try:
    from src.rag.config import validate_rag_config
    rag_warnings = validate_rag_config()
    if rag_warnings:
        import logging as _logging
        _rag_logger = _logging.getLogger("agent.startup")
        for w in rag_warnings:
            _rag_logger.warning("RAG config: %s", w)
except Exception:
    pass

_agent_instance = None
_agent_init_lock = threading.Lock()
_agent_instances: dict[str, "Agent"] = {}
_agent_instances_lock = threading.Lock()


def _json_sse(event_name: str, payload: dict) -> str:
    """构造 SSE 事件字符串：event: <name>\ndata: <json>\n\n"""
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def get_agent() -> "Agent":
    """获取全局 Agent 单例（双重检查锁，懒加载）—— 供非对话相关接口使用"""
    global _agent_instance
    if _agent_instance is None:
        with _agent_init_lock:
            if _agent_instance is None:
                from src.core.agent import Agent, Model
                from src.core.tools import (
                    calculate, calculate_average, calculate_percentage,
                    create_file, delete_file, delete_multiple_files,
                    get_current_time, get_search_results,
                    list_files,
                    plot_bar_chart, plot_histogram, plot_line_chart,
                    plot_multi_line_chart, plot_pie_chart, plot_scatter_chart,
                    rag_delete_document, rag_ingest_document,
                    rag_list_documents, rag_query, read_file,
                )

                tools = [
                    get_current_time, get_search_results,
                    create_file, read_file, list_files,
                    delete_file, delete_multiple_files,
                    calculate, calculate_percentage, calculate_average,
                    plot_line_chart, plot_bar_chart, plot_pie_chart,
                    plot_scatter_chart, plot_histogram, plot_multi_line_chart,
                    rag_ingest_document, rag_query,
                    rag_list_documents, rag_delete_document,
                ]

                model = Model()
                _agent_instance = Agent(model, tools)
    return _agent_instance


def get_agent_for_conversation(conv_id: str) -> "Agent":
    """获取按对话隔离的 Agent 实例，每个对话拥有独立记忆和流锁"""
    with _agent_instances_lock:
        agent = _agent_instances.get(conv_id)
        if agent is not None:
            return agent

        from src.core.agent import Agent, Model
        from src.core.tools import (
            calculate, calculate_average, calculate_percentage,
            create_file, delete_file, delete_multiple_files,
            get_current_time, get_search_results,
            list_files,
            plot_bar_chart, plot_histogram, plot_line_chart,
            plot_multi_line_chart, plot_pie_chart, plot_scatter_chart,
            rag_delete_document, rag_ingest_document,
            rag_list_documents, rag_query, read_file,
        )

        tools = [
            get_current_time, get_search_results,
            create_file, read_file, list_files,
            delete_file, delete_multiple_files,
            calculate, calculate_percentage, calculate_average,
            plot_line_chart, plot_bar_chart, plot_pie_chart,
            plot_scatter_chart, plot_histogram, plot_multi_line_chart,
            rag_ingest_document, rag_query,
            rag_list_documents, rag_delete_document,
        ]

        model = Model()
        agent = Agent(model, tools)
        agent.conv_id = conv_id
        _agent_instances[conv_id] = agent
        return agent


def remove_agent_for_conversation(conv_id: str):
    """删除对话对应的 Agent 实例，释放资源"""
    with _agent_instances_lock:
        _agent_instances.pop(conv_id, None)


def _get_rag_service_safe():
    """安全获取 RAG 服务实例，失败时返回 (None, error_message)"""
    try:
        from src.rag.service import get_rag_service

        return get_rag_service(), None
    except Exception as exc:
        return None, str(exc)


@app.get("/")
def chat_page():
    """聊天页面"""
    return send_from_directory(str(VUE_DIR), "index.html")


@app.get("/knowledge")
def knowledge_page():
    """知识库管理页面"""
    return send_from_directory(str(VUE_DIR), "index.html")


@app.get("/assets/<path:filename>")
def vue_assets(filename: str):
    """Vue 构建的静态资源"""
    assets_dir = VUE_DIR / "assets"
    return send_from_directory(str(assets_dir), filename)


@app.get("/favicon.ico")
def favicon():
    favicon_path = VUE_DIR / "favicon.ico"
    if favicon_path.exists():
        return send_from_directory(str(VUE_DIR), "favicon.ico")
    return "", 204


@app.get("/api/chat/state")
def api_chat_state():
    """获取 Agent 当前状态（内存信息、是否正在生成）"""
    conv_id = request.args.get("conv_id", "").strip()
    if conv_id:
        agent = get_agent_for_conversation(conv_id)
    else:
        agent = get_agent()
    return jsonify(
        {
            "ok": True,
            "memory": agent.get_memory_status(),
            "busy": agent.is_busy(),
        }
    )


@app.post("/api/chat/reset")
def api_chat_reset():
    """重置 Agent 会话内存，生成中不允许重置"""
    conv_id = (request.get_json(silent=True) or {}).get("conv_id", "").strip()
    if conv_id:
        agent = get_agent_for_conversation(conv_id)
    else:
        agent = get_agent()

    if agent.is_busy():
        return jsonify({"ok": False, "message": "当前正在生成，请先停止生成"}), 409

    agent.clear_memory()
    return jsonify({"ok": True, "message": "会话已重置"})


@app.post("/api/chat/sync")
def api_chat_sync():
    """同步前端对话历史到 Agent 内存，用于恢复上下文"""
    body = request.get_json(silent=True) or {}
    conv_id = str(body.get("conv_id", "")).strip()

    if conv_id:
        agent = get_agent_for_conversation(conv_id)
    else:
        agent = get_agent()

    if agent.is_busy():
        return jsonify({"ok": False, "message": "当前正在生成，请先停止生成"}), 409

    messages = body.get("messages", [])
    if not isinstance(messages, list):
        return jsonify({"ok": False, "message": "messages 必须是数组"}), 400

    agent.sync_memory_from_conversation(messages)
    return jsonify({"ok": True, "memory": agent.get_memory_status()})


# ========== Chat History API ==========

@app.get("/api/chat/conversations")
def api_list_conversations():
    """获取对话列表及当前活跃对话 ID"""
    db = get_chat_db()
    convs = db.list_conversations()
    active_id = db.get_active_conversation_id()
    return jsonify({"ok": True, "conversations": convs, "activeId": active_id})


@app.post("/api/chat/conversations")
def api_create_conversation():
    db = get_chat_db()
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "新对话")).strip() or "新对话"
    conv = db.create_conversation(title)
    return jsonify({"ok": True, "conversation": conv})


@app.get("/api/chat/conversations/<conv_id>")
def api_get_conversation(conv_id):
    db = get_chat_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"ok": False, "message": "对话不存在"}), 404
    messages = db.get_messages(conv_id)
    return jsonify({"ok": True, "conversation": conv, "messages": messages})


@app.post("/api/chat/conversations/<conv_id>/activate")
def api_activate_conversation(conv_id):
    db = get_chat_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"ok": False, "message": "对话不存在"}), 404
    db.set_active_conversation(conv_id)
    return jsonify({"ok": True})


@app.delete("/api/chat/conversations/<conv_id>")
def api_delete_conversation(conv_id):
    db = get_chat_db()
    db.delete_conversation(conv_id)
    remove_agent_for_conversation(conv_id)
    return jsonify({"ok": True})


@app.post("/api/chat/conversations/batch-delete")
def api_batch_delete_conversations():
    db = get_chat_db()
    body = request.get_json(silent=True) or {}
    ids = body.get("ids", [])
    if not isinstance(ids, list) or not ids:
        return jsonify({"ok": False, "message": "ids 必须是非空数组"}), 400
    count = db.delete_conversations_batch(ids)
    for cid in ids:
        remove_agent_for_conversation(cid)
    return jsonify({"ok": True, "deleted": count})


@app.post("/api/chat/conversations/<conv_id>/messages")
def api_append_message(conv_id):
    db = get_chat_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        return jsonify({"ok": False, "message": "对话不存在"}), 404
    body = request.get_json(silent=True) or {}
    role = str(body.get("role", "")).strip()
    if role == "user":
        content = str(body.get("content", "")).strip()
        if not content:
            return jsonify({"ok": False, "message": "content 不能为空"}), 400
        msg = db.append_user_message(conv_id, content)
        return jsonify({"ok": True, "message": msg})
    elif role == "assistant":
        msg = db.create_assistant_message(conv_id)
        return jsonify({"ok": True, "message": msg})
    else:
        return jsonify({"ok": False, "message": "role 必须是 user 或 assistant"}), 400


@app.patch("/api/chat/conversations/<conv_id>/messages/<int:msg_id>")
def api_update_message(conv_id, msg_id):
    db = get_chat_db()
    body = request.get_json(silent=True) or {}
    action = str(body.get("action", "")).strip()
    if action == "append_text":
        content = str(body.get("content", ""))
        db.append_text_segment(conv_id, msg_id, content)
    elif action == "append_reasoning":
        content = str(body.get("content", ""))
        db.append_reasoning_segment(conv_id, msg_id, content)
    elif action == "add_tool_call":
        name = str(body.get("name", "tool"))
        args = body.get("args", {})
        if not isinstance(args, dict):
            args = {}
        db.add_tool_call_segment(conv_id, msg_id, name, args)
    elif action == "set_tool_result":
        result = str(body.get("result", ""))
        db.update_tool_result(conv_id, msg_id, result)
    elif action == "set_token_stats":
        stats = body.get("stats", {})
        if not isinstance(stats, dict):
            stats = {}
        db.set_token_stats(conv_id, msg_id, stats)
    else:
        return jsonify({"ok": False, "message": f"未知 action: {action}"}), 400
    return jsonify({"ok": True})


@app.post("/api/chat/conversations/<conv_id>/touch")
def api_touch_conversation(conv_id):
    db = get_chat_db()
    db.touch_conversation(conv_id)
    return jsonify({"ok": True})


@app.post("/api/chat/conversations/<conv_id>/title")
def api_update_conversation_title(conv_id):
    db = get_chat_db()
    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "新对话")).strip() or "新对话"
    db.update_conversation_title(conv_id, title)
    return jsonify({"ok": True})


@app.post("/api/chat/stream")
def api_chat_stream():
    """
    SSE 流式聊天接口（核心）。

    每个对话使用独立的 Agent 实例和流锁，多对话可并发。
    Agent 的 React_Agent_Stream_UI 生成的事件被转换为 SSE 格式推送：
      - content:    文本增量
      - reasoning:  推理过程增量
      - tool_call:  工具调用通知
      - tool_result: 工具执行结果
      - token_stats: Token 统计
      - done:       生成完成
      - error:      生成失败
    """
    body = request.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()
    conv_id = str(body.get("conv_id", "")).strip()
    if not message:
        return jsonify({"ok": False, "message": "message 不能为空"}), 400

    agent = get_agent_for_conversation(conv_id) if conv_id else get_agent()

    if not agent.acquire_stream_lock():
        return jsonify({"ok": False, "message": "已有回复在生成，请先停止"}), 409

    @stream_with_context
    def event_stream():
        event_iter = None
        try:
            event_iter = agent.React_Agent_Stream_UI(message)
            for event_type, data in event_iter:
                if event_type == "content":
                    yield _json_sse("content", {"delta": data})
                elif event_type == "reasoning":
                    yield _json_sse("reasoning", {"delta": data})
                elif event_type == "phase":
                    yield _json_sse("phase", data)
                elif event_type == "tool_call":
                    yield _json_sse("tool_call", data)
                elif event_type == "tool_result":
                    yield _json_sse("tool_result", data)
                elif event_type == "token_stats":
                    yield _json_sse("token_stats", data)

            yield _json_sse("done", {"ok": True})
        except GeneratorExit:
            pass
        except Exception as exc:
            yield _json_sse("error", {"message": f"生成失败: {exc}"})
        finally:
            if event_iter is not None:
                try:
                    event_iter.close()
                except Exception:
                    pass
            agent.release_stream_lock()

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/kb/documents")
def api_kb_documents():
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    docs = service.list_documents()
    return jsonify({"ok": True, "documents": docs, "count": len(docs)})


@app.get("/api/kb/health")
def api_kb_health():
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    status = service.health_status(job_limit=5, probe_models=False)
    return jsonify(status)


@app.post("/api/kb/upload")
def api_kb_upload():
    """
    上传文档到知识库。
    
    流程：校验文件名 → 检查扩展名 → 检查重复 → 保存到 files/ → 调用 RAG 入库
    支持格式：.txt, .md, .markdown, .pdf, .docx
    """
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"ok": False, "message": "缺少上传文件(file)"}), 400

    raw_name = uploaded.filename or ""
    try:
        filename = _safe_filename(Path(raw_name).name)
    except ValueError:
        return jsonify({"ok": False, "message": "无效文件名"}), 400

    if not filename:
        return jsonify({"ok": False, "message": "无效文件名"}), 400

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"ok": False, "message": f"不支持的文件类型: {suffix}"}), 400

    # 检查同名文档是否已存在
    docs = service.list_documents()
    if any(d.get("source") == filename for d in docs):
        return jsonify({
            "ok": False,
            "message": f"文档「{filename}」已入库，如需重新入库请先删除旧文档",
        }), 409

    FILES_DIR.mkdir(parents=True, exist_ok=True)
    save_path = FILES_DIR / filename
    uploaded.save(save_path)

    result = service.ingest_file(filename)
    code = 200 if result.get("ok") else 400
    return jsonify(result), code


@app.get("/api/kb/job/<job_id>")
def api_kb_job(job_id: str):
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    status = service.get_job_status(job_id)
    code = 200 if status.get("ok") else 404
    return jsonify(status), code


@app.get("/api/kb/jobs/active")
def api_kb_active_jobs():
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    jobs = service.get_active_jobs()
    return jsonify({"ok": True, "jobs": jobs, "count": len(jobs)})


@app.get("/api/kb/chunks/stats")
def api_kb_chunk_stats():
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    stats = service.get_chunk_stats()
    return jsonify({"ok": True, "stats": stats})


@app.delete("/api/kb/documents/<path:source>")
def api_kb_delete(source: str):
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    safe_source = Path(source).name.strip()
    if not safe_source:
        return jsonify({"ok": False, "message": "source 不能为空"}), 400

    result = service.delete_document(safe_source)
    code = 200 if result.get("ok") else 404
    return jsonify(result), code


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
