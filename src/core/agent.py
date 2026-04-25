"""
Agent 核心模块 —— ReAct 模式的 LLM Agent 实现

本模块实现了基于 ReAct (Reasoning + Acting) 模式的智能体，支持：
- 同步调用 (React_Agent)
- 终端流式输出 (React_Agent_Stream)
- SSE 流式输出供前端消费 (React_Agent_Stream_UI)

安全说明：
  工具参数解析使用 _safe_parse_json_args()，替代了不安全的 eval()，
  采用 json.loads + ast.literal_eval 双重安全解析策略。

架构概览：
  Model  —— LLM 模型封装（基于 LangChain ChatOpenAI）
  Agent  —— ReAct 智能体，管理对话记忆、工具调用、Token 统计
"""

import ast
import json
import logging
import os
import sys
import uuid

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langchain.chat_models import init_chat_model
from typing import List, Callable, Dict, Optional, Tuple

sys.path.append(".")
from src.core.tools import (
    get_current_time,
    get_search_results,
    create_file,
    overwrite_file,
    read_file,
    delete_file,
    list_files,
    calculate,
    calculate_percentage,
    calculate_average,
    get_deepseek_balance,
    get_deepseek_usage,
    rag_ingest_document,
    rag_query,
    rag_list_documents,
    rag_delete_document,
)
from src.core.tools.rag_tools import start_rag_session, end_rag_session
from src.core.session_logger import start_session, end_session

load_dotenv()

logger = logging.getLogger("agent.core")


def _safe_parse_json_args(args_str: str) -> dict:
    """
    安全解析 LLM 返回的工具调用参数字符串。

    替代了不安全的 eval()，采用双重解析策略：
    1. 先将 JS 风格布尔值/null 转换为 Python 风格 (true→True, false→False, null→None)
    2. 优先使用 json.loads() 解析（最安全）
    3. 若 json.loads 失败，回退到 ast.literal_eval()（仅解析字面量，不执行代码）

    Args:
        args_str: LLM 返回的参数字符串，通常为 JSON 格式

    Returns:
        解析后的字典；解析失败时返回空字典 {}
    """
    if not args_str or not args_str.strip():
        return {}
    normalized = (
        args_str
        .replace("true", "True")
        .replace("false", "False")
        .replace("null", "None")
    )
    try:
        return json.loads(normalized)
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        return ast.literal_eval(normalized)
    except (ValueError, SyntaxError):
        return {}


class Model:
    """
    LLM 模型封装类。

    从环境变量读取模型配置，初始化 LangChain 实例。
    环境变量要求：
      - LLM_MODEL: 模型名称（如 deepseek-chat）
      - LLM_API_KEY: API 密钥
      - LLM_BASE_URL: API 基础地址
    """

    def __init__(self):
        try:
            self.model_name = os.getenv("LLM_MODEL")
            self.api_key = os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("LLM_BASE_URL")

            if not all([self.model_name, self.api_key, self.base_url]):
                raise ValueError("缺少必要的环境变量")

            self.llm = init_chat_model(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60,
                stream_usage=True,
            )
            logger.info("使用模型: %s", self.model_name)
        except KeyError as e:
            raise ValueError(f"缺少必要的环境变量: {e}")


class Agent:
    """
    ReAct 模式智能体。

    核心工作流程：
      用户输入 → LLM 推理 → 判断是否需要调用工具 → 执行工具 → 将结果反馈给 LLM → 重复直到 LLM 不再调用工具

    提供三种运行模式：
      - React_Agent:         同步阻塞调用，等待完整响应后返回
      - React_Agent_Stream:  终端流式输出，边生成边打印
      - React_Agent_Stream_UI: SSE 流式输出，通过 yield 向前端推送事件

    Args:
        model: Model 实例，封装了 LLM 连接
        tools: 工具函数列表（LangChain StructuredTool 实例）
        max_memory: 对话记忆最大条数，超出时保留 SystemPrompt + 最近的 N-1 条
        max_iterations: 流式模式下最大工具调用迭代次数，防止无限循环
    """

    def __init__(self, model: Model, tools: List[Callable], max_memory: int = 50, max_iterations: int = 10):
        self.model = model
        self.tools_list = tools
        self.max_memory = max_memory
        self.max_iterations = max_iterations

        with open("src/core/prompts/React_prompt.md", "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

        self.llm_with_tools = self.model.llm.bind_tools(self.tools_list)

        self.memory = [SystemMessage(content=self.system_prompt)]

    def _trim_memory(self):
        """裁剪对话记忆：保留 SystemPrompt + 最近 (max_memory-1) 条消息"""
        if len(self.memory) > self.max_memory:
            self.memory = [self.memory[0]] + self.memory[-(self.max_memory - 1):]

    def clear_memory(self):
        """清空对话记忆，仅保留 SystemPrompt"""
        self.memory = [SystemMessage(content=self.system_prompt)]
        logger.info("记忆已清空")

    def sync_memory_from_conversation(self, messages: list):
        """
        从外部对话记录同步记忆（用于前端恢复会话上下文）。

        将前端存储的对话消息转换为 LangChain Message 对象，重建 Agent 的对话记忆。
        assistant 消息中的 segments（文本段 + 工具调用段）会被合并为纯文本。

        Args:
            messages: 前端传入的对话消息列表，每条包含 role/content/segments 等字段
        """
        self.memory = [SystemMessage(content=self.system_prompt)]

        if not isinstance(messages, list):
            return

        def _assistant_to_text(msg: dict) -> str:
            """将 assistant 消息的 segments 合并为纯文本，保留工具调用结果"""
            if not isinstance(msg, dict):
                return ""

            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

            segs = msg.get("segments")
            if not isinstance(segs, list):
                return ""

            parts = []
            for seg in segs:
                if not isinstance(seg, dict):
                    continue
                if seg.get("type") == "text":
                    text = str(seg.get("content", "")).strip()
                    if text:
                        parts.append(text)
                elif seg.get("type") == "tool_call":
                    name = str(seg.get("name", "tool")).strip()
                    result = str(seg.get("result", "")).strip()
                    if result:
                        parts.append(f"[工具 {name} 返回]\n{result}")

            return "\n\n".join(parts).strip()

        max_rebuild = max(1, self.max_memory - 1)
        for msg in messages[-max_rebuild:]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")

            if role == "user":
                text = str(msg.get("content", "")).strip()
                if text:
                    self.memory.append(HumanMessage(content=text))
            elif role == "assistant":
                text = _assistant_to_text(msg)
                if text:
                    self.memory.append(AIMessage(content=text))

        self._trim_memory()

    def get_memory_count(self) -> int:
        """获取当前记忆条数（不含 SystemPrompt）"""
        return len(self.memory) - 1

    def get_memory_status(self) -> dict:
        """获取记忆状态摘要，供前端展示"""
        return {
            "current_count": self.get_memory_count(),
            "max_memory": self.max_memory,
            "remaining": self.max_memory - self.get_memory_count(),
        }

    # ==================== 公共工具方法 ====================

    @staticmethod
    def _extract_token_usage(chunk_or_msg) -> dict:
        """
        从 LLM 响应中提取 Token 消耗量。

        兼容两种数据来源：
        1. usage_metadata（LangChain 新版，stream_usage=True 时在最后一个 chunk 中提供）
        2. response_metadata.token_usage（OpenAI API 传统格式）

        Args:
            chunk_or_msg: AIMessage / AIMessageChunk 对象

        Returns:
            {"input_tokens": int, "output_tokens": int}
        """
        usage_meta = getattr(chunk_or_msg, "usage_metadata", None)
        if usage_meta:
            input_tokens = usage_meta.get("input_tokens", 0) or 0
            output_tokens = usage_meta.get("output_tokens", 0) or 0
            if input_tokens > 0 or output_tokens > 0:
                return {"input_tokens": input_tokens, "output_tokens": output_tokens}

        resp_meta = getattr(chunk_or_msg, "response_metadata", None)
        if resp_meta:
            token_usage = resp_meta.get("token_usage", {}) or resp_meta.get("usage", {})
            if token_usage and isinstance(token_usage, dict):
                input_tokens = token_usage.get("prompt_tokens", 0) or token_usage.get("input_tokens", 0) or 0
                output_tokens = token_usage.get("completion_tokens", 0) or token_usage.get("output_tokens", 0) or 0
                if input_tokens > 0 or output_tokens > 0:
                    return {"input_tokens": input_tokens, "output_tokens": output_tokens}

        return {"input_tokens": 0, "output_tokens": 0}

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        粗略估算文本的 Token 数（当 API 未返回 Token 统计时的降级方案）。

        估算规则：
          - 中文字符：1 个字 ≈ 1.5 tokens
          - 其他字符：1 个字符 ≈ 0.25 tokens

        Args:
            text: 待估算的文本

        Returns:
            估算的 Token 数
        """
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.25)

    def _messages_to_text(self, messages: list) -> str:
        """
        将 LangChain Message 列表序列化为纯文本，用于 Token 估算。

        每条消息格式为 [Role] content，工具调用会内联显示。
        """
        parts = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                parts.append(f"[System] {msg.content}")
            elif isinstance(msg, HumanMessage):
                parts.append(f"[Human] {msg.content}")
            elif isinstance(msg, AIMessage):
                content = msg.content or ""
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content += f" [ToolCall: {tc.get('name', '')}({tc.get('args', '')})]"
                parts.append(f"[AI] {content}")
            elif isinstance(msg, ToolMessage):
                parts.append(f"[Tool] {msg.content}")
        return "\n".join(parts)

    @staticmethod
    def _format_token_info(total_input: int, total_output: int, llm_calls: int, estimated: bool = False) -> str:
        """
        格式化 Token 消耗统计信息，用于终端输出。
        """
        total_tokens = total_input + total_output
        tag = " (估算)" if estimated else ""
        return (
            f"\n{'─' * 40}\n"
            f"📊 Token消耗统计{tag} | LLM调用次数: {llm_calls}\n"
            f"   输入: {total_input:,} tokens | 输出: {total_output:,} tokens | 合计: {total_tokens:,} tokens\n"
            f"{'─' * 40}"
        )

    @staticmethod
    def _parse_tool_call_chunks(tool_calls_chunks: list) -> dict:
        """
        将流式响应中的 tool_call_chunks 碎片组装为完整的工具调用字典。

        流式模式下，LLM 的工具调用参数是分多个 chunk 逐步返回的，
        需要按 index 分组并拼接 args 字符串。

        Args:
            tool_calls_chunks: 包含 tool_call_chunks 属性的 AIMessageChunk 列表

        Returns:
            {index: {"id": str, "name": str, "args": str}} —— args 为拼接后的完整 JSON 字符串
        """
        tool_calls_dict = {}
        for chunk in tool_calls_chunks:
            for tc_chunk in chunk.tool_call_chunks:
                idx = tc_chunk.get("index", 0)
                if idx not in tool_calls_dict:
                    tool_calls_dict[idx] = {
                        "id": tc_chunk.get("id", ""),
                        "name": tc_chunk.get("name", ""),
                        "args": "",
                    }
                if tc_chunk.get("args"):
                    tool_calls_dict[idx]["args"] += tc_chunk["args"]
        return tool_calls_dict

    @staticmethod
    def _build_ai_message(full_content: str, tool_calls_dict: dict) -> AIMessage:
        """
        根据完整文本和工具调用字典构建 AIMessage 对象。

        若存在工具调用，使用 AIMessageChunk 并附加 tool_calls 属性，
        参数字符串通过 _safe_parse_json_args 安全解析为 dict。

        Args:
            full_content: LLM 返回的完整文本内容
            tool_calls_dict: 由 _parse_tool_call_chunks 组装的字典

        Returns:
            AIMessage 或 AIMessageChunk 对象
        """
        if tool_calls_dict:
            ai_msg = AIMessageChunk(content=full_content)
            ai_msg.tool_calls = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "args": _safe_parse_json_args(tc["args"]),
                }
                for tc in tool_calls_dict.values()
            ]
        else:
            ai_msg = AIMessage(content=full_content)
        return ai_msg

    def _execute_tool_call(self, tool_call: dict, session_logger=None) -> tuple:
        """
        执行单个工具调用并将结果加入对话记忆。

        Args:
            tool_call: {"id": str, "name": str, "args": dict}
            session_logger: 可选的会话日志记录器

        Returns:
            (tool_name, result_content) 工具名和执行结果文本
        """
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        logger.info("调用工具: %s(%s)", tool_name, tool_args)

        if session_logger:
            session_logger.log_tool_call(
                call_index=0,
                tool_name=tool_name,
                tool_args=tool_args,
            )

        tool_func = next((t for t in self.tools_list if t.name == tool_name), None)
        result_content = ""
        if tool_func:
            tool_result = tool_func.invoke(tool_args)
            result_content = tool_result.content if hasattr(tool_result, "content") else str(tool_result)
            logger.info("工具返回: %s", result_content)

            if session_logger:
                session_logger.log_tool_result(
                    tool_name=tool_name,
                    result_length=len(result_content),
                    result_preview=result_content,
                )

        tool_message = ToolMessage(content=result_content, tool_call_id=tool_id)
        self.memory.append(tool_message)

        return tool_name, result_content

    @staticmethod
    def _accumulate_token_usage(usage_chunk: Optional[dict], last_chunk, current_input: int, current_output: int) -> Tuple[int, int]:
        """
        累加 Token 消耗量。

        优先使用流式中间 chunk 的 usage 数据，若无则从最后一个 chunk 提取。

        Args:
            usage_chunk: 流式中间捕获到的 usage 字典，可能为 None
            last_chunk: 流式响应的最后一个 chunk，用于降级提取
            current_input: 当前已累计的输入 Token 数
            current_output: 当前已累计的输出 Token 数

        Returns:
            (updated_input, updated_output) 累加后的 Token 数
        """
        if usage_chunk:
            return current_input + usage_chunk["input_tokens"], current_output + usage_chunk["output_tokens"]
        if last_chunk is not None:
            token_usage = Agent._extract_token_usage(last_chunk)
            return current_input + token_usage["input_tokens"], current_output + token_usage["output_tokens"]
        return current_input, current_output

    # ==================== Agent 运行方法 ====================

    def React_Agent(self, user_input: str):
        """
        同步阻塞模式运行 Agent。

        调用 LLM 并等待完整响应，若 LLM 请求调用工具则执行后再次调用 LLM，
        循环直到 LLM 不再调用工具为止。

        流程：
          1. 将用户输入加入记忆
          2. 启动 RAG 会话和日志会话
          3. 调用 LLM → 若有工具调用则执行 → 重复
          4. 统计 Token 消耗并记录日志
          5. 返回 LLM 最终文本响应

        Args:
            user_input: 用户输入文本

        Returns:
            LLM 最终回复的文本内容
        """
        self.memory.append(HumanMessage(content=user_input))
        self._trim_memory()

        rag_session_id = str(uuid.uuid4())
        start_rag_session(rag_session_id)

        log_session_id = str(uuid.uuid4())
        session_logger = start_session(log_session_id)
        session_logger.log_user_input(user_input)

        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        is_estimated = False

        try:
            ai_msg = self.llm_with_tools.invoke(self.memory)
            self.memory.append(ai_msg)

            token_usage = self._extract_token_usage(ai_msg)
            total_input_tokens += token_usage["input_tokens"]
            total_output_tokens += token_usage["output_tokens"]
            llm_calls += 1
            session_logger.log_llm_call(
                call_index=llm_calls,
                input_tokens=token_usage["input_tokens"],
                output_tokens=token_usage["output_tokens"],
                estimated=False,
                content_preview=ai_msg.content or "",
            )

            while ai_msg.tool_calls:
                for tool_call in ai_msg.tool_calls:
                    self._execute_tool_call(tool_call, session_logger)

                ai_msg = self.llm_with_tools.invoke(self.memory)
                self.memory.append(ai_msg)
                self._trim_memory()

                token_usage = self._extract_token_usage(ai_msg)
                total_input_tokens += token_usage["input_tokens"]
                total_output_tokens += token_usage["output_tokens"]
                llm_calls += 1
                session_logger.log_llm_call(
                    call_index=llm_calls,
                    input_tokens=token_usage["input_tokens"],
                    output_tokens=token_usage["output_tokens"],
                    estimated=False,
                    content_preview=ai_msg.content or "",
                )

            if total_input_tokens == 0 and total_output_tokens == 0:
                is_estimated = True
                input_text = self._messages_to_text(self.memory)
                total_input_tokens = self._estimate_tokens(input_text)
                total_output_tokens = self._estimate_tokens(ai_msg.content or "")

            session_logger.log_session_end(
                total_llm_calls=llm_calls,
                total_input=total_input_tokens,
                total_output=total_output_tokens,
                estimated=is_estimated,
            )

            return ai_msg.content
        finally:
            end_rag_session(rag_session_id)
            end_session(log_session_id)

    def React_Agent_Stream(self, user_input: str):
        """
        终端流式模式运行 Agent。

        与 React_Agent 类似，但 LLM 响应通过流式输出逐字打印到终端。
        支持多轮工具调用，设有最大迭代次数限制防止无限循环。

        流程：
          1. 将用户输入加入记忆
          2. 循环：流式调用 LLM → 逐字打印 → 解析工具调用 → 执行工具
          3. 当 LLM 不再调用工具或达到最大迭代次数时退出
          4. 打印 Token 消耗统计

        Args:
            user_input: 用户输入文本

        Returns:
            LLM 最终回复的文本内容
        """
        self.memory.append(HumanMessage(content=user_input))
        self._trim_memory()

        rag_session_id = str(uuid.uuid4())
        start_rag_session(rag_session_id)

        log_session_id = str(uuid.uuid4())
        session_logger = start_session(log_session_id)
        session_logger.log_user_input(user_input)

        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        all_output_text = ""
        is_estimated = False
        iteration_count = 0

        try:
            while True:
                iteration_count += 1
                if iteration_count > self.max_iterations:
                    print(f"\n[达到最大迭代次数 {self.max_iterations}，停止工具调用]")
                    break

                full_content = ""
                tool_calls_chunks = []
                last_chunk = None
                usage_chunk = None

                for chunk in self.llm_with_tools.stream(self.memory, stream_usage=True):
                    if chunk.content:
                        print(chunk.content, end="", flush=True)
                        full_content += chunk.content

                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if not reasoning_content:
                        additional_kwargs = getattr(chunk, "additional_kwargs", None)
                        if additional_kwargs and isinstance(additional_kwargs, dict):
                            reasoning_content = additional_kwargs.get("reasoning_content")
                    
                    if reasoning_content:
                        print(f"\033[90m{reasoning_content}\033[0m", end="", flush=True)

                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        tool_calls_chunks.append(chunk)

                    chunk_usage = self._extract_token_usage(chunk)
                    if chunk_usage["input_tokens"] > 0 or chunk_usage["output_tokens"] > 0:
                        usage_chunk = chunk_usage

                    last_chunk = chunk

                print()

                total_input_tokens, total_output_tokens = self._accumulate_token_usage(
                    usage_chunk, last_chunk, total_input_tokens, total_output_tokens,
                )
                llm_calls += 1
                all_output_text += full_content

                logged_input = usage_chunk["input_tokens"] if usage_chunk else (self._extract_token_usage(last_chunk)["input_tokens"] if last_chunk else 0)
                logged_output = usage_chunk["output_tokens"] if usage_chunk else (self._extract_token_usage(last_chunk)["output_tokens"] if last_chunk else 0)
                session_logger.log_llm_call(
                    call_index=llm_calls,
                    input_tokens=logged_input,
                    output_tokens=logged_output,
                    estimated=False,
                    content_preview=full_content,
                )

                tool_calls_dict = self._parse_tool_call_chunks(tool_calls_chunks)
                ai_msg = self._build_ai_message(full_content, tool_calls_dict)

                self.memory.append(ai_msg)
                self._trim_memory()

                if not ai_msg.tool_calls:
                    break

                for tool_call in ai_msg.tool_calls:
                    self._execute_tool_call(tool_call, session_logger)

            if total_input_tokens == 0 and total_output_tokens == 0:
                is_estimated = True
                input_text = self._messages_to_text(self.memory)
                total_input_tokens = self._estimate_tokens(input_text)
                total_output_tokens = self._estimate_tokens(all_output_text)

            session_logger.log_session_end(
                total_llm_calls=llm_calls,
                total_input=total_input_tokens,
                total_output=total_output_tokens,
                estimated=is_estimated,
            )

            print(self._format_token_info(total_input_tokens, total_output_tokens, llm_calls, is_estimated))

            return ai_msg.content
        finally:
            end_rag_session(rag_session_id)
            end_session(log_session_id)

    def React_Agent_Stream_UI(self, user_input: str):
        """
        SSE 流式模式运行 Agent（供前端消费）。

        通过 generator yield 事件元组向前端推送实时数据，事件类型包括：
          - ("content", str):        文本内容增量
          - ("reasoning", str):      推理过程增量（如 DeepSeek 的思维链）
          - ("tool_call", dict):     工具调用通知 {"name": str, "args": dict}
          - ("tool_result", dict):   工具执行结果 {"name": str, "result": str}
          - ("token_stats", dict):   Token 消耗统计

        与 React_Agent_Stream 的区别：
          - 不直接 print，而是 yield 事件供 Flask SSE 推送
          - 支持推理内容（reasoning_content）输出
          - 工具调用结果也通过 yield 推送给前端

        Args:
            user_input: 用户输入文本

        Yields:
            (event_type, data) 事件元组
        """
        self.memory.append(HumanMessage(content=user_input))
        self._trim_memory()

        rag_session_id = str(uuid.uuid4())
        start_rag_session(rag_session_id)

        log_session_id = str(uuid.uuid4())
        session_logger = start_session(log_session_id)
        session_logger.log_user_input(user_input)

        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        all_output_text = ""
        is_estimated = False

        try:
            while True:
                full_content = ""
                full_reasoning = ""
                tool_calls_chunks = []
                last_chunk = None
                usage_chunk = None

                yield ("phase", {"type": "thinking"})

                has_reasoning = False
                for chunk in self.llm_with_tools.stream(self.memory, stream_usage=True):
                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if not reasoning_content:
                        additional_kwargs = getattr(chunk, "additional_kwargs", None)
                        if additional_kwargs and isinstance(additional_kwargs, dict):
                            reasoning_content = additional_kwargs.get("reasoning_content")
                    
                    if reasoning_content:
                        if not has_reasoning:
                            has_reasoning = True
                        full_reasoning += reasoning_content
                        yield ("reasoning", reasoning_content)
                    elif chunk.content:
                        if has_reasoning:
                            yield ("phase", {"type": "responding"})
                            has_reasoning = False
                        full_content += chunk.content
                        yield ("content", chunk.content)

                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        tool_calls_chunks.append(chunk)

                    chunk_usage = self._extract_token_usage(chunk)
                    if chunk_usage["input_tokens"] > 0 or chunk_usage["output_tokens"] > 0:
                        usage_chunk = chunk_usage

                    last_chunk = chunk

                total_input_tokens, total_output_tokens = self._accumulate_token_usage(
                    usage_chunk, last_chunk, total_input_tokens, total_output_tokens,
                )
                llm_calls += 1
                all_output_text += full_content

                logged_input = usage_chunk["input_tokens"] if usage_chunk else (self._extract_token_usage(last_chunk)["input_tokens"] if last_chunk else 0)
                logged_output = usage_chunk["output_tokens"] if usage_chunk else (self._extract_token_usage(last_chunk)["output_tokens"] if last_chunk else 0)
                session_logger.log_llm_call(
                    call_index=llm_calls,
                    input_tokens=logged_input,
                    output_tokens=logged_output,
                    estimated=False,
                    content_preview=full_content,
                )

                tool_calls_dict = self._parse_tool_call_chunks(tool_calls_chunks)
                ai_msg = self._build_ai_message(full_content, tool_calls_dict)

                self.memory.append(ai_msg)
                self._trim_memory()

                if not ai_msg.tool_calls:
                    yield ("phase", {"type": "done"})
                    break

                for tool_call in ai_msg.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call["id"]

                    yield ("phase", {"type": "tool_call", "name": tool_name})
                    yield ("tool_call", {"name": tool_name, "args": tool_args})

                    session_logger.log_tool_call(
                        call_index=llm_calls,
                        tool_name=tool_name,
                        tool_args=tool_args,
                    )

                    tool_func = next((t for t in self.tools_list if t.name == tool_name), None)
                    if tool_func:
                        tool_result = tool_func.invoke(tool_args)
                        result_content = tool_result.content if hasattr(tool_result, "content") else str(tool_result)
                        yield ("tool_result", {"name": tool_name, "result": result_content})

                        session_logger.log_tool_result(
                            tool_name=tool_name,
                            result_length=len(result_content),
                            result_preview=result_content,
                        )

                        tool_message = ToolMessage(content=result_content, tool_call_id=tool_id)
                        self.memory.append(tool_message)

            if total_input_tokens == 0 and total_output_tokens == 0:
                is_estimated = True
                input_text = self._messages_to_text(self.memory)
                total_input_tokens = self._estimate_tokens(input_text)
                total_output_tokens = self._estimate_tokens(all_output_text)

            yield ("token_stats", {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "llm_calls": llm_calls,
                "estimated": is_estimated,
            })

            session_logger.log_session_end(
                total_llm_calls=llm_calls,
                total_input=total_input_tokens,
                total_output=total_output_tokens,
                estimated=is_estimated,
            )
        finally:
            end_rag_session(rag_session_id)
            end_session(log_session_id)


if __name__ == "__main__":
    model = Model()
    agent = Agent(model, [
        get_current_time,
        get_search_results,
        create_file,
        overwrite_file,
        read_file,
        delete_file,
        list_files,
        calculate,
        calculate_percentage,
        calculate_average,
        get_deepseek_balance,
        get_deepseek_usage,
        rag_ingest_document,
        rag_query,
        rag_list_documents,
        rag_delete_document,
    ])

    print("多轮对话已启动（输入 'exit' 退出，'clear' 清空记忆，'status' 查看记忆状态）\n")

    while True:
        user_input = input("请输入您的问题：").strip()

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("对话结束")
            break

        if user_input.lower() == "clear":
            agent.clear_memory()
            continue

        if user_input.lower() == "status":
            status = agent.get_memory_status()
            print(f"记忆状态: {status['current_count']}/{status['max_memory']} (剩余: {status['remaining']})")
            continue

        print()
        response = agent.React_Agent_Stream(user_input)
        print()
