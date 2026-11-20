.PHONY: setup dev-api dev-web test lint format web-build build

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
	cd web && npm run lint && npm run typecheck

format:
	uv run ruff check --fix .
	uv run ruff format .

web-build:
	cd web && npm run build

build: web-build  ## Wheel + sdist in dist/, web dashboard included
	uv build
