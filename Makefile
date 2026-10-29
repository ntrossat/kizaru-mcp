LIGHTDASH_VERSION ?= 3.93.6
LIGHTDASH_DIR := .lightdash
DEMO_DIR := $(LIGHTDASH_DIR)/examples/full-jaffle-shop-demo
LIGHTDASH := LIGHTDASH_VERSION=$(LIGHTDASH_VERSION) docker compose -p lightdash-mcp-lightdash \
	-f $(DEMO_DIR)/docker-compose.yml -f dev/lightdash.compose.yml
REDIS := docker compose -p lightdash-mcp -f compose.dev.yml

.PHONY: dev setup lightdash wait redis install run test reset logs down clean oauth-client

dev: setup run

setup: lightdash redis install wait

$(DEMO_DIR):
	git clone -q --depth 1 --branch $(LIGHTDASH_VERSION) --filter=blob:none --sparse \
		https://github.com/lightdash/lightdash $(LIGHTDASH_DIR)
	git -C $(LIGHTDASH_DIR) sparse-checkout set examples/full-jaffle-shop-demo packages/backend/src/generated

lightdash: $(DEMO_DIR)
	$(LIGHTDASH) up -d

wait:
	@printf "Waiting for Lightdash (dbt seed, migrations, sample content)"
	@for i in $$(seq 1 120); do \
		curl -sf http://localhost:8080/api/v1/health > /dev/null && echo " ready: http://localhost:8080" && exit 0; \
		printf "."; sleep 5; \
	done; echo " timed out, see: make logs"; exit 1

redis:
	$(REDIS) up -d

install:
	uv sync

run:
	uv run lightdash-mcp

test:
	uv run pytest

reset:
	$(LIGHTDASH) restart lightdash
	@$(MAKE) --no-print-directory wait

logs:
	$(LIGHTDASH) logs -f lightdash

down:
	$(LIGHTDASH) down
	$(REDIS) down

clean:
	-$(LIGHTDASH) down -v
	-$(REDIS) down -v
	rm -rf $(LIGHTDASH_DIR)

oauth-client:
	@curl -s -X POST http://localhost:8080/api/v1/oauth/register \
		-H 'Content-Type: application/json' \
		-d '{"client_name":"lightdash-mcp-dev","redirect_uris":["http://localhost:8000/oauth/lightdash/callback"],"scope":"read write"}'
	@echo
