# AI 数据查询与 RAG V1.0 架构审计

## 1. 审计基线

- 审计日期：2026-10-31（Asia/Shanghai）
- 代码基线：`main@88cabce2e5c3b271111871bd106b1390c2656c31`
- 开发分支：`feature/ai-data-rag-v1`
- 生产数据库：PostgreSQL 17.11
- 生产缓存与队列：Redis 7.4、Celery Worker、Celery Beat
- Web 技术栈：Django 5.2、DRF、Vue 3、TypeScript、Element Plus

本次审计只进行了只读代码和环境检查，没有修改生产数据、模型配置或任务状态。

## 2. 可复用能力

### 2.1 业务数据

- `ReviewRecord` 已保存产品、来源、采集入口、帖子/回复关系、标题、正文、发布时间、原帖链接和原始元数据。
- `ThreadTreeViewSet` 已在后端完成帖子列表、搜索、过滤、排序、分页及回复树构造，前端不需要下载全量反馈后自行分组。
- `ReviewQuality`、`GovernanceAIReview` 与 `final_corpus_reviews()` 已形成最终有效 AI 语料口径，可排除无效、官方、未接受和被覆盖的数据。
- `StructuredAnalysis` 与 `OpinionAspect` 已保存结构化问题、分类、严重度、情感、证据和产品关联。
- `apps.reports.services` 已提供总览、问题排行、趋势、产品对比与证据查询，是统计类工具的唯一业务口径来源。

### 2.2 AI 助手

- 已有用户会话、消息、取消、幂等请求 ID、SSE 输出、证据保存、工具轨迹、Token 和耗时记录。
- 已有模型配置加密、模型选择、OpenAI-compatible/Ollama/fake Provider、连接测试及外部地址 SSRF 校验。
- 已有受控工具调用与不支持原生 function calling 时的路由降级；模型不能直接执行 SQL 或 ORM。
- 系统提示已明确禁止把帖子内容当作指令、禁止编造数量和用户原话。

### 2.3 采集与异步任务

- `persist_review()` 通过稳定外部 ID 去重并更新动态字段。
- Celery Beat 已用于采集恢复、治理、结构化分析和报告调度，适合增加索引对账任务。
- PostgreSQL、Redis、Worker、Beat、Backend、Frontend 在生产环境均为健康状态。

## 3. 缺失能力与风险

### 3.1 缺失能力

1. 没有 Embedding Provider、向量字段、索引运行记录、失败重试或断点续跑。
2. 没有 pgvector、LangChain 或其他向量库依赖。
3. 现有 `search_feedback` 仅做标题/正文关键词包含查询，不支持语义相似、混合检索和匹配依据。
4. 工具集缺少 `list_products`、面向 THREAD 的 `query_posts` 和 `get_post_detail`。
5. 前端只显示“正在查询真实数据”，未展示理解、查询、检索、生成等可核验执行阶段，也没有统计卡片和产品对比结构化展示。
6. 没有独立的 RAG 质量指标、索引状态 API 和固定评测集。

### 3.2 数据库与 pgvector 结论

生产数据库是 PostgreSQL 17.11，适合采用 pgvector；但当前 `postgres:17-alpine` 镜像的可用扩展中不存在 `vector`。直接创建向量字段会导致生产迁移失败。

实施方案：

- 将 PostgreSQL 17 镜像兼容升级为固定版本的 `pgvector/pgvector:0.8.7-pg17`，继续挂载原有 PostgreSQL 数据卷，不重建数据库。
- 使用 Django migration 执行 `CREATE EXTENSION IF NOT EXISTS vector`，再创建固定维度向量字段和 HNSW 索引。
- 测试环境仍使用 SQLite；模型保留 JSON 向量兼容字段，检索服务在非 PostgreSQL 环境使用受限的 Python 余弦回退，避免把 SQLite 性能结论冒充生产结论。
- 向量不可用或 Embedding 服务异常时自动降级为关键词检索并返回明确状态，不阻塞采集和帖子查询。

### 3.3 兼容性风险

- Embedding 模型的输出维度必须稳定；V1 固定为 1024 维，并在入库前严格校验。
- 更换模型或清洗版本后必须重建对应文档向量，不能混合比较不同向量空间。
- PostgreSQL 镜像升级前必须备份数据库并验证扩展；回滚代码时不可先删除扩展或向量数据。
- 现有助手 Provider 是自研 OpenAI-compatible 客户端。LangChain 仅承担严格 Schema 工具注册和受控路由，不替换凭据、会话、SSE 与取消机制，避免影响现有模型兼容性。
- 用户帖子属于不可信输入；检索内容只进入工具结果，不进入系统指令，且不得暴露其他用户私有配置。

## 4. 实施架构

### 4.1 受控业务工具

新增并统一六个只读工具：

- `list_products`
- `query_posts`
- `get_post_detail`
- `get_issue_statistics`
- `get_issue_trends`
- `compare_products`

保留旧工具别名，避免破坏已有会话与测试。全部输入输出使用 Pydantic，限制日期、产品、来源和数量；统计继续调用 `apps.reports.services`。

### 4.2 索引模型与同步

- 一个 THREAD 对应一个索引文档，回复文本以受控长度加入检索文档，但不修改原始记录。
- 保存清洗版本、内容哈希、Embedding Provider/模型、索引状态、重试次数、错误和同步时间。
- 采集事务提交后只投递轻量索引任务；Embedding 失败不回滚采集。
- 周期对账负责补建、更新和删除同步；批量命令保存检查点，支持断点续跑。

### 4.3 混合检索

- PostgreSQL 关键词匹配与 pgvector 余弦距离分别取候选。
- 依据归一化关键词分、向量分和元数据过滤进行合并、去重、重排。
- 返回真实帖子 ID、标题、摘要、链接、匹配类型和分数。
- 产品、来源、发布时间和结构化标签过滤均在后端执行。

### 4.4 智能编排

- LangChain `StructuredTool` 仅包装白名单工具及 Pydantic Schema。
- 原生工具调用仍优先使用现有 Provider；不支持时使用确定性意图路由。
- 限制最大步骤、工具次数、结果数和总超时；工具失败时只返回错误事实，不允许模型补写结论。
- SSE 仅输出实际阶段和工具名称，不输出内部思维链。

## 5. 验收策略

- 固定数据集不少于 30 个用例，覆盖统计、检索、权限、故障、删除同步和恢复。
- 独立计算统计真值；引用 ID 必须在数据库存在并可访问。
- 记录 Recall@K、引用准确率、回答正确率、P50/P95。
- CI 执行 Ruff、mypy、migration check、pytest、ESLint、TypeScript、Vitest 和生产构建。
- Docker 验收验证扩展、迁移、索引任务、混合检索与重启恢复；未经执行的项目不标记通过。

