SERVICES := target-service monitoring-service incident-service notification-service
COMPOSE  := docker compose

.PHONY: help env up down build pull deploy logs ps health test lint integration clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

env: ## Create .env from .env.example (if missing)
	@test -f .env || (cp .env.example .env && echo "Created .env - change the passwords")

up: env ## Build from source and start the full stack
	$(COMPOSE) up -d --build

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

build: ## Build all images
	$(COMPOSE) build

pull: ## Pull published images from GHCR
	$(COMPOSE) pull --ignore-buildable

deploy: env ## Pull latest images, restart, verify health (CI/CD stage 5)
	$(COMPOSE) pull --ignore-buildable
	$(COMPOSE) up -d --no-build
	./scripts/healthcheck.sh

logs: ## Follow logs (make logs s=monitoring-service)
	$(COMPOSE) logs -f $(s)

ps: ## Show container status
	$(COMPOSE) ps

health: ## Check health of every service through the gateway
	./scripts/healthcheck.sh

test: ## Run unit tests for every service
	@for s in $(SERVICES); do echo "== $$s"; (cd services/$$s && python -m pytest -q) || exit 1; done

lint: ## Lint all Python code
	ruff check services tests

integration: ## Run integration tests against the running stack
	python -m pytest -q tests/integration

clean: ## Stop the stack AND delete all data volumes
	$(COMPOSE) down -v
