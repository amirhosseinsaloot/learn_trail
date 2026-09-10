# syntax=docker/dockerfile:1
# Nuroli API image (ARCHITECTURE.md section 15): multi-stage, uv-managed
# dependencies, Python 3.14, non-root, one uvicorn worker. Base images are
# pinned by tag and digest. The build context is the repository root and
# .dockerignore allows only the files the build needs, so no .env is copied.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM python:3.14-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
RUN groupadd --gid 1000 nuroli && useradd --uid 1000 --gid nuroli --create-home nuroli
WORKDIR /app
COPY --from=builder --chown=nuroli:nuroli /app/.venv ./.venv
COPY --from=builder --chown=nuroli:nuroli /app/src ./src
COPY --chown=nuroli:nuroli backend/alembic.ini ./alembic.ini
COPY --chown=nuroli:nuroli backend/migrations ./migrations
COPY --chown=nuroli:nuroli infra/docker/api-entrypoint.sh ./api-entrypoint.sh
USER nuroli
EXPOSE 8000
# The entrypoint applies migrations under an advisory lock, then execs the command.
ENTRYPOINT ["/app/api-entrypoint.sh"]
CMD ["python", "-m", "nuroli.main"]
