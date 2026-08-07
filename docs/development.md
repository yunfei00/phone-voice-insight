# 开发指南

## Windows

安装 Python 3.12+、Node.js 20.19+、uv 和 Docker Desktop，然后：

```powershell
Copy-Item .env.example .env
.\scripts\setup.ps1
.\scripts\dev.ps1
```

`setup.ps1` 检查工具、安装锁定依赖、在 Docker 可用时启动 PostgreSQL/Redis、执行迁移和初始化数据。初始化数据由 Django data migration 幂等写入。

## Linux/macOS

```bash
cp .env.example .env
chmod +x scripts/*.sh
./scripts/setup.sh
./scripts/dev.sh
```

## Python 环境

正常开发应先启动 PostgreSQL 和 Redis：

```powershell
docker compose up -d postgres redis
.\scripts\backend.ps1
```

`backend.ps1` 会先检查 `localhost:5432`，数据库未监听时会立即停止并给出提示。`.env` 位于仓库根目录；本地直连容器映射端口使用 `localhost`，容器内使用服务名 `postgres` 和 `redis`。

没有安装 Docker/PostgreSQL、只需本地预览和前端联调时：

```powershell
.\scripts\backend.ps1 -UseSQLite
```

该模式使用忽略的 `backend/local.sqlite3`，并将 Celery 任务设为 eager。它不替代 PostgreSQL 集成验证；Redis 未运行时健康检查显示降级，Celery Worker 不可用。

Linux/macOS 对应命令：

```bash
sh scripts/backend.sh
sh scripts/backend.sh --sqlite
```

## Node 环境

```powershell
cd frontend
npm ci
npm run dev
```

API 地址只通过 `VITE_API_BASE_URL` 配置。刷新任意前端路由由 Vite fallback 或 Nginx `try_files` 返回 `index.html`。

## Docker 环境

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
docker compose ps
docker compose logs -f backend
```

开发覆盖文件挂载前后端源码，Django 自动重载，Vite HMR。PostgreSQL/Redis 数据放在命名卷；前端 `node_modules` 使用独立卷，避免主机覆盖容器依赖。

## 数据库与管理员

```powershell
cd backend
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Docker 中：

```powershell
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py createsuperuser
```

## 常见问题

- `postgres` 无法解析：本地直跑时改为 `localhost`；容器内保留服务名。
- Redis 显示 error：确认 Redis 运行且 URL 数据库编号正确；健康接口仍会返回 `degraded`。
- 8000/5173/5432/6379 冲突：修改 `.env` 的主机端口变量。
- 前端 CORS 失败：把实际前端 origin 加入 `CORS_ALLOWED_ORIGINS`，不要使用通配符。
- 采集任务失败：Phase 1 预期返回 `collector not implemented`，不是环境故障。
- `ConnectionTimeout localhost:5432`：PostgreSQL 没有启动；运行 `docker compose up -d postgres redis`，或使用 `backend.ps1 -UseSQLite` 做本地预览。
