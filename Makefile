LIGHTDASH_VERSION ?= 3.93.6
LIGHTDASH_DIR := .lightdash
DEMO_DIR := $(LIGHTDASH_DIR)/examples/full-jaffle-shop-demo
LIGHTDASH := LIGHTDASH_VERSION=$(LIGHTDASH_VERSION) docker compose -p kizaru-mcp-lightdash \
	-f $(DEMO_DIR)/docker-compose.yml -f dev/lightdash.compose.yml
REDIS := docker compose -p kizaru-mcp -f compose.dev.yml
# A pattern for pkill that does not match the shell running it
SERVER := $(CURDIR)/[.]venv/bin/kizaru-mcp

.PHONY: dev setup lightdash wait redis install run test reset logs stop down clean

# Takes over from a server already running from this checkout: stopped, forced after 5 seconds.
# Ctrl+C stops the containers too; a takeover leaves them running.
dev: setup
	@pkill -f '$(SERVER)' && for i in $$(seq 1 25); do pgrep -f '$(SERVER)' > /dev/null || exit 0; sleep 0.2; done; \
		pkill -9 -f '$(SERVER)'; true
	@trap 'interrupted=1' INT; uv run kizaru-mcp; [ -z "$$interrupted" ] || $(MAKE) --no-print-directory stop

setup: lightdash redis install wait

$(DEMO_DIR):
	git clone -q --depth 1 --branch $(LIGHTDASH_VERSION) --filter=blob:none --sparse \
		https://github.com/lightdash/lightdash $(LIGHTDASH_DIR)

# Set on every run, so existing checkouts get new paths too.
lightdash: $(DEMO_DIR)
	git -C $(LIGHTDASH_DIR) sparse-checkout set docker examples/full-jaffle-shop-demo packages/backend/src/generated
	$(LIGHTDASH) up -d

wait:
	@printf "Waiting for Lightdash"
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

# Lightdash sets up an empty database when it starts.
reset:
	$(LIGHTDASH) stop lightdash
	$(LIGHTDASH) exec -T db psql -U postgres -q -c 'drop schema if exists public, graphile_worker cascade'
	$(LIGHTDASH) start lightdash
	@$(MAKE) --no-print-directory wait

logs:
	$(LIGHTDASH) logs -f lightdash

stop:
	$(LIGHTDASH) stop
	$(REDIS) stop

down:
	$(LIGHTDASH) down
	$(REDIS) down

clean:
	-$(LIGHTDASH) down -v
	-$(REDIS) down -v
	rm -rf $(LIGHTDASH_DIR)
