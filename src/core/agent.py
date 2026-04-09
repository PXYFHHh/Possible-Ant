from langchain.chat_models import init_chat_model
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
    list_files
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
            
            self.llm = init_chat_model(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60
            )
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
        
        while True:
            full_content = ""
            tool_calls_chunks = []
            
            for chunk in self.llm_with_tools.stream(self.memory):
                if chunk.content:
                    print(chunk.content, end="", flush=True)
                    full_content += chunk.content
                
                if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                    tool_calls_chunks.append(chunk)
            
            print()
            
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
                        'args': eval(tc['args']) if tc['args'] else {}
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
                    tool_message = ToolMessage(
                        content=result_content,
                        tool_call_id=tool_id
                    )
                    self.memory.append(tool_message)
        
        return ai_msg.content


if __name__ == "__main__":
    model = Model()
    agent = Agent(model, [
        get_current_time, 
        get_search_results,
        create_file,
        overwrite_file,
        read_file,
        delete_file,
        list_files
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

