# AI 数据查询与 RAG V1.0 架构说明

## 1. 总体架构

```text
用户问题
  ↓
AI 助手 SSE / 会话与取消
  ↓
受控意图路由（原生工具调用 / 确定性降级）
  ↓
LangChain StructuredTool + Pydantic Schema
  ├─ list_products
  ├─ query_posts ──→ 关键词 + pgvector 混合检索
  ├─ get_post_detail ──→ 帖子与回复树
  ├─ get_issue_statistics ──→ reports.services
  ├─ get_issue_trends ──→ reports.services
  └─ compare_products ──→ reports.services
  ↓
真实统计、真实帖子、统计口径、数据截止时间
  ↓
模型生成结论 + 证据校验 + SSE 输出
```

模型不能直接访问 SQL、ORM 或任意 Python 函数。LangChain 只注册白名单工具，参数先经过 Pydantic 严格校验；原有 Provider、凭据加密、模型选择、会话、限流、SSE 与取消机制继续生效。

## 2. 业务查询工具

| 工具 | 数据来源 | 主要限制 |
| --- | --- | --- |
| `list_products` | 启用产品与 THREAD 数量 | 最多 100 个产品 |
| `query_posts` | `RagDocument`、`ReviewRecord` | 最多 30 条，系统上限可配置为 1～50 |
| `get_post_detail` | `ReviewRecord` 帖子与回复 | 只读，孤立回复不会丢失 |
| `get_issue_statistics` | 最终有效 AI 语料、结构化观点 | 排除无效、官方、UNCERTAIN、ERROR |
| `get_issue_trends` | 统一报表服务 | 返回时间范围、样本量与口径 |
| `compare_products` | 统一报表服务 | 2～5 个真实启用产品 |

旧工具名称继续保留，避免已有会话和外部调用中断。

## 3. RAG 数据模型

### 3.1 RagDocument

- 每个 `THREAD` 最多一个派生索引文档。
- 保存清洗文本、摘要、内容哈希、1024 维向量、Provider、模型、清洗版本、状态、失败原因和同步时间。
- `review` 使用 `OneToOne + CASCADE`；帖子删除时索引同步删除。
- 产品、来源为冗余过滤键，不替代原始数据。

索引状态：

- `INDEXED`：关键词与向量均可用。
- `KEYWORD_ONLY`：Embedding 未启用，关键词检索可用。
- `FAILED`：Embedding 失败，记录原因并由对账任务重试。
- `PENDING`：等待处理。

### 3.2 RagIndexRun

保存批量任务状态、最后处理的帖子 ID、请求/处理/成功/仅关键词/失败数量和错误。每批最多 500 条，完成一批后继续投递下一批，支持 Worker 重启后从 checkpoint 继续。

## 4. 文本构建与同步

- 主文档由帖子标题、正文和受控长度的回复组成，总长上限 16,000 字符。
- 不修改 `ReviewRecord` 的标题或正文。
- 以清洗后文本 SHA-256 判断是否需要重建。
- `ReviewRecord` 保存后通过 `transaction.on_commit()` 投递索引任务；Broker 或 Embedding 故障只记录错误，不回滚采集。
- Celery Beat 每 10 分钟对账未建索引和失败索引。
- `sync_rag_index` 管理命令负责历史批量索引与断点续跑。

## 5. Embedding Provider

支持：

- `disabled`：安全默认值，仅关键词检索。
- `openai_compatible`：调用 `/embeddings`。
- `ollama`：调用兼容 `/v1/embeddings`。
- `fake`：只用于自动测试，生产默认禁止。

外部地址复用现有 SSRF 防护：拒绝携带账号密码的 URL、未授权内网/回环/链路本地地址和危险解析结果。向量必须严格为 1024 维。

推荐中文/多语言模型为 `BAAI/bge-m3`。若替换为其他模型，必须保证 1024 维；模型或清洗版本变化后应重新索引，不能混用不同向量空间。

## 6. 混合检索

1. 根据产品、来源、发布时间和结构化标签过滤候选。
2. 标题、正文和回复执行完整关键词及中文二元片段召回。
3. PostgreSQL 使用 pgvector 余弦距离召回；测试 SQLite 使用最多 500 条的受限 Python 余弦回退。
4. 合并候选、按帖子 ID 去重，综合关键词与向量分重排。
5. 返回真实帖子 ID、标题、摘要、原帖链接、匹配原因和分数。

Embedding 服务异常时返回“已降级为关键词检索”，不会伪造向量结果。

## 7. PostgreSQL 索引

- 生产镜像：`pgvector/pgvector:0.8.7-pg17`。
- migration 条件创建 `vector` 扩展。
- 向量字段：`vector(1024)`。
- HNSW：`vector_cosine_ops`，仅为非空向量建立。
- 产品/来源、状态/产品另有普通复合索引。

## 8. 前端交互

SSE 只显示实际执行阶段，不暴露思维链：

1. 正在理解问题。
2. 正在查询业务数据或检索帖子。
3. 正在生成结论。

工具结果以指标卡、产品对比表、检索状态、统计口径和原始证据展示；刷新后从消息 `tool_result` 与 `evidence` 恢复。

## 9. 安全边界

- 所有接口沿用 Token 身份认证和角色权限。
- 工具只读，不能启动采集、修改、删除或管理操作。
- 用户帖子被视为不可信数据，不能覆盖系统指令。
- 最大结果数、消息数、模型超时、单用户频率和取消状态均受限制。
- API Key 不进入工具结果、消息、日志或前端。

