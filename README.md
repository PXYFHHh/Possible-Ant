# Agent

一个本地可运行的多工具 AI Agent，支持流式聊天、工具调用、文档知识库 (RAG)、多会话管理和知识库管理页面。

## 用到了哪些技术

- **LLM Agent 框架**: `LangChain` + `langchain-openai`
  - 使用 `ChatOpenAI` 兼容 OpenAI 风格接口
  - 基于工具调用 (Tool Calling) 的 ReAct 工作流，SSE 流式输出
  - 支持 DeepSeek Reasoner 推理过程可视化
- **后端服务**: `Flask` + `SSE (text/event-stream)`
  - 聊天流式输出、知识库管理 API
  - 会话历史基于 SQLite 持久化存储
- **前端**: 原生 `HTML/CSS/JavaScript`
  - Markdown 渲染: `marked`，XSS 清洗: `DOMPurify`
  - 按轮次分区展示思考过程 / 回复 / 工具调用
  - 入库进度实时轮询
- **RAG 检索体系**:
  - 向量库: `ChromaDB`
  - 稀疏检索: `rank-bm25`
  - 向量嵌入: `HuggingFaceEmbeddings` (`BAAI/bge-small-zh-v1.5`)
  - 重排模型: `CrossEncoder` (`BAAI/bge-reranker-v2-m3`)
  - 融合策略: BM25 + 向量混合检索，支持 RRF / 线性融合
  - 分块策略: 三级分块 (L1/L2/L3) + Auto-merging 自动合并
  - 查询增强: 低命中时自动改写与重试
  - 入库优化: 动态按可用内存调整嵌入批次，一次嵌入分批写入
- **元数据与可观测性**:
  - SQLite 管理文档 / 分块 / 入库任务 / 会话
  - 检索与入库日志
  - 会话级 Token 统计
- **文档解析**:
  - `pypdf` (PDF)、`docx2txt` (DOCX)、LangChain loader (TXT/Markdown)
- **工具能力**:
  - 网络搜索 (`ddgs`)
  - 数学计算 (四则运算 / 百分比 / 均值)
  - 文件管理 (创建 / 读取 / 列表 / 删除)
  - 图表绘制 (`matplotlib`，6 种图表，懒加载)

## 主要功能

- 流式聊天对话（支持推理过程展示）
- 多工具调用（网络搜索、文件管理、计算、图表、RAG）
- 知识库文档上传、入库、检索、删除
- 多会话历史侧边栏，SQLite 持久化，可跨页面刷新恢复
- 停止生成、会话状态查看与 Token 统计

## 项目结构

```
├── app.py                  Flask Web 应用入口 (唯一入口)
├── requirements.txt
├── src/
│   ├── core/
│   │   ├── agent.py        Agent 核心 (ReAct + SSE 流式)
│   │   ├── session_logger.py  会话日志
│   │   ├── prompts/        System Prompt
│   │   └── tools/          工具函数 (搜索/计算/文件/图表/RAG)
│   ├── chat/
│   │   └── db.py           会话数据库
│   └── rag/
│       ├── service.py       RAG 统一服务
│       ├── chunker.py       三级分块
│       ├── retriever.py     混合检索 + 融合
│       ├── embedding.py     向量嵌入 + 批次检测
│       ├── reranker.py      重排序
│       ├── bm25_index.py    BM25 索引
│       ├── query_rewriter.py  查询改写
│       ├── database.py      文档/分块元数据
│       ├── cache.py         LRU 缓存
│       ├── model_utils.py   模型路径解析
│       └── config.py        配置中心
├── static/                 前端 JS/CSS
├── templates/              Jinja 页面模板
└── files/                  文档上传目录
```

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置环境变量

至少需要:

- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_BASE_URL`

可选 RAG 参数可通过 `RAG_` 前缀环境变量覆盖，参见 `src/rag/config.py`：

- `RAG_EMBEDDING_MODEL` (默认 `BAAI/bge-small-zh-v1.5`)
- `RAG_RERANK_MODEL` (默认 `BAAI/bge-reranker-v2-m3`)
- `RAG_USE_MODELSCOPE` (默认 `1`，国内用户可通过 ModelScope 下载模型)
- `RAG_INGEST_BATCH_SIZE` / `RAG_EMBED_BATCH_SIZE` 入库批次控制

### 3) 启动

```bash
python app.py
```

访问 `http://127.0.0.1:5000`

## License

MIT
