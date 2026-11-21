.DEFAULT_GOAL := help

UV ?= uv
NPM ?= npm
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
PAGEINDEX_BACKEND_URL ?= http://127.0.0.1:$(BACKEND_PORT)

.PHONY: help install run format lint build test prune purge \
	install-backend install-frontend run-backend run-frontend \
	format-backend format-frontend lint-backend lint-frontend \
	build-backend build-frontend test-backend test-frontend \
	prune-backend prune-frontend

help:
	@printf '%s\n' \
		'make install  Install both projects from their lockfiles' \
		'make run      Start both development servers' \
		'make format   Format Python and frontend source files' \
		'make lint     Run Ruff and Oxlint' \
		'make build    Compile backend sources and build Next.js for production' \
		'make test     Run backend tests and frontend type checks' \
		'make prune    Remove local caches, build output, and test artifacts' \
		'make purge    Prune and remove node_modules and Python virtual environments'

install: install-backend install-frontend

run:
	$(MAKE) -j2 run-backend run-frontend

format: format-backend format-frontend
lint: lint-backend lint-frontend
build: build-backend build-frontend
test: test-backend test-frontend
prune: prune-backend prune-frontend

purge: prune
	$(RM) -r -- frontend/node_modules backend/.venv backend/venv

install-backend:
	cd backend && $(UV) sync --locked

install-frontend:
	cd frontend && $(NPM) ci

run-backend:
	cd backend && exec $(UV) run --locked fastapi dev --port $(BACKEND_PORT)

run-frontend:
	cd frontend && PAGEINDEX_BACKEND_URL="$(PAGEINDEX_BACKEND_URL)" exec $(NPM) run dev -- --hostname 127.0.0.1 --port $(FRONTEND_PORT)

format-backend:
	cd backend && $(UV) run --locked ruff format app main.py tests

format-frontend:
	cd frontend && $(NPM) run format

lint-backend:
	cd backend && $(UV) run --locked ruff check app main.py tests

lint-frontend:
	cd frontend && $(NPM) run lint

build-backend:
	cd backend && $(UV) run --locked python -m compileall -q app main.py

build-frontend:
	cd frontend && $(NPM) run build

test-backend:
	cd backend && $(UV) run --locked python -m unittest discover -s tests -v

test-frontend:
	cd frontend && $(NPM) run typecheck

prune-backend:
	$(RM) -r -- backend/__pycache__ backend/.pytest_cache backend/.ruff_cache \
		backend/.mypy_cache backend/.pyright backend/.uv-cache \
		backend/build backend/dist backend/htmlcov backend/.coverage backend/.coverage.* \
		backend/*.egg-info backend/*.pyc backend/*.pyo
	find backend/app backend/tests -type d -name __pycache__ -prune -exec $(RM) -r -- {} +
	find backend/app backend/tests -type f \( -name '*.pyc' -o -name '*.pyo' \) -exec $(RM) -- {} +

prune-frontend:
	$(RM) -r -- frontend/.next frontend/.turbo frontend/.npm \
		frontend/out frontend/build frontend/dist frontend/coverage \
		frontend/playwright-report frontend/test-results frontend/next-env.d.ts \
		frontend/*.tsbuildinfo frontend/npm-debug.log*
