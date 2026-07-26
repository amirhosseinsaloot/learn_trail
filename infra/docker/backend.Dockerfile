# LearnTrail backend (apps/api) — FastAPI under uvicorn.
#
# Build context is the REPO ROOT, not apps/api: the uv workspace is rooted
# there (`pyproject.toml` + `uv.lock`), and a lockfile-driven install needs
# both plus every member's pyproject.toml. See .dockerignore for what is kept
# out of that context.
#
# Phase 0 image: a development image, not a production one. It runs uvicorn
# with --reload against bind-mounted source (see docker-compose.yml). A slim
# runtime stage lands when there is something to deploy.

FROM python:3.12-slim-bookworm

# uv is pinned to the exact version that produced the committed uv.lock
# (`uv --version` on the host). Copying the static binary out of the published
# image is both faster and more reproducible than curl | sh.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV \
    # Bytecode-compile on install: slower build, faster container start, and no
    # first-request .pyc writes into the bind-mounted source tree.
    UV_COMPILE_BYTECODE=1 \
    # The uv cache and the target venv sit on different layers/mounts, so
    # hardlinking is unavailable; copy instead of emitting a warning per file.
    UV_LINK_MODE=copy \
    # The venv lives OUTSIDE /app on purpose. docker-compose.yml bind-mounts
    # host source over /app/apps/api and /app/packages/database; anything under
    # a mounted path would be shadowed at runtime.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    # No __pycache__ dirs written back into the bind-mounted host tree.
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- Layer 1: third-party dependencies only. -------------------------------
# Only the manifests are copied, so this layer is rebuilt when a dependency
# changes and reused when application source changes. --no-install-workspace
# skips the members themselves (they have no source here yet).
# README.md is required: both members declare `readme = "../../README.md"` and
# hatchling reads it while building their metadata.
COPY pyproject.toml uv.lock README.md ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/ai_core/pyproject.toml packages/ai_core/pyproject.toml
COPY packages/database/pyproject.toml packages/database/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

# --- Layer 2: workspace source. --------------------------------------------
# PACKAGING TRAP (plans/phase-0.md, task 8): packages/database's wheel ships
# only the `database/` package — `alembic.ini` and `migrations/` are excluded
# by [tool.hatch.build.targets.wheel], so an image built from the built
# distribution would have an importable `database` and no migration env at all.
# Resolution: copy packages/database in as SOURCE and let `uv sync` install
# workspace members in editable mode. alembic.ini and migrations/ therefore
# exist as real files at /app/packages/database/, and migrations stay where
# packages/database's own tooling (alembic.ini's %(here)s-relative
# script_location) already expects them. The alternative — moving migrations/
# under database/ so they ship in the wheel — was rejected: it would rewrite a
# layout task 4 just fixed, and mixes lifecycle-managed migration scripts into
# an importable package.
COPY apps/api/ apps/api/
COPY packages/ai_core/ packages/ai_core/
COPY packages/database/ packages/database/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Run as a non-root user whose uid matches the repo owner, so files created in
# the bind-mounted source tree (and any alembic revision generated from inside
# the container) stay writable from the host.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /app app \
    && chown -R app:app /app /opt/venv
USER app

EXPOSE 8000

# Healthcheck target is FastAPI's built-in /openapi.json. apps/api has NO
# routes in Phase 0 by design (routes are Phase 1), so there is deliberately no
# /health endpoint to probe. urllib rather than curl: it is already in the
# image, and adding curl means an apt layer for one HTTP GET.
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/openapi.json', timeout=4).read()"]

# --host 0.0.0.0 so the port is reachable from outside the container's
# loopback. --reload picks up edits to the bind-mounted source.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", \
     "--reload-dir", "/app/apps/api", "--reload-dir", "/app/packages/ai_core", \
     "--reload-dir", "/app/packages/database"]
