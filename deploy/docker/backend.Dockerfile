FROM ghcr.io/astral-sh/uv:0.11.2 AS uv

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=uv /uv /uvx /bin/
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
ARG UV_DEFAULT_INDEX_URL=https://pypi.org/simple
RUN sed -i "s|https://pypi.org/simple|$UV_DEFAULT_INDEX_URL|g" uv.lock && \
    uv sync --default-index "$UV_DEFAULT_INDEX_URL" --frozen --no-dev --no-install-project

COPY backend/ ./
COPY collectors/ ./collectors/
COPY ai/ ./ai/

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
