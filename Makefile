LIGHTDASH_VERSION ?= 3.93.6
LIGHTDASH_DIR := .lightdash
DEMO_DIR := $(LIGHTDASH_DIR)/examples/full-jaffle-shop-demo
COMPOSE := LIGHTDASH_VERSION=$(LIGHTDASH_VERSION) docker compose -p kizaru-mcp-lightdash \
	-f $(DEMO_DIR)/docker-compose.yml -f dev/lightdash.compose.yml

.PHONY: dev mcp lightdash wait test lint logs stop clean

dev: lightdash wait .env mcp

mcp:
	uv run kizaru-mcp

$(DEMO_DIR):
	git clone -q --depth 1 --branch $(LIGHTDASH_VERSION) --filter=blob:none --sparse \
		https://github.com/lightdash/lightdash $(LIGHTDASH_DIR)

# Set on every run, so existing checkouts get new paths too.
lightdash: $(DEMO_DIR)
	git -C $(LIGHTDASH_DIR) sparse-checkout set docker examples/full-jaffle-shop-demo
	$(COMPOSE) up -d

wait:
	@printf "Waiting for Lightdash"
	@for i in $$(seq 1 120); do \
		curl -sf http://localhost:8080/api/v1/health > /dev/null && echo " ready: http://localhost:8080" && exit 0; \
		printf "."; sleep 5; \
	done; echo " timed out, see: make logs"; exit 1

# First run only: registers an OAuth client with the local Lightdash and generates FERNET_KEY.
.env:
	uv run python dev/init_env.py

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

logs:
	$(COMPOSE) logs -f lightdash

stop:
	$(COMPOSE) stop

clean:
	-$(COMPOSE) down -v
	rm -rf $(LIGHTDASH_DIR)
	@if head -1 .env 2>/dev/null | grep -q '^# Created by make dev'; then rm .env; fi
