FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.12-slim-bookworm AS backend-build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM python:3.12-slim-bookworm AS backend
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd -g 10001 pageindex && useradd -u 10001 -g pageindex pageindex \
    && install -d -o pageindex -g pageindex /var/lib/pageindex/uploads
COPY --from=backend-build /app/.venv /app/.venv
COPY backend/app ./app
COPY backend/main.py .
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
ENV PAGEINDEX_BACKEND_URL=http://backend:8000 NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT_STANDALONE=1
RUN npm run build

FROM node:22-bookworm-slim AS frontend
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
COPY --from=frontend-build --chown=node:node /app/.next/standalone ./
COPY --from=frontend-build --chown=node:node /app/.next/static ./.next/static
COPY --from=frontend-build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
