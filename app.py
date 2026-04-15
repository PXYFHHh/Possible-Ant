import json
import os
import sys
import threading
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from werkzeug.utils import secure_filename

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.agent import Agent, Model
from src.core.tools import (
    calculate,
    calculate_average,
    calculate_percentage,
    create_file,
    delete_file,
    delete_multiple_files,
    get_activities_by_date_range,
    get_application_usage,
    get_current_time,
    get_deepseek_balance,
    get_deepseek_usage,
    get_manictime_schema,
    get_productivity_summary,
    get_productivity_with_screen_time,
    get_screen_time_by_date,
    get_screen_time_today,
    get_search_results,
    get_today_activities,
    list_files,
    plot_bar_chart,
    plot_histogram,
    plot_line_chart,
    plot_multi_line_chart,
    plot_pie_chart,
    plot_scatter_chart,
    rag_delete_document,
    rag_ingest_document,
    rag_list_documents,
    rag_query,
    read_file,
)


BASE_DIR = Path(__file__).resolve().parent
FILES_DIR = BASE_DIR / "files"
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}

ALL_TOOLS = [
    get_current_time,
    get_search_results,
    create_file,
    read_file,
    list_files,
    delete_file,
    delete_multiple_files,
    calculate,
    calculate_percentage,
    calculate_average,
    plot_line_chart,
    plot_bar_chart,
    plot_pie_chart,
    plot_scatter_chart,
    plot_histogram,
    plot_multi_line_chart,
    get_manictime_schema,
    get_today_activities,
    get_activities_by_date_range,
    get_application_usage,
    get_productivity_summary,
    get_screen_time_today,
    get_screen_time_by_date,
    get_productivity_with_screen_time,
    get_deepseek_balance,
    get_deepseek_usage,
    rag_ingest_document,
    rag_query,
    rag_list_documents,
    rag_delete_document,
]

app = Flask(__name__, template_folder="templates", static_folder="static")

_agent_instance = None
_agent_init_lock = threading.Lock()
_generation_lock = threading.Lock()


def _json_sse(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def get_agent() -> Agent:
    global _agent_instance
    if _agent_instance is None:
        with _agent_init_lock:
            if _agent_instance is None:
                model = Model()
                _agent_instance = Agent(model, ALL_TOOLS)
    return _agent_instance


def _get_rag_service_safe():
    try:
        from src.rag.service import get_rag_service

        return get_rag_service(), None
    except Exception as exc:
        return None, str(exc)


@app.get("/")
def chat_page():
    return render_template("chat.html")


@app.get("/knowledge")
def knowledge_page():
    return render_template("knowledge.html")


@app.get("/api/chat/state")
def api_chat_state():
    agent = get_agent()
    return jsonify(
        {
            "ok": True,
            "memory": agent.get_memory_status(),
            "busy": _generation_lock.locked(),
        }
    )


@app.post("/api/chat/reset")
def api_chat_reset():
    if _generation_lock.locked():
        return jsonify({"ok": False, "message": "当前正在生成，请先停止生成"}), 409

    agent = get_agent()
    agent.clear_memory()
    return jsonify({"ok": True, "message": "会话已重置"})


@app.post("/api/chat/stream")
def api_chat_stream():
    body = request.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "message": "message 不能为空"}), 400

    if not _generation_lock.acquire(blocking=False):
        return jsonify({"ok": False, "message": "已有回复在生成，请先停止"}), 409

    @stream_with_context
    def event_stream():
        event_iter = None
        try:
            agent = get_agent()
            event_iter = agent.React_Agent_Stream_UI(message)
            for event_type, data in event_iter:
                if event_type == "content":
                    yield _json_sse("content", {"delta": data})
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
            _generation_lock.release()

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
    service, err = _get_rag_service_safe()
    if err:
        return jsonify({"ok": False, "message": f"RAG 未就绪: {err}"}), 500

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"ok": False, "message": "缺少上传文件(file)"}), 400

    raw_name = uploaded.filename or ""
    filename = secure_filename(Path(raw_name).name)
    if not filename:
        return jsonify({"ok": False, "message": "无效文件名"}), 400

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"ok": False, "message": f"不支持的文件类型: {suffix}"}), 400

    FILES_DIR.mkdir(parents=True, exist_ok=True)
    save_path = FILES_DIR / filename
    uploaded.save(save_path)

    result = service.ingest_file(filename)
    code = 200 if result.get("ok") else 400
    return jsonify(result), code


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
