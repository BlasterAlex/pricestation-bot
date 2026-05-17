VENV := .venv/Scripts

.PHONY: lint test dev cleanup

lint:
	$(VENV)/ruff check --fix .

test:
	docker compose -f deploy/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test

dev:
	docker compose -f deploy/docker-compose.dev.yml up --build -d

cleanup:
	docker compose -f deploy/docker-compose.dev.yml down --remove-orphans
