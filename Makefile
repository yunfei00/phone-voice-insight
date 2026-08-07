.PHONY: setup up down logs migrate createsuperuser test lint format backend backend-sqlite backend-shell frontend-shell

setup:
	sh scripts/setup.sh

up:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

down:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

logs:
	docker compose logs -f

migrate:
	docker compose run --rm backend python manage.py migrate

createsuperuser:
	docker compose run --rm backend python manage.py createsuperuser

test:
	sh scripts/test.sh

lint:
	sh scripts/lint.sh

format:
	cd backend && uv run ruff format . ../collectors ../ai
	cd frontend && npm run format

backend:
	sh scripts/backend.sh

backend-sqlite:
	sh scripts/backend.sh --sqlite

backend-shell:
	docker compose exec backend python manage.py shell

frontend-shell:
	docker compose exec frontend sh
