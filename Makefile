LIGHTDASH_VERSION ?= 3.93.6
LIGHTDASH_DIR := .lightdash
DEMO_DIR := $(LIGHTDASH_DIR)/examples/full-jaffle-shop-demo
COMPOSE := LIGHTDASH_VERSION=$(LIGHTDASH_VERSION) docker compose -p kizaru-mcp-lightdash \
	-f $(DEMO_DIR)/docker-compose.yml -f dev/lightdash.compose.yml

.PHONY: dev setup lightdash wait test reset logs stop clean

dev: setup
	uv run kizaru-mcp

setup: lightdash wait

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

test:
	uv run pytest

# Lightdash sets up an empty database when it starts.
reset:
	$(COMPOSE) stop lightdash
	$(COMPOSE) exec -T db psql -U postgres -q -c 'drop schema if exists public, graphile_worker cascade'
	$(COMPOSE) start lightdash
	@$(MAKE) --no-print-directory wait

logs:
	$(COMPOSE) logs -f lightdash

stop:
	$(COMPOSE) stop

clean:
	-$(COMPOSE) down -v
	rm -rf $(LIGHTDASH_DIR)
