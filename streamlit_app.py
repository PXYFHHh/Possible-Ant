import streamlit as st
import sys
import os
import json
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.agent import Model, Agent
from src.core.tools import (
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
)

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

BASE_DIR = Path(__file__).resolve().parent
FILES_DIR = BASE_DIR / "files"

st.set_page_config(
    page_title="AI 智能助手",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stChatMessage { padding: 0.5rem 0; }
    .token-stats-box {
        background: linear-gradient(135deg, #2d1b69 0%, #1a1a2e 100%);
        border: 1px solid #7b2cbf;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 8px 0;
        font-size: 0.85rem;
    }
    .token-stats-label { color: #c77dff; font-weight: 600; }
    .token-stats-value { color: #e0aaff; font-family: 'Consolas', monospace; }
</style>
""", unsafe_allow_html=True)


def init_agent():
    if "agent" not in st.session_state:
        model = Model()
        agent = Agent(model, ALL_TOOLS)
        st.session_state.agent = agent
        st.session_state.messages = []
        st.session_state.total_input_tokens = 0
        st.session_state.total_output_tokens = 0
        st.session_state.total_llm_calls = 0


def get_conversation_turns():
    turns = 0
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            turns += 1
    return turns


def render_sidebar():
    with st.sidebar:
        st.title("🤖 AI 智能助手")
        st.caption("基于 LangChain + DeepSeek 的多工具智能代理")
        
        st.markdown("---")
        
        st.subheader("📊 会话统计")
        turns = get_conversation_turns()
        stats = st.session_state.agent.get_memory_status()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("对话轮次", turns)
        with col2:
            st.metric("记忆消息数", f"{stats['current_count']}/{stats['max_memory']}")
        
        col3, col4 = st.columns(2)
        with col3:
            st.metric("输入 Tokens", f"{st.session_state.total_input_tokens:,}")
        with col4:
            st.metric("输出 Tokens", f"{st.session_state.total_output_tokens:,}")
        
        st.metric("LLM 调用次数", st.session_state.total_llm_calls)
        
        st.markdown("---")

        st.subheader("📚 知识库")
        FILES_DIR.mkdir(parents=True, exist_ok=True)
        uploaded_file = st.file_uploader(
            "上传文档并入库",
            type=["txt", "md", "pdf", "docx"],
            accept_multiple_files=False,
            key="rag_upload_file",
        )

        if uploaded_file is not None:
            save_name = os.path.basename(uploaded_file.name)
            save_path = FILES_DIR / save_name

            if st.button("📥 上传并入库", use_container_width=True):
                try:
                    save_path.write_bytes(uploaded_file.getbuffer())
                    ingest_result = rag_ingest_document.invoke({"filename": save_name})
                    if ingest_result.startswith("✅"):
                        st.success(ingest_result)
                    else:
                        st.error(ingest_result)
                except Exception as exc:
                    st.error(f"上传失败: {exc}")

        if st.button("🔄 刷新知识库", use_container_width=True):
            st.rerun()

        kb_text = rag_list_documents.invoke({})
        with st.expander("已入库文档", expanded=False):
            st.text(kb_text)

        st.markdown("---")
        
        col_clear, col_new = st.columns(2)
        with col_clear:
            if st.button("🗑️ 清空记忆", use_container_width=True):
                st.session_state.agent.clear_memory()
                st.session_state.messages = []
                st.session_state.total_input_tokens = 0
                st.session_state.total_output_tokens = 0
                st.session_state.total_llm_calls = 0
                st.rerun()
        with col_new:
            if st.button("🆕 新对话", use_container_width=True):
                init_agent()
                st.rerun()


def render_segments(segments):
    for seg in segments:
        if seg["type"] == "text" and seg["content"].strip():
            st.markdown(seg["content"])
        elif seg["type"] == "tool_call":
            result_text = seg.get("result", "")
            if len(result_text) > 2000:
                result_text = result_text[:2000] + "\n... (已截断)"
            with st.status(f"🔧 {seg['name']}", expanded=False, state="complete"):
                st.markdown("**参数：**")
                st.code(seg["args"], language="json")
                st.markdown("**返回结果：**")
                st.code(result_text)


def render_messages():
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        elif msg["role"] == "assistant":
            with st.chat_message("assistant"):
                segments = msg.get("segments", [])
                if segments:
                    render_segments(segments)
                else:
                    st.markdown(msg.get("content", ""))
                
                if "token_stats" in msg:
                    ts = msg["token_stats"]
                    tag = " (估算)" if ts.get("estimated") else ""
                    total = ts["input_tokens"] + ts["output_tokens"]
                    st.markdown(
                        f'<div class="token-stats-box">'
                        f'<span class="token-stats-label">📊 Token消耗{tag}</span> | '
                        f'LLM调用: <span class="token-stats-value">{ts["llm_calls"]}</span> | '
                        f'输入: <span class="token-stats-value">{ts["input_tokens"]:,}</span> | '
                        f'输出: <span class="token-stats-value">{ts["output_tokens"]:,}</span> | '
                        f'合计: <span class="token-stats-value">{total:,}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )


def handle_chat():
    if prompt := st.chat_input("输入您的问题..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            content_placeholder = st.empty()
            full_response = ""
            finalized_length = 0
            segments = []
            token_stats = None
            current_tool_status = None
            current_tool_result_holder = None
            
            try:
                for event_type, data in st.session_state.agent.React_Agent_Stream_UI(prompt):
                    if event_type == "content":
                        full_response += data
                        current_section = full_response[finalized_length:]
                        content_placeholder.markdown(current_section + "▌")
                    
                    elif event_type == "tool_call":
                        current_section = full_response[finalized_length:]
                        if current_section.strip():
                            content_placeholder.markdown(current_section)
                            segments.append({"type": "text", "content": current_section})
                        else:
                            content_placeholder.empty()
                        finalized_length = len(full_response)
                        
                        args_str = json.dumps(data["args"], ensure_ascii=False, indent=2)
                        
                        with st.status(f"🔧 调用工具: {data['name']}...", expanded=True) as status:
                            st.markdown("**参数：**")
                            st.code(args_str, language="json")
                            result_holder = st.empty()
                            current_tool_status = status
                            current_tool_result_holder = result_holder
                        
                        segments.append({
                            "type": "tool_call",
                            "name": data["name"],
                            "args": args_str,
                            "result": ""
                        })
                    
                    elif event_type == "tool_result":
                        result_text = data["result"]
                        if len(result_text) > 2000:
                            display_text = result_text[:2000] + "\n... (已截断)"
                        else:
                            display_text = result_text
                        
                        current_tool_result_holder.markdown("**返回结果：**")
                        current_tool_result_holder.code(display_text)
                        current_tool_status.update(
                            label=f"✅ {data['name']} 完成",
                            state="complete",
                            expanded=False
                        )
                        
                        for seg in reversed(segments):
                            if seg["type"] == "tool_call" and seg["name"] == data["name"] and not seg["result"]:
                                seg["result"] = result_text
                                break
                        
                        content_placeholder = st.empty()
                    
                    elif event_type == "token_stats":
                        token_stats = data
                        st.session_state.total_input_tokens += data["input_tokens"]
                        st.session_state.total_output_tokens += data["output_tokens"]
                        st.session_state.total_llm_calls += data["llm_calls"]
                
                current_section = full_response[finalized_length:]
                if current_section.strip():
                    content_placeholder.markdown(current_section)
                    segments.append({"type": "text", "content": current_section})
                else:
                    content_placeholder.empty()
                
                if token_stats:
                    tag = " (估算)" if token_stats.get("estimated") else ""
                    total = token_stats["input_tokens"] + token_stats["output_tokens"]
                    st.markdown(
                        f'<div class="token-stats-box">'
                        f'<span class="token-stats-label">📊 Token消耗{tag}</span> | '
                        f'LLM调用: <span class="token-stats-value">{token_stats["llm_calls"]}</span> | '
                        f'输入: <span class="token-stats-value">{token_stats["input_tokens"]:,}</span> | '
                        f'输出: <span class="token-stats-value">{token_stats["output_tokens"]:,}</span> | '
                        f'合计: <span class="token-stats-value">{total:,}</span>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                
                assistant_msg = {
                    "role": "assistant",
                    "content": full_response,
                    "segments": segments
                }
                if token_stats:
                    assistant_msg["token_stats"] = token_stats
                st.session_state.messages.append(assistant_msg)
                
            except Exception as e:
                error_msg = f"❌ 发生错误: {str(e)}"
                content_placeholder.markdown(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg, "segments": [{"type": "text", "content": error_msg}]})


def main():
    init_agent()
    render_sidebar()
    render_messages()
    handle_chat()


if __name__ == "__main__":
    main()
