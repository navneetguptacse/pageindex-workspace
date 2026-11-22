# PageIndex backend

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](pyproject.toml)
[![SQLModel](https://img.shields.io/badge/ORM-SQLModel-2563EB)](pyproject.toml)

FastAPI serves the document, chat, search, and extraction API. SQLModel persists workspace data and background jobs in PostgreSQL with Docker Compose or SQLite for native local development.

## Run locally

Use Python 3.11+ and uv. Copy the repo root’s [`.env.example`](../.env.example) to `.env` in the same directory if needed. Run these commands from `backend/`.

```bash
uv sync --locked
uv run --locked fastapi dev
```

Open the [API docs](http://localhost:8000/docs). From the repo root, run `make test-backend` for the test suite or `make lint-backend` and `make format-backend` for Ruff. Tests default to SQLite. Set `TEST_DATABASE_URL` and `TEST_REDIS_URL` in the test process environment to enable PostgreSQL and Redis coverage.

## Configuration

- **Single-user mode** uses `AUTH_REQUIRED=false` and the optional provider settings in the root `.env.example`. Set `PAGEINDEX_API_KEY` and the chat key for `CHAT_MODEL`. The default model uses `DEEPSEEK_API_KEY`.
- **Storage** uses SQLite and local PDF files by default. Set `DATABASE_URL` or `UPLOAD_DIR` in the root `.env` to override them for native runs. PostgreSQL URLs use `postgresql+psycopg://`. Compose supplies PostgreSQL and a persistent uploads volume. [Local Docker setup](../README.md#run-with-docker)
- **Redis** caches page previews and images when `REDIS_URL` is set. Entries expire after `PREVIEW_CACHE_TTL_SECONDS`, which defaults to 300 seconds. Compose starts Redis with a 64 MiB cache limit and least-recently-used eviction by default.
- **Background jobs** support `Prefer: respond-async` and `Idempotency-Key` for retry-safe upload or extraction requests. Poll the returned resource for progress.

## Chat

Document-list questions return the ready PDFs in the current library, collection, or single-PDF scope. They support uploads from today or yesterday in UTC and size comparisons such as “List files larger than 10 MB.” Page counts come from the stored PDF and show **Unavailable** if it can’t be read. These responses use zero model tokens.

Content questions use the model. The first attempt allows up to 4,096 output tokens within the configured limit. If the first answer is cut off, chat retries once with instructions to produce a concise, complete answer. The retry uses `CHAT_OUTPUT_TOKENS`, which defaults to 8,192.

For signed-in accounts, each model call reserves a conservative input allowance and its output budget from `CHAT_TOKENS_PER_DAY`. Concurrent calls share that budget. The server replaces the reservation with the provider’s reported usage when available. Calls with unknown usage may retain the reservation until the UTC reset.

Run `uv run --locked python -m app.evaluate_chat scenarios.json` to validate cases. Each case has a `name` and `turns` with a `question` and optional `expected_text` or `expected_pages`. Add `--live` to send requests to the app and `--username` to sign into a password-based account. Set `--url` to the frontend origin for Docker Compose.

## Authentication

Set `AUTH_REQUIRED=true` and `APP_PUBLIC_URL` to the same origin you open in the browser, such as `http://localhost:3000`. For local HTTP, set `SECURE_COOKIES=false`. For HTTPS, use `SECURE_COOKIES=true`. After changing the root `.env`, restart a native backend or recreate the Compose backend with `docker compose up -d backend`.

With `AUTH_ALLOW_SIGNUP=true`, enable a registration method for visitors at `/register` or `/login`.

- **Email** uses `RESEND_API_KEY` and `RESEND_FROM_EMAIL` with a sender authorized by Resend. It supports verified registration, recovery email verification, password reset, and password change notifications. [Resend sender setup](https://resend.com/docs/dashboard/domains/introduction)
- **Google** uses `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from a web application OAuth client. Register `${APP_PUBLIC_URL}/api/v1/workspace/oauth/google/callback` as its redirect URI. [Google OAuth setup](https://developers.google.com/identity/protocols/oauth2/web-server)
- **GitHub** uses `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` from an OAuth App. Register `${APP_PUBLIC_URL}/api/v1/workspace/oauth/github/callback` as its callback URL. [GitHub OAuth setup](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)

To create an account without configuring email or OAuth, run `uv run --locked python -m app.manage_users alice` from `backend/` or `docker compose exec backend python -m app.manage_users alice` from the repo root with Compose running. During provisioning, `--claim-local-data` assigns existing local data to that user. Set `AUTH_ALLOW_SIGNUP=false` to disable self-registration.

Set `PROVIDER_CREDENTIALS_ENCRYPTION_KEY` once in the root `.env`. Generate its value with `openssl rand -base64 32 | tr '/+' '_-'`. Retain the key securely so restored databases can still decrypt their credentials.

After signing in, users open **Account → Profile & settings → Provider settings** to save their own PageIndex API key. For chat, choose OpenAI, DeepSeek, Anthropic, or Google Gemini and enter that provider’s API key and model ID. Credentials are encrypted and saved per account. When replacing a PageIndex key, use one for the same library to retain access to documents already indexed there.

The app checks provider credentials and model access before saving. PageIndex uses a read-only library request. Chat sends a short test prompt to the selected model, which may use provider credits. Use **Test saved connection** to check saved credentials again after rotating a key or changing provider permissions.

Users can update their first and last names in **Account → Profile & settings**. Usernames are permanent. To change a recovery email, users with passwords confirm their current password, then enter the six-digit code sent to the new address. The code expires after ten minutes, and the current address stays active until the code is verified.

## Import an existing SQLite workspace

Stop the old app and back up its SQLite file and PDFs. Create the root `.env` as described in the [local Docker setup](../README.md#run-with-docker). With an empty PostgreSQL database, run these commands from the repo root before starting the app:

```bash
docker compose build backend
docker compose up -d --wait postgres
docker compose run --rm --no-deps \
  -v "$PWD/backend/data:/legacy:ro" \
  backend python -m app.migrate_sqlite /legacy/app.db --uploads /legacy/uploads
docker compose up -d --build --wait
```

The importer preserves workspace data and stored PDFs. Users sign in again after the import.
