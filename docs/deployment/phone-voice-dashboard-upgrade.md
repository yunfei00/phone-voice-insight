# 手机用户声音智能洞察驾驶舱 V1.0 升级与回滚

## 1. 适用范围

- 服务器：`106.52.122.214`
- 目录：`/opt/apps/phone-voice-insight`
- 编排：`docker compose -f docker-compose.prod.yml`
- 验证分支：`feat/phone-voice-v1-dashboard`
- 实现提交：`c6fb3a94799530616038c427320860c7a3dae4aa`

开发分支仅用于部署验收，PR 保持未合并。

## 2. 本次数据库变化

迁移 `reports.0002_aggregatereport_data_cutoff_and_more`：

- `AggregateReport.product/source` 改为可空，以支持全产品/全来源报告；
- 新增日报/周报类型；
- 新增 `generated_at`、`data_cutoff`；
- 调整幂等唯一约束和查询索引。

迁移是兼容性扩展，不删除 `ReviewRecord`、采集任务、治理数据、AI 配置或历史结构化结果。

## 3. 部署前检查与备份

2026-10-29 实际执行：

- 六个容器部署前均健康；
- 采集、治理、AI 治理、结构化分析活动任务均为 0；
- 磁盘剩余约 24GB；
- 数据库备份：`/opt/apps/backups/phone-voice-insight/postgres-20261029-043526.sql.gz`，已通过 `gzip -t`；
- 环境配置备份：`/opt/apps/backups/phone-voice-insight/env-20261029-043526`，权限 600。

备份文件中可能含敏感配置，不得复制到仓库或公开传输。

## 4. 标准升级流程

```bash
cd /opt/apps/phone-voice-insight
git fetch origin feat/phone-voice-v1-dashboard
git switch feat/phone-voice-v1-dashboard
git pull --ff-only origin feat/phone-voice-v1-dashboard
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml build \
  --build-arg UV_DEFAULT_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
docker compose -f docker-compose.prod.yml run --rm backend python manage.py migrate
docker compose -f docker-compose.prod.yml up -d --force-recreate \
  backend celery-worker celery-beat frontend
```

首次升级时数据库迁移已经执行；后续同分支重建只需 `migrate --check` 确认一致。

## 5. 健康检查

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --check
docker compose -f docker-compose.prod.yml exec -T celery-worker \
  celery -A config inspect ping --timeout 10
curl -fsS http://127.0.0.1:8088/phone/healthz
curl -fsS http://127.0.0.1:8088/phone/api/v1/health/
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/phone/
```

期望：六个容器 healthy、Worker `pong`、页面 HTTP 200、后端数据库与 Redis 均为 `ok`。

## 6. 报告初始化

迁移后可手工运行一次确定性报告任务；该操作不调用付费 AI：

```python
from apps.reports.tasks import generate_insight_reports
generate_insight_reports.run("DAILY")
generate_insight_reports.run("WEEKLY")
```

Celery Beat 后续按计划自动幂等生成。

## 7. 回滚

本次数据库变更对旧代码为加法兼容，优先只回滚应用代码，不反向迁移数据库：

```bash
cd /opt/apps/phone-voice-insight
git switch main
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml build \
  --build-arg UV_DEFAULT_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
docker compose -f docker-compose.prod.yml up -d --force-recreate \
  backend celery-worker celery-beat frontend
```

如发生数据级异常，停止写入后使用本次 gzip 备份恢复到单独数据库验证，确认后再决定正式恢复；不得直接覆盖正在运行的生产库。

## 8. 安全说明

- 不修改现有 API Key；
- 不在日志、文档、提交或截图中输出密钥；
- `AI_AUTOMATION_ENABLED=false` 保持不变；
- 报告展示不会触发模型调用；
- 本次未删除或重建数据库。
