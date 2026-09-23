# Common tasks. Everything backend-side runs inside docker-compose, so the host
# needs only Docker and Node (with corepack for pnpm).

-include .env
export

COMPOSE := docker compose
# Tests and migrations use the owner role (it may create the test database);
# the running app uses the non-superuser app role.
AS_OWNER := -e DB_USER=$(POSTGRES_USER) -e DB_PASSWORD=$(POSTGRES_PASSWORD)
BACKEND_RUN := $(COMPOSE) run --rm --no-deps $(AS_OWNER) backend

.PHONY: help env up down build logs ps migrate fixtures seed shell \
        test test-backend test-web e2e lint typecheck check demo-phase-0 demo-phase-1 web-install

help:
	@grep -E '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n",$$1,$$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env; review it before non-local use")

up: env ## Build and start the whole stack, wait until healthy
	$(COMPOSE) up -d --build --wait

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

build: ## Build images
	$(COMPOSE) build

logs: ## Follow logs
	$(COMPOSE) logs -f --tail=100

ps: ## Show service status
	$(COMPOSE) ps

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate

fixtures: ## Rebuild shared test datasets in fixtures/generated
	$(COMPOSE) run --rm --no-deps backend python manage.py build_fixtures

seed: migrate fixtures ## Migrate, build fixtures, create demo districts and users
	$(BACKEND_RUN) python manage.py seed_demo

shell: ## Django shell
	$(COMPOSE) exec backend python manage.py shell

web-install:
	corepack enable && pnpm install

test: test-backend test-web ## Run all automated tests

test-backend: ## Backend tests (pytest, in the container)
	$(COMPOSE) up -d --wait db redis
	$(BACKEND_RUN) pytest

test-web: web-install ## Frontend unit tests (Vitest)
	pnpm test

e2e: web-install ## End-to-end tests against the running stack (needs `make up`)
	pnpm --filter @spatial/web exec playwright install --with-deps chromium
	pnpm --filter @spatial/web e2e

lint: web-install ## Lint backend and frontend
	$(BACKEND_RUN) ruff check .
	$(BACKEND_RUN) ruff format --check .
	pnpm lint

typecheck: web-install ## Type-check backend and frontend
	$(BACKEND_RUN) mypy .
	pnpm typecheck

check: lint typecheck test ## Everything CI runs

demo-phase-0: ## Walk through the Phase 0 deliverable
	./scripts/demo-phase-0.sh

demo-phase-1: ## Walk through the Phase 1 deliverable (needs `make up seed`)
	./scripts/demo-phase-1.sh
