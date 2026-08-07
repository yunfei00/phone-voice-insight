# PVI 后端

Django 5 + Django REST Framework 服务，负责产品、数据来源、采集任务、原始反馈、分析结果和报告快照。

## 本地运行

```powershell
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

默认使用 PostgreSQL 与 Redis；测试使用 SQLite，并 mock Redis 健康检查，因此不访问外部站点。

```powershell
uv run ruff check .
uv run mypy .
uv run pytest
```

API 文档位于 `/api/docs/` 和 `/api/redoc/`。
