.PHONY: up up-fg down build logs logs-app logs-ollama restart test test-health test-story test-scan test-webhook shell model-pull model-list status

# Start all services
up:
	docker compose up -d

# Start with logs in foreground
up-fg:
	docker compose up

# Stop all services
down:
	docker compose down

# Rebuild app image and restart
build:
	docker compose build app

restart:
	docker compose restart app

# Tail logs
logs:
	docker compose logs -f

logs-app:
	docker compose logs -f app

logs-ollama:
	docker compose logs -f ollama

# Run unit + integration tests (local python, no docker)
test:
	python -m pytest --tb=short -q

# --- Live smoke tests against running service ---

BASE_URL  ?= http://localhost:8000
API_KEY   ?= $(shell grep '^API_KEY=' .env | head -1 | sed 's/^API_KEY=//')
WH_SECRET ?= $(shell grep '^GITHUB_WEBHOOK_SECRET=' .env | head -1 | sed 's/^GITHUB_WEBHOOK_SECRET=//')

test-health:
	curl -sf $(BASE_URL)/health | python3 -m json.tool

test-story:
	curl -sf -X POST $(BASE_URL)/stories \
	  -H "Content-Type: application/json" \
	  -H "X-Api-Key: $(API_KEY)" \
	  -d '{"repo":"$(REPO)","story":"As a user I want to reset my password so I can regain access"}' \
	  && echo " → 202 accepted"

test-scan:
	curl -sf -X POST $(BASE_URL)/scan \
	  -H "Content-Type: application/json" \
	  -H "X-Api-Key: $(API_KEY)" \
	  -d '{"repo":"$(REPO)"}' \
	  && echo " → 202 accepted"

test-webhook:
	@BODY='{"action":"opened","issue":{"number":1,"title":"Test issue","body":"## Acceptance Criteria\n- [ ] Works"},"repository":{"full_name":"$(REPO)"}}'; \
	SIG="sha256=$$(echo -n "$$BODY" | openssl dgst -sha256 -hmac "$(WH_SECRET)" | awk '{print $$2}')"; \
	curl -sf -X POST $(BASE_URL)/webhook \
	  -H "Content-Type: application/json" \
	  -H "X-GitHub-Event: issues" \
	  -H "X-Hub-Signature-256: $$SIG" \
	  -d "$$BODY" \
	  && echo " → 202 accepted"

# Ollama model management
model-pull:
	docker compose exec ollama ollama pull $(shell grep ^OLLAMA_MODEL .env | cut -d= -f2)

model-list:
	docker compose exec ollama ollama list

# Open shell in app container
shell:
	docker compose exec app bash

# Service status
status:
	docker compose ps
