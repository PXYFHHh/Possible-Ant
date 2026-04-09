# 文件操作工具

## 概述

本模块提供了安全的文件操作工具，只允许在 `files` 文件夹内进行文件操作。

## 可用工具

### 1. create_file
创建新文件并写入内容

**参数：**
- `filename`: 文件名（仅文件名，不包含路径）
- `content`: 要写入的文件内容

**示例：**
```python
create_file.invoke({"filename": "test.txt", "content": "你好，世界！"})
```

### 2. overwrite_file
覆盖已存在文件的内容

**参数：**
- `filename`: 文件名（仅文件名，不包含路径）
- `content`: 要写入的新内容

**示例：**
```python
overwrite_file.invoke({"filename": "test.txt", "content": "新内容"})
```

### 3. read_file
读取文件内容

**参数：**
- `filename`: 文件名（仅文件名，不包含路径）

**示例：**
```python
read_file.invoke({"filename": "test.txt"})
```

### 4. delete_file
删除文件

**参数：**
- `filename`: 文件名（仅文件名，不包含路径）

**示例：**
```python
delete_file.invoke({"filename": "test.txt"})
```

### 5. list_files
列出 files 文件夹中的所有文件

**参数：** 无

**示例：**
```python
list_files.invoke({})
```

## 安全特性

1. **路径限制**：只允许在 `files` 文件夹内操作
2. **文件名验证**：禁止使用路径分隔符和特殊字符
3. **自动创建目录**：如果 `files` 文件夹不存在，会自动创建
4. **错误处理**：所有操作都有完善的错误处理和友好提示

## 使用示例

### 在 Agent 中使用

```python
from src.core.agent import Model, Agent
from src.core.tools import create_file, read_file, delete_file, list_files

model = Model()
agent = Agent(model, [create_file, read_file, delete_file, list_files])

# 创建文件
agent.React_Agent_Stream("创建一个名为 hello.txt 的文件，内容是：你好！")

# 读取文件
agent.React_Agent_Stream("读取 hello.txt 文件")

# 列出文件
agent.React_Agent_Stream("列出所有文件")

# 删除文件
agent.React_Agent_Stream("删除 hello.txt 文件")
```

## 注意事项

1. 文件名不能包含以下字符：`\ / : * ? " < > |`
2. 文件名不能为空
3. 所有文件操作都限制在 `files` 文件夹内
4. 创建文件时，如果文件已存在会提示使用 `overwrite_file`
5. 覆盖文件时，如果文件不存在会提示先创建文件
