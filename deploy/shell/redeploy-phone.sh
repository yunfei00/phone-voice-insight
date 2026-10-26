#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
    echo "ERROR: $ROOT_DIR/.env not found."
    echo "Reuse the existing production .env before redeploying so database credentials stay unchanged."
    exit 1
fi

docker compose --env-file .env -f docker-compose.prod.yml up -d --build
docker compose --env-file .env -f docker-compose.prod.yml ps

echo
echo "Health:"
curl -fsS http://127.0.0.1:8088/healthz
echo
echo "Local app: http://127.0.0.1:8088/phone/"
echo "Public path: /phone/"
