# LearnTrail frontend (apps/web) — Next.js dev server.
#
# Build context is the REPO ROOT, not apps/web (plans/phase-0.md, task 8):
# package.json, pnpm-workspace.yaml, pnpm-lock.yaml and biome.jsonc all live
# there, and `pnpm install --frozen-lockfile` needs the workspace root to
# resolve apps/web at all. See .dockerignore for what is kept out.
#
# Phase 0 image: a development image running `next dev`. A multi-stage
# standalone production build lands when there is something to deploy.

FROM node:24-slim

ENV \
    # lefthook's postinstall (allowed to run via pnpm-workspace.yaml's
    # allowBuilds) shells out to `lefthook install -f`. There is no .git in the
    # build context, so it would have nothing to wire up — under CI=true it
    # no-ops and swallows the failure, which is what keeps this build green.
    CI=true \
    # Next phones home with anonymous usage data unless this is set. A local
    # dev container should make no network call nobody asked for.
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=development

# Pinned to package.json's `packageManager` field. Installed directly rather
# than via corepack: same result, one fewer moving part (corepack is on its way
# out of Node distributions), and pnpm's own version management sees an exact
# match so it never re-downloads itself at runtime.
RUN npm install --global pnpm@11.9.0 && npm cache clean --force

# node:24-slim ships a `node` user at uid/gid 1000, matching the repo owner, so
# anything written into the bind-mounted source tree stays host-writable.
# Ownership is set BEFORE the install and every COPY uses --chown, rather than
# a single `chown -R /app` at the end: recursively re-owning a pnpm
# node_modules is ~150k inodes and added 40s to every build.
RUN mkdir -p /app && chown node:node /app
WORKDIR /app
USER node

# --- Layer 1: dependencies only. -------------------------------------------
# Manifests + lockfile first so this layer survives source edits. Every
# workspace member listed in pnpm-workspace.yaml must have its package.json
# present or --frozen-lockfile fails.
COPY --chown=node:node package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY --chown=node:node apps/web/package.json apps/web/package.json
#
# No --mount=type=cache for the pnpm store on purpose: a cache mount is a
# different filesystem from the image layer, so pnpm cannot hardlink out of it
# and silently falls back to copying — all of the complexity, none of the win.
RUN pnpm install --frozen-lockfile

# --- Layer 2: application source. ------------------------------------------
# biome.jsonc is copied because Biome resolves only from the workspace root
# (plans/phase-0.md, task 6) and a lint run inside the container would
# otherwise find no config.
COPY --chown=node:node biome.jsonc ./
COPY --chown=node:node apps/web/ apps/web/

# .next must exist, owned by `node`, before the container starts. Docker seeds
# an ANONYMOUS VOLUME (docker-compose.yml mounts one here) from whatever is at
# that path in the image — and when the path does not exist it creates an empty
# ROOT-owned directory instead, so `next dev` dies with
# `EACCES: permission denied, mkdir '/app/apps/web/.next/dev'`. Creating it
# here as `node` is what makes the volume inherit the right ownership.
# .dockerignore excludes .next from the build context (deliberately — a host
# build's output must never be baked in), so this cannot be a COPY.
RUN mkdir -p /app/apps/web/.next

EXPOSE 3000

# `GET / -> 200`. The page is static, so the frontend reaches healthy without
# the backend existing (plans/phase-0.md, task 8) — which is why there is no
# depends_on between them in Phase 0. Node's global fetch, not curl: no apt
# layer needed. start-period is generous because `next dev` compiles the route
# on the FIRST request, and that compile is what this probe triggers.
HEALTHCHECK --interval=10s --timeout=20s --start-period=90s --retries=10 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.status===200?0:1)).catch(()=>process.exit(1))"]

# The dev command fixed by task 6, run from the workspace root. --hostname
# 0.0.0.0 is passed explicitly rather than relying on Next's default so the
# port is reachable from outside the container's loopback.
CMD ["pnpm", "--filter", "web", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
