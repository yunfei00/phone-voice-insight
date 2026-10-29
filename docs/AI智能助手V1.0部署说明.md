# AI 智能助手 V1.0 部署说明

## 1. 升级内容

- 新增 `assistant` Django 应用及数据库迁移。
- 前端新增 `/ai-assistant`。
- Nginx API 代理关闭缓冲，读取超时调整为 300 秒。
- Django Cache 使用 Redis，支持跨 Worker 助手并发锁与限流。

## 2. 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ASSISTANT_AI_PRIVATE_HOST_ALLOWLIST` | 空 | 允许访问的私网 AI 主机名，逗号分隔；不要填写 IP 网段或通配符 |
| `ASSISTANT_MAX_MESSAGES_PER_CONVERSATION` | 200 | 单会话消息上限，范围 20～1000 |
| `ASSISTANT_MAX_EXECUTION_SECONDS` | 180 | 单次助手请求上限，范围 30～300 |

公网 OpenAI 兼容地址无需白名单，但必须解析为公网 IP。Docker 内 Ollama 可配置为受控主机名，例如 `ollama`，并由管理员确认其部署用途。

## 3. Docker Compose 升级

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build backend frontend celery-worker celery-beat
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml ps
```

迁移仅新增助手表，不删除或改写采集、治理、分析与报告数据。

## 4. 验证

1. `/api/v1/health/` 返回数据库与 Redis 正常。
2. 登录后打开 `/phone/ai-assistant`。
3. 新建模型配置并执行最小连接测试。
4. 新建会话，以 Mock 或受控测试 Provider 验证 SSE、证据与停止生成。
5. 查看 Nginx、Backend 日志，确认响应未被缓存或缓冲。

## 5. 回滚

回滚应用镜像或 Git 提交后重新启动服务即可。新增助手表可保留，不影响旧版本；若必须回滚迁移，先备份数据库，再执行 `python manage.py migrate assistant zero`，该操作会删除助手会话和模型配置，禁止在未确认数据保留要求时执行。

