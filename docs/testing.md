# 测试策略

## 后端

```powershell
cd backend
uv run pytest
```

当前覆盖健康检查、Product 创建、反馈条件唯一约束、采集状态机、产品列表 API、反馈筛选 API、Celery ping、未实现任务失败落库和 AI Schema 校验。

测试设置使用 SQLite，健康检查 mock Redis。这使 CI 不依赖外部服务，同时数据库特有行为仍需在 Compose/PostgreSQL 集成测试补充。

## 前端

```powershell
cd frontend
npm run test
```

当前覆盖 App 挂载和健康数据、API 异常错误状态、基础路由。所有 API 均 mock，不访问真实后端或第三方网站。

## 静态质量

```powershell
cd backend
uv run ruff format --check . ..\collectors ..\ai
uv run ruff check . ..\collectors ..\ai
uv run mypy .

cd ..\frontend
npm run lint
npm run typecheck
npm run build
```

## Docker 健康检查

```powershell
docker compose config
docker compose up --build
docker compose ps
Invoke-RestMethod http://localhost:8000/api/v1/health/
```

检查 postgres、redis、backend、celery-worker、celery-beat 和 frontend 都达到 healthy。

## 后续采集器契约测试

每个来源用脱敏、可合法保存的固定样本测试目标校验、分页、记录解析、父子关系、标准化、checkpoint、错误分类、去重和限速；测试不得请求真实站点。少量端到端 PoC 需显式人工触发并遵守合规边界。
