from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage, SystemMessage
from typing import List, Callable
import os
import sys
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

load_dotenv()


class Model:
    def __init__(self):
        try:
            self.model_name = os.getenv("LLM_MODEL")
            self.api_key = os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("LLM_BASE_URL")
            
            if not all([self.model_name, self.api_key, self.base_url]):
                raise ValueError("缺少必要的环境变量")
            
            self.llm = ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60,
                stream_usage=True
            )
            print(f"使用模型: {self.model_name}")
        except KeyError as e:
            raise ValueError(f"缺少必要的环境变量: {e}")


class Agent:
    def __init__(self, model: Model, tools: List[Callable], max_memory: int = 50):
        self.model = model
        self.tools_list = tools
        self.max_memory = max_memory
        
        with open("src/core/prompts/React_prompt.md", "r", encoding="utf-8") as f:
            self.system_prompt = f.read()
        
        self.llm_with_tools = self.model.llm.bind_tools(self.tools_list)
        
        self.memory = [SystemMessage(content=self.system_prompt)]
    
    def _trim_memory(self):
        if len(self.memory) > self.max_memory:
            self.memory = [self.memory[0]] + self.memory[-(self.max_memory-1):]
    
    def clear_memory(self):
        self.memory = [SystemMessage(content=self.system_prompt)]
        print("记忆已清空")
    
    def get_memory_count(self) -> int:
        return len(self.memory) - 1
    
    def get_memory_status(self) -> dict:
        return {
            "current_count": self.get_memory_count(),
            "max_memory": self.max_memory,
            "remaining": self.max_memory - self.get_memory_count()
        }

    def _extract_token_usage(self, chunk_or_msg) -> dict:
        usage_meta = getattr(chunk_or_msg, 'usage_metadata', None)
        if usage_meta:
            input_tokens = usage_meta.get('input_tokens', 0) or 0
            output_tokens = usage_meta.get('output_tokens', 0) or 0
            if input_tokens > 0 or output_tokens > 0:
                return {"input_tokens": input_tokens, "output_tokens": output_tokens}

        resp_meta = getattr(chunk_or_msg, 'response_metadata', None)
        if resp_meta:
            token_usage = resp_meta.get('token_usage', {}) or resp_meta.get('usage', {})
            if token_usage and isinstance(token_usage, dict):
                input_tokens = token_usage.get('prompt_tokens', 0) or token_usage.get('input_tokens', 0) or 0
                output_tokens = token_usage.get('completion_tokens', 0) or token_usage.get('output_tokens', 0) or 0
                if input_tokens > 0 or output_tokens > 0:
                    return {"input_tokens": input_tokens, "output_tokens": output_tokens}

        return {"input_tokens": 0, "output_tokens": 0}

    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.25)

    def _messages_to_text(self, messages: list) -> str:
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

    def _format_token_info(self, total_input: int, total_output: int, llm_calls: int, estimated: bool = False) -> str:
        total_tokens = total_input + total_output
        tag = " (估算)" if estimated else ""
        return (
            f"\n{'─' * 40}\n"
            f"📊 Token消耗统计{tag} | LLM调用次数: {llm_calls}\n"
            f"   输入: {total_input:,} tokens | 输出: {total_output:,} tokens | 合计: {total_tokens:,} tokens\n"
            f"{'─' * 40}"
        )

    def React_Agent(self, user_input: str):
        self.memory.append(HumanMessage(content=user_input))
        self._trim_memory()
        
        ai_msg = self.llm_with_tools.invoke(self.memory)
        self.memory.append(ai_msg)
        
        while ai_msg.tool_calls:
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                print(f"调用工具: {tool_name}({tool_args})")
                
                tool_func = next((t for t in self.tools_list if t.name == tool_name), None)
                if tool_func:
                    tool_result = tool_func.invoke(tool_args)
                    result_content = tool_result.content if hasattr(tool_result, 'content') else str(tool_result)
                    print(f"工具返回: {result_content}\n")
                    tool_message = ToolMessage(
                        content=result_content,
                        tool_call_id=tool_id
                    )
                    self.memory.append(tool_message)
            
            ai_msg = self.llm_with_tools.invoke(self.memory)
            self.memory.append(ai_msg)
            self._trim_memory()
        
        return ai_msg.content

    def React_Agent_Stream(self, user_input: str):
        self.memory.append(HumanMessage(content=user_input))
        self._trim_memory()
        
        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        all_output_text = ""
        is_estimated = False
        
        while True:
            full_content = ""
            tool_calls_chunks = []
            last_chunk = None
            usage_chunk = None
            
            for chunk in self.llm_with_tools.stream(self.memory, stream_usage=True):
                if chunk.content:
                    print(chunk.content, end="", flush=True)
                    full_content += chunk.content
                
                if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                    tool_calls_chunks.append(chunk)
                
                chunk_usage = self._extract_token_usage(chunk)
                if chunk_usage["input_tokens"] > 0 or chunk_usage["output_tokens"] > 0:
                    usage_chunk = chunk_usage
                
                last_chunk = chunk
            
            print()
            
            if usage_chunk:
                total_input_tokens += usage_chunk["input_tokens"]
                total_output_tokens += usage_chunk["output_tokens"]
            elif last_chunk is not None:
                token_usage = self._extract_token_usage(last_chunk)
                total_input_tokens += token_usage["input_tokens"]
                total_output_tokens += token_usage["output_tokens"]
            
            llm_calls += 1
            all_output_text += full_content
            
            if tool_calls_chunks:
                from langchain_core.messages import AIMessageChunk
                ai_msg = AIMessageChunk(content=full_content)
                
                tool_calls_dict = {}
                for chunk in tool_calls_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        idx = tc_chunk.get('index', 0)
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                'id': tc_chunk.get('id', ''),
                                'name': tc_chunk.get('name', ''),
                                'args': ''
                            }
                        if tc_chunk.get('args'):
                            tool_calls_dict[idx]['args'] += tc_chunk['args']
                
                ai_msg.tool_calls = [
                    {
                        'id': tc['id'],
                        'name': tc['name'],
                        'args': eval(tc['args'].replace('true', 'True').replace('false', 'False').replace('null', 'None')) if tc['args'] else {}
                    }
                    for tc in tool_calls_dict.values()
                ]
            else:
                ai_msg = AIMessage(content=full_content)
            
            self.memory.append(ai_msg)
            self._trim_memory()
            
            if not ai_msg.tool_calls:
                break
            
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                print(f"\n调用工具: {tool_name}({tool_args})")
                
                tool_func = next((t for t in self.tools_list if t.name == tool_name), None)
                if tool_func:
                    tool_result = tool_func.invoke(tool_args)
                    result_content = tool_result.content if hasattr(tool_result, 'content') else str(tool_result)
                    print(f"工具返回: {result_content}\n")
                    tool_message = ToolMessage(
                        content=result_content,
                        tool_call_id=tool_id
                    )
                    self.memory.append(tool_message)
        
        if total_input_tokens == 0 and total_output_tokens == 0:
            is_estimated = True
            input_text = self._messages_to_text(self.memory)
            total_input_tokens = self._estimate_tokens(input_text)
            total_output_tokens = self._estimate_tokens(all_output_text)
        
        print(self._format_token_info(total_input_tokens, total_output_tokens, llm_calls, is_estimated))
        
        return ai_msg.content

    def React_Agent_Stream_UI(self, user_input: str):
        self.memory.append(HumanMessage(content=user_input))
        self._trim_memory()
        
        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        all_output_text = ""
        is_estimated = False
        
        while True:
            full_content = ""
            tool_calls_chunks = []
            last_chunk = None
            usage_chunk = None
            
            for chunk in self.llm_with_tools.stream(self.memory, stream_usage=True):
                if chunk.content:
                    full_content += chunk.content
                    yield ("content", chunk.content)
                
                if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                    tool_calls_chunks.append(chunk)
                
                chunk_usage = self._extract_token_usage(chunk)
                if chunk_usage["input_tokens"] > 0 or chunk_usage["output_tokens"] > 0:
                    usage_chunk = chunk_usage
                
                last_chunk = chunk
            
            if usage_chunk:
                total_input_tokens += usage_chunk["input_tokens"]
                total_output_tokens += usage_chunk["output_tokens"]
            elif last_chunk is not None:
                token_usage = self._extract_token_usage(last_chunk)
                total_input_tokens += token_usage["input_tokens"]
                total_output_tokens += token_usage["output_tokens"]
            
            llm_calls += 1
            all_output_text += full_content
            
            if tool_calls_chunks:
                from langchain_core.messages import AIMessageChunk
                ai_msg = AIMessageChunk(content=full_content)
                
                tool_calls_dict = {}
                for chunk in tool_calls_chunks:
                    for tc_chunk in chunk.tool_call_chunks:
                        idx = tc_chunk.get('index', 0)
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                'id': tc_chunk.get('id', ''),
                                'name': tc_chunk.get('name', ''),
                                'args': ''
                            }
                        if tc_chunk.get('args'):
                            tool_calls_dict[idx]['args'] += tc_chunk['args']
                
                ai_msg.tool_calls = [
                    {
                        'id': tc['id'],
                        'name': tc['name'],
                        'args': eval(tc['args'].replace('true', 'True').replace('false', 'False').replace('null', 'None')) if tc['args'] else {}
                    }
                    for tc in tool_calls_dict.values()
                ]
            else:
                ai_msg = AIMessage(content=full_content)
            
            self.memory.append(ai_msg)
            self._trim_memory()
            
            if not ai_msg.tool_calls:
                break
            
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                yield ("tool_call", {"name": tool_name, "args": tool_args})
                
                tool_func = next((t for t in self.tools_list if t.name == tool_name), None)
                if tool_func:
                    tool_result = tool_func.invoke(tool_args)
                    result_content = tool_result.content if hasattr(tool_result, 'content') else str(tool_result)
                    yield ("tool_result", {"name": tool_name, "result": result_content})
                    tool_message = ToolMessage(
                        content=result_content,
                        tool_call_id=tool_id
                    )
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
            "estimated": is_estimated
        })


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
        
        if user_input.lower() == 'exit':
            print("对话结束")
            break
        
        if user_input.lower() == 'clear':
            agent.clear_memory()
            continue
        
        if user_input.lower() == 'status':
            status = agent.get_memory_status()
            print(f"记忆状态: {status['current_count']}/{status['max_memory']} (剩余: {status['remaining']})")
            continue
        
        print()
        response = agent.React_Agent_Stream(user_input)
        print()
