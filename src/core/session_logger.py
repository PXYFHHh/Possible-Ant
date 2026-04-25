"""
会话日志模块 —— 每次对话生成独立的 JSONL 日志文件

日志格式：每行一个 JSON 对象，包含时间戳、事件类型和事件数据。
日志目录：<project_root>/logs/
文件命名：session_<YYYYMMDD_HHMMSS>_<session_id前8位>.jsonl

记录的事件类型：
  - session_start:  会话开始
  - user_input:     用户输入（截断预览）
  - llm_call:       LLM 调用（Token 统计）
  - tool_call:      工具调用（名称、参数预览）
  - tool_result:    工具执行结果（长度、预览）
  - session_end:    会话结束（汇总 Token 统计）
"""

import json
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"  # 日志目录
_TZ = timezone(timedelta(hours=8))                       # 东八区时区


def _now_str() -> str:
    """返回东八区当前时间的格式化字符串"""
    return datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S")


class SessionLogger:
    """
    会话级日志记录器，每个对话生成独立的 JSONL 日志文件。
    日志目录: <project_root>/logs/
    文件命名: session_<YYYYMMDD_HHMMSS>_<uuid>.jsonl
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = threading.Lock()
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(_TZ).strftime("%Y%m%d_%H%M%S")
        self._log_path = LOGS_DIR / f"session_{ts}_{session_id[:8]}.jsonl"
        self._file = open(self._log_path, "a", encoding="utf-8")
        self._llm_call_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def _write(self, event_type: str, data: Dict[str, Any]) -> None:
        """写入一条 JSONL 日志（线程安全，自动 flush）"""
        entry = {"ts": _now_str(), "type": event_type, **data}
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def log_session_start(self) -> None:
        """记录会话开始事件"""
        self._write("session_start", {
            "session_id": self.session_id,
            "log_file": str(self._log_path),
        })

    def log_user_input(self, text: str) -> None:
        """记录用户输入（超过 200 字符截断预览）"""
        preview = text[:200] + ("..." if len(text) > 200 else "")
        self._write("user_input", {"text": preview, "length": len(text)})

    def log_llm_call(self, call_index: int, input_tokens: int, output_tokens: int,
                      estimated: bool = False, content_preview: str = "") -> None:
        """记录 LLM 调用，累加 Token 统计"""
        self._llm_call_count += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._write("llm_call", {
            "call_index": call_index,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated": estimated,
            "content_preview": (content_preview or "")[:150],
        })

    def log_tool_call(self, call_index: int, tool_name: str, tool_args: Dict[str, Any]) -> None:
        """记录工具调用事件（参数截断到 300 字符预览）"""
        args_preview = json.dumps(tool_args, ensure_ascii=False)[:300]
        self._write("tool_call", {
            "call_index": call_index,
            "tool_name": tool_name,
            "args": args_preview,
        })

    def log_tool_result(self, tool_name: str, result_length: int,
                         result_preview: str = "") -> None:
        """记录工具执行结果（预览截断到 300 字符）"""
        self._write("tool_result", {
            "tool_name": tool_name,
            "result_length": result_length,
            "preview": (result_preview or "")[:300],
        })

    def log_session_end(self, total_llm_calls: int, total_input: int,
                        total_output: int, estimated: bool) -> None:
        """记录会话结束事件，包含汇总 Token 统计"""
        total = total_input + total_output
        self._write("session_end", {
            "total_llm_calls": total_llm_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total,
            "estimated": estimated,
            "log_file": str(self._log_path),
        })

    def close(self) -> None:
        """关闭日志文件句柄"""
        with self._lock:
            if not self._file.closed:
                self._file.close()

    @property
    def log_path(self) -> str:
        """日志文件路径"""
        return str(self._log_path)


_active_loggers: Dict[str, SessionLogger] = {}
_logger_lock = threading.Lock()


def start_session(session_id: str) -> SessionLogger:
    """创建并注册新的 SessionLogger，记录会话开始事件"""
    logger = SessionLogger(session_id)
    logger.log_session_start()
    with _logger_lock:
        _active_loggers[session_id] = logger
    return logger


def get_logger(session_id: str) -> Optional[SessionLogger]:
    """获取指定会话的 SessionLogger"""
    return _active_loggers.get(session_id)


def end_session(session_id: str) -> None:
    """结束会话，关闭日志文件并从活跃列表中移除"""
    with _logger_lock:
        logger = _active_loggers.pop(session_id, None)
    if logger:
        logger.close()
