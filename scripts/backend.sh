#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
USE_SQLITE=0
MIGRATE_ONLY=0

for argument in "$@"; do
  case "$argument" in
    --sqlite) USE_SQLITE=1 ;;
    --migrate-only) MIGRATE_ONLY=1 ;;
    *)
      echo "Unknown argument: $argument" >&2
      exit 2
      ;;
  esac
done

if [ "$USE_SQLITE" -eq 1 ]; then
  export DJANGO_SETTINGS_MODULE=config.settings.local
  echo "Warning: using SQLite local preview mode. PostgreSQL remains the normal development database." >&2
else
  POSTGRES_HOST=${POSTGRES_HOST:-localhost}
  POSTGRES_PORT=${POSTGRES_PORT:-5432}
  export POSTGRES_HOST POSTGRES_PORT
  export DJANGO_SETTINGS_MODULE=config.settings.development
  if ! (
    cd "$ROOT_DIR/backend"
    uv run python -c "import socket; socket.create_connection(('$POSTGRES_HOST', $POSTGRES_PORT), timeout=1).close()"
  ) >/dev/null 2>&1; then
    echo "PostgreSQL is not reachable at $POSTGRES_HOST:$POSTGRES_PORT." >&2
    echo "Start it with 'docker compose up -d postgres redis', or use 'sh scripts/backend.sh --sqlite'." >&2
    exit 1
  fi
fi

export REDIS_HOST=localhost
export REDIS_URL=redis://localhost:6379/0
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/1

cd "$ROOT_DIR/backend"
uv run python manage.py migrate --noinput
if [ "$MIGRATE_ONLY" -eq 0 ]; then
  uv run python manage.py runserver 127.0.0.1:8000
fi
