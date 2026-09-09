# syntax=docker/dockerfile:1
# Nuroli web image (ARCHITECTURE.md section 15): pnpm build of the React app,
# served by an unprivileged nginx that proxies the API. Base images are pinned
# by tag and digest; the context is the repository root under .dockerignore.

FROM node:24-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS builder
WORKDIR /app/frontend
RUN npm install -g pnpm@11.9.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir /pnpm/store
COPY frontend/ ./
RUN pnpm exec vite build

FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6 AS runtime
COPY infra/nginx/security-headers.conf /etc/nginx/security-headers.conf
COPY infra/nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
