# Agent

一个本地可运行的多工具 AI Agent，支持聊天、工具调用、文档知识库 (RAG)、多会话历史和知识库管理页面。

## 用到了哪些技术

- **LLM Agent 框架**: `LangChain` + `langchain-openai`
  - 使用 `ChatOpenAI` 兼容 OpenAI 风格接口 (可接 OpenAI/OpenRouter/自建兼容网关)
  - 基于工具调用 (Tool Calling) 的 ReAct 工作流
- **后端服务**: `Flask` + `SSE (text/event-stream)`
  - `app.py` 提供聊天流式输出、知识库管理、会话同步等 API
- **前端**: 原生 `HTML/CSS/JavaScript`
  - 聊天页面与知识库页面基于 Jinja 模板
  - Markdown 渲染使用 `marked`
  - XSS 清洗使用 `DOMPurify`
  - 会话历史存储在浏览器 `localStorage`
- **RAG 检索体系**:
  - 向量库: `ChromaDB`
  - 稀疏检索: `rank-bm25`
  - 向量嵌入: `HuggingFaceEmbeddings` (默认 `BAAI/bge-small-zh-v1.5`)
  - 重排模型: `sentence-transformers CrossEncoder` (默认 `BAAI/bge-reranker-v2-m3`)
  - 融合策略: BM25 + 向量混合检索，支持 `RRF` / 线性融合
  - 分块策略: 三级分块 (L1/L2/L3) + 自动父块合并
  - 查询增强: 低命中时自动 query 改写与重试
- **RAG 元数据与可观测性**:
  - 元数据注册表: `SQLite` (WAL)
  - 文档/分块/入库作业表结构管理
  - 检索与入库日志输出
- **文档解析**:
  - `pypdf` (PDF)
  - `docx2txt` (DOCX)
  - 文本与 Markdown 通过 LangChain loader 处理
- **其他工具能力**:
  - 网络搜索: `ddgs`
  - 数学计算与统计
  - 图表绘制: `matplotlib`
  - ManicTime 相关分析工具

## 主要功能

- 聊天对话 (流式输出)
- 多工具调用 (搜索、文件、计算、图表、ManicTime、DeepSeek 监控、RAG)
- 知识库文档上传、入库、检索、删除
- 多会话历史侧边栏与本地持久化
- 停止生成、会话状态与 token 统计

## 项目结构

- `app.py`: Flask Web 应用入口
- `main.py`: 终端模式入口
- `src/core/`: Agent、Prompt、工具定义
- `src/rag/`: RAG 服务 (分块、索引、检索、重排、数据库)
- `templates/`: 页面模板
- `static/`: 前端 JS/CSS
- `files/`: 默认文档上传目录

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置环境变量

至少需要以下变量:

- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_BASE_URL`

可选 RAG 参数示例:

- `RAG_QUERY_MAX_ATTEMPTS` (默认 3)
- `RAG_QUERY_MIN_HITS` (默认 2)
- `RAG_QUERY_LOW_SCORE_THRESHOLD` (默认 0.12)

### 3) 启动 Web 应用

```bash
python app.py
```

默认访问: `http://127.0.0.1:5000`

### 4) (可选) 启动终端模式

```bash
python main.py
```

## License

MIT
