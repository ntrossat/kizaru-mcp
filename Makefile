LIGHTDASH_VERSION ?= 3.93.6
LIGHTDASH_DIR := .lightdash
DEMO_DIR := $(LIGHTDASH_DIR)/examples/full-jaffle-shop-demo
DEV_ENV := $(LIGHTDASH_DIR)/mcp.env
LIGHTDASH := LIGHTDASH_VERSION=$(LIGHTDASH_VERSION) docker compose -p kizaru-mcp-lightdash \
	-f $(DEMO_DIR)/docker-compose.yml -f dev/lightdash.compose.yml
REDIS := docker compose -p kizaru-mcp -f compose.dev.yml

.PHONY: dev setup lightdash wait redis install run test reset logs down clean

# The OAuth client and Fernet key for the local Lightdash come from $(DEV_ENV), not .env.
dev: setup
	uv run python dev/env.py $(DEV_ENV)
	uv run --env-file $(DEV_ENV) kizaru-mcp

setup: lightdash redis install wait

$(DEMO_DIR):
	git clone -q --depth 1 --branch $(LIGHTDASH_VERSION) --filter=blob:none --sparse \
		https://github.com/lightdash/lightdash $(LIGHTDASH_DIR)

# Set on every run, so existing checkouts get new paths too.
lightdash: $(DEMO_DIR)
	git -C $(LIGHTDASH_DIR) sparse-checkout set docker examples/full-jaffle-shop-demo packages/backend/src/generated
	@grep -qx mcp.env $(LIGHTDASH_DIR)/.git/info/exclude || echo mcp.env >> $(LIGHTDASH_DIR)/.git/info/exclude
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
	uv run kizaru-mcp

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
