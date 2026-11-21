# PageIndex

[![Frontend: Next.js](https://img.shields.io/badge/Frontend-Next.js-000000?logo=nextdotjs)](frontend/README.md)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](backend/README.md)
[![Storage: PostgreSQL 18](https://img.shields.io/badge/Storage-PostgreSQL_18-4169E1?logo=postgresql&logoColor=white)](#run-with-docker)

PageIndex is a PDF workspace for organizing documents, asking questions with page citations, searching libraries, and extracting structured JSON. Chat can list the indexed PDFs in its current scope with exact page counts from stored files, using zero model tokens.

## Quick start

Install GNU Make, uv, and Node.js. Copy [`.env.example`](.env.example) to `.env` in the repo root if you haven’t created one. Native runs use SQLite by default. [Supported Node.js versions](frontend/README.md#run-locally)

```bash
make install
make run
```

Open the app at [localhost:3000](http://localhost:3000) or the native API docs at [localhost:8000/docs](http://localhost:8000/docs).

The example enables accounts. Set the credential encryption key and configure a sign-in method or create a local account. Users then enter their own PageIndex and chat credentials in **Account → Profile & settings → Provider settings**. For optional single-user mode, set `AUTH_REQUIRED=false` and use the commented provider settings in the example. [Authentication setup](backend/README.md#authentication)

## Run with Docker

The root Dockerfile builds both apps. Compose runs the frontend, FastAPI, PostgreSQL 18, and Redis. It uses the same root `.env` as the native backend. Copy `.env.example` if needed and set `POSTGRES_PASSWORD` before starting Compose. Generate a password with `openssl rand -hex 32` for a new database, or reuse the password of an existing one.

```bash
docker compose up -d --build --wait --remove-orphans
```

Compose publishes only the frontend, on `127.0.0.1` at `HTTP_PORT`, which defaults to `3000`. If you change the frontend port with authentication enabled, update `APP_PUBLIC_URL` to match the URL in your browser.

Run `docker compose down` to stop the stack and retain your database and PDFs. [Import an existing SQLite workspace](backend/README.md#import-an-existing-sqlite-workspace)

## Development commands

| Command | What it does |
| --- | --- |
| `make install` | Installs backend and frontend dependencies from their lockfiles. |
| `make run` | Starts both development servers. |
| `make format` | Formats Python with Ruff and frontend code with Oxfmt. |
| `make lint` | Checks Python with Ruff and frontend code with Oxlint. |
| `make build` | Compiles the Python sources and builds Next.js. |
| `make test` | Runs backend tests and frontend type checks. |
| `make prune` | Removes local caches, build output, and test artifacts. |
| `make purge` | Runs `prune` and removes the local dependencies and Python virtual environments. |

Stop the development servers before cleaning. Both cleanup commands preserve environment files, lockfiles, databases, and uploaded PDFs. Run `make install` after a purge.

See the [backend guide](backend/README.md) for configuration and tests, and the [frontend guide](frontend/README.md) for development checks.
