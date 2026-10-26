# 部署说明

## 生产入口约定

生产部署统一使用 `/phone/` 前缀。

- 容器本机入口：`http://127.0.0.1:8088/phone/`
- 容器健康检查：`http://127.0.0.1:8088/healthz`
- 对外入口：`http://<主机>/phone/`
- API：`/phone/api/v1/`
- Django Admin：`/phone/admin/`

前端生产构建固定使用：

```text
VITE_PUBLIC_BASE=/phone/
VITE_API_BASE_URL=/phone/api/v1
```

因此不要再把生产前端按根路径 `/` 构建。

## Docker Compose

生产使用 `docker-compose.prod.yml`。保留现有 `.env`，尤其不要更换已经初始化数据库所使用的 PostgreSQL 密码。

重新部署：

```bash
sh deploy/shell/redeploy-phone.sh
```

脚本会重新构建镜像、启动服务并打印状态。

也可以手工执行：

```bash
docker compose --env-file .env -f docker-compose.prod.yml up -d --build
docker compose --env-file .env -f docker-compose.prod.yml ps
```

生产 Compose 只发布统一 Web 入口。PostgreSQL、Redis 和 Django 后端端口仅在 Compose 网络内可见。

## 宿主机 Nginx

如果一台主机部署多个网站，由宿主机 Nginx 通过路径区分。Phone Voice Insight 使用仓库中的：

```text
deploy/nginx/host-phone-path.conf
```

核心规则是保留 `/phone/` 前缀转发到 8088：

```nginx
location = /phone {
    return 301 /phone/;
}

location /phone/ {
    proxy_pass http://127.0.0.1:8088;
}
```

注意 `proxy_pass` 后面没有额外的 `/`，这样 `/phone/assets/... `、`/phone/api/... ` 都会原样进入容器。

修改宿主机 Nginx 后先执行：

```bash
nginx -t
```

确认成功后再 reload。

## 当前服务器

历史公网服务器入口仍为：

- 管理端：`http://8.130.97.14/phone/`
- API 健康检查：`http://8.130.97.14/phone/api/v1/health/`
- Django Admin：`http://8.130.97.14/phone/admin/`

## 数据与升级

PostgreSQL 是业务事实源。重新部署或升级时不要执行 `docker compose down -v`，也不要删除 `postgres_data`。

如果只是更新代码：

```bash
git pull
sh deploy/shell/redeploy-phone.sh
```

## 日志

应用日志输出到容器标准输出，可通过：

```bash
docker compose --env-file .env -f docker-compose.prod.yml logs -f frontend
docker compose --env-file .env -f docker-compose.prod.yml logs -f backend
```

查看。
