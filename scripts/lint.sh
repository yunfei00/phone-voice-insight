#!/usr/bin/env sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
(cd "$ROOT_DIR/backend" && uv run ruff check . ../collectors ../ai && uv run ruff format --check . ../collectors ../ai && uv run mypy .)
(cd "$ROOT_DIR/frontend" && npm run lint && npm run typecheck)
