#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for command in uv node npm; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "缺少必要命令：$command" >&2
    exit 1
  }
done

[ -f "$ROOT_DIR/.env" ] || cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
(cd "$ROOT_DIR/backend" && uv sync)
(cd "$ROOT_DIR/frontend" && npm ci)

if command -v docker >/dev/null 2>&1; then
  (cd "$ROOT_DIR" && docker compose up -d postgres redis)
  (cd "$ROOT_DIR" && docker compose run --rm backend python manage.py migrate --noinput)
else
  echo "未检测到 Docker；依赖已安装，请自行准备 PostgreSQL/Redis 后运行迁移。" >&2
fi
