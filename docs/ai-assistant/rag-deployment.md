# AI 数据查询与 RAG V1.0 部署说明

## 1. 升级前检查

1. 确认当前分支与提交，保存 `.env` 备份。
2. 备份 PostgreSQL，并验证备份可读。
3. 确认 PostgreSQL 主版本为 17，磁盘空间充足。
4. 确认没有正在执行的关键采集或结构化分析迁移。
5. 不删除数据库、不删除 Volume、不修改现有 AI API Key。

## 2. PostgreSQL 镜像升级

Compose 从 `postgres:17-alpine` 切换为 `pgvector/pgvector:0.8.7-pg17`。两者均为 PostgreSQL 17，继续使用原有 `/var/lib/postgresql/data` Volume。

上线前必须在数据库备份后执行；不得跨 PostgreSQL 主版本直接复用数据目录。

```bash
docker compose pull postgres
docker compose build backend celery-worker celery-beat frontend
docker compose up -d postgres redis
docker compose up -d backend celery-worker celery-beat frontend
docker compose ps
```

Backend 启动时执行 migration，migration 会幂等创建 `vector` 扩展和 HNSW 索引。

## 3. 环境变量

```dotenv
RAG_INDEXING_ENABLED=true
RAG_EMBEDDING_PROVIDER=disabled
RAG_EMBEDDING_BASE_URL=
RAG_EMBEDDING_API_KEY=
RAG_EMBEDDING_MODEL=BAAI/bge-m3
RAG_EMBEDDING_TIMEOUT_SECONDS=30
RAG_RETRIEVAL_LIMIT=20
```

安全默认使用 `disabled`，此时系统仍支持关键词检索。配置 OpenAI-compatible 或 Ollama 前，必须确认地址通过 SSRF 白名单审查、模型输出恰好为 1024 维且费用预算明确。

私有 Ollama 地址需由管理员加入现有 `ASSISTANT_AI_PRIVATE_HOST_ALLOWLIST`。不要把 Key 写入 Compose 文件或 Git。

## 4. 历史索引

同步执行一批并自动续跑：

```bash
docker compose exec backend python manage.py sync_rag_index --batch-size 100
```

提交 Celery：

```bash
docker compose exec backend python manage.py sync_rag_index --batch-size 100 --enqueue
```

如果任务中断，从索引任务 ID 继续：

```bash
docker compose exec backend python manage.py sync_rag_index --run-id <RUN_ID> --batch-size 100 --enqueue
```

索引失败不会影响采集数据；修复 Provider 后，Celery Beat 会逐步重试失败文档。

## 5. 验证

```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT indexname FROM pg_indexes WHERE indexname='rag_doc_embedding_hnsw';"
docker compose exec backend python manage.py showmigrations assistant
docker compose ps
```

API：

- `GET /api/v1/assistant/rag-index/`：索引数量、状态、失败数和最近同步时间。
- `POST /api/v1/assistant/rag-index/sync/`：管理员启动历史索引，重复运行返回 409。

## 6. 回滚

1. 先停止新索引任务并备份数据库。
2. 回滚应用代码和迁移到升级前版本。
3. `RagDocument` 是派生数据，可在确认回滚后删除；原始 `ReviewRecord` 不受影响。
4. 不需要立即删除 `vector` 扩展；保留扩展不会影响旧应用。
5. 如需回退 PostgreSQL 镜像，保持 PostgreSQL 17 且先在隔离环境验证同一数据卷。

## 7. 当前生产状态

本次只在服务器独立项目 `pvi-rag-validation`、独立数据库 Volume 和 5188 端口完成验证。正式生产目录 `/opt/apps/phone-voice-insight` 及生产数据库未被覆盖。

