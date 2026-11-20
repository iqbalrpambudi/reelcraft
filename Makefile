.PHONY: setup dev-api dev-web test lint format web-build build api-types migration

setup:  ## Install deps and git hooks
	uv sync
	cd web && npm ci
	uv run pre-commit install

dev-api:  ## API with auto-reload on :8765
	uv run uvicorn reelcraft.api.app:create_app --factory --reload --port 8765

dev-web:  ## Vite dev server, proxies /api to dev-api
	cd web && npm run dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run basedpyright
	uv run lint-imports
	@# models and migrations must agree; checked against a throwaway database
	REELCRAFT_DATA_DIR=$$(mktemp -d) sh -c 'uv run alembic upgrade head && uv run alembic check'
	@# web types must match the API
	$(MAKE) api-types && git diff --exit-code web/src/api/schema.d.ts
	cd web && npm run lint && npm run typecheck

format:
	uv run ruff check --fix .
	uv run ruff format .

web-build:
	cd web && npm run build

build: web-build  ## Wheel + sdist in dist/, web dashboard included
	uv build

api-types:  ## Regenerate web/src/api/schema.d.ts from the FastAPI app
	@tmp=$$(mktemp) && \
	uv run python -c "import json; from reelcraft.api.app import create_app; print(json.dumps(create_app().openapi()))" > $$tmp && \
	cd web && npx --yes openapi-typescript@7.13.0 $$tmp -o src/api/schema.d.ts
	@# shortcut: npx-pinned generator because 7.x peers on TypeScript 5; install it once it supports TS 7

migration:  ## New migration from model changes: make migration m="add scenes"
	REELCRAFT_DATA_DIR=$$(mktemp -d) sh -c 'uv run alembic upgrade head && uv run alembic revision --autogenerate -m "$(m)"'
	uv run ruff check --fix -q src/reelcraft/storage/migrations
	uv run ruff format -q src/reelcraft/storage/migrations
