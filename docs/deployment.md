# 部署说明

## 当前方案

项目提供两套 Compose 配置：

- `docker-compose.yml` 与 `docker-compose.dev.yml` 用于本地开发和热更新。
- `docker-compose.prod.yml` 用于单机生产部署，前端采用多阶段静态构建与 Nginx，后端采用 Gunicorn，并包含 PostgreSQL、Redis、Celery Worker 和 Celery Beat。

生产部署先复制 `.env.example` 为不提交的 `.env`，替换 `SECRET_KEY`、`POSTGRES_PASSWORD`、允许主机和公开地址，再运行：

```bash
docker compose --env-file .env -f docker-compose.prod.yml up -d --build
docker compose --env-file .env -f docker-compose.prod.yml ps
```

生产配置只发布统一 Web 入口；PostgreSQL、Redis 和 Django 后端端口仅在 Compose 网络内可见。默认入口绑定 `127.0.0.1:8088`，由宿主机反向代理对外发布。

## 当前服务器部署

`8.130.97.14` 上的部署目录为 `/opt/apps/phone-voice-insight`，公网入口为：

- 管理端：<http://8.130.97.14/phone/>
- API 健康检查：<http://8.130.97.14/phone/api/v1/health/>
- Django Admin：<http://8.130.97.14/phone/admin/>

root 用户的 `.bashrc` 已加载 `deploy/shell/phone-voice-insight-aliases.sh`，新登录 shell 可以使用：

```bash
phone_start
phone_stop
phone_restart
```

宿主机 Nginx 通过 `/etc/nginx/snippets/phone-voice-insight.conf` 把 `/phone/` 转发到 `127.0.0.1:8088`。修改代理配置后必须先执行 `nginx -t`，验证通过再 reload。

## 环境变量

秘密只经运行环境注入，不写入 Dockerfile、镜像或 Git。生产应由秘密管理器提供 `SECRET_KEY`、`POSTGRES_PASSWORD` 等；设置 production settings、准确的 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`、`CORS_ALLOWED_ORIGINS` 和 HTTPS。服务器 `.env` 权限应保持为 `0600`。

## 持久化与备份

`postgres_data` 保存数据库，`redis_data` 使用 AOF 便于开发恢复。PostgreSQL 是唯一业务事实源，应定期用 `pg_dump` 备份并在隔离环境验证恢复。Redis 仅作为队列/结果基础设施，不能代替数据库备份。

升级前保存数据库备份并检查迁移；不要通过删除卷解决迁移问题。

## 日志

应用输出结构清晰的标准流日志，由容器平台收集。不得记录密码、Cookie、Token、完整连接串或个人敏感内容。生产需配置轮转、保留期和告警。

## 后续 HTTPS 与运维

当前 IP 路径入口使用 HTTP。绑定正式域名后应启用 HTTPS 自动续期、安全响应头、日志轮转以及独立备份/监控，并把 `SESSION_COOKIE_SECURE` 和 `CSRF_COOKIE_SECURE` 设为 `true`。正式开放采集功能前还需完成容量、恢复、权限、隐私和采集合规评审。
