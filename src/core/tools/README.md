# 工具模块说明

## 文件结构

```
src/core/tools/
├── __init__.py           # 工具导出
├── get_time.py           # 获取当前时间工具
├── web_search.py         # 网络搜索工具
└── file_manager.py       # 文件管理工具集
```

## 工具列表

### 1. get_time.py - 时间工具
**工具名称**: `get_current_time`

**功能**: 获取当前系统时间

**返回格式**: 
```
现在是 2026年4月10日 星期五 上午 00:44:25
```

**使用示例**:
```python
from src.core.tools import get_current_time

# 直接调用
result = get_current_time.invoke({})

# 在Agent中使用
agent.React_Agent_Stream("现在几点了？")
```

---

### 2. web_search.py - 网络搜索工具
**工具名称**: `get_search_results`

**功能**: 使用DuckDuckGo搜索引擎进行网络搜索

**参数**:
- `query` (str): 搜索关键词

**返回格式**:
```
标题: [新闻标题]
链接: [URL]
摘要: [内容摘要]
```

**使用示例**:
```python
from src.core.tools import get_search_results

# 直接调用
result = get_search_results.invoke({"query": "今日新闻"})

# 在Agent中使用
agent.React_Agent_Stream("搜索一下今天的新闻")
```

---

### 3. file_manager.py - 文件管理工具集

#### 3.1 create_file - 创建文件
**功能**: 在files文件夹中创建新文件

**参数**:
- `filename` (str): 文件名
- `content` (str): 文件内容

**使用示例**:
```python
create_file.invoke({"filename": "test.txt", "content": "你好"})
```

#### 3.2 overwrite_file - 覆盖文件
**功能**: 覆盖已存在文件的内容

**参数**:
- `filename` (str): 文件名
- `content` (str): 新内容

**使用示例**:
```python
overwrite_file.invoke({"filename": "test.txt", "content": "新内容"})
```

#### 3.3 read_file - 读取文件
**功能**: 读取文件内容

**参数**:
- `filename` (str): 文件名

**使用示例**:
```python
read_file.invoke({"filename": "test.txt"})
```

#### 3.4 delete_file - 删除文件
**功能**: 删除指定文件

**参数**:
- `filename` (str): 文件名

**使用示例**:
```python
delete_file.invoke({"filename": "test.txt"})
```

#### 3.5 list_files - 列出文件
**功能**: 列出files文件夹中的所有文件

**使用示例**:
```python
list_files.invoke({})
```

## 命名规则

- **get_time.py**: 获取时间，简洁明了
- **web_search.py**: 网络搜索，明确功能
- **file_manager.py**: 文件管理器，体现管理多个文件操作

## 安全特性

1. **文件操作限制**: 只允许在 `files` 文件夹内操作
2. **文件名验证**: 禁止路径遍历和特殊字符
3. **错误处理**: 所有工具都有完善的异常处理
4. **友好提示**: 提供清晰的操作反馈

## 扩展指南

添加新工具的步骤：

1. 在 `src/core/tools/` 目录下创建新的工具文件
2. 使用 `@tool` 装饰器定义工具函数
3. 在 `__init__.py` 中导入并导出工具
4. 在 `agent.py` 中添加到工具列表

示例：
```python
# src/core/tools/new_tool.py
from langchain_core.tools import tool

@tool
def my_new_tool(param: str) -> str:
    """
    工具描述
    
    params:
        param: 参数说明
    
    return:
        返回值说明
    """
    # 实现逻辑
    return "结果"
```

```python
# src/core/tools/__init__.py
from .new_tool import my_new_tool

__all__ = [..., "my_new_tool"]
```
