# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Kizaru: an MCP server for self-hosted Lightdash (data queries, access, content, deliveries). Python 3.15+, managed with uv.

## Commands

| Command | Does |
| --- | --- |
| `make dev` | Start the local Lightdash (Docker, demo data on :8080), then run the server on :8000/mcp |
| `make setup` | Start the local Lightdash only |
| `make test` | `uv run pytest` |
| `make lint` | `ruff check .` and `ruff format --check .` (line length 130) |
| `make reset` | Clean Lightdash database with the sample data |
| `make logs` / `make stop` / `make clean` | Follow logs / stop / delete containers, volumes and `.lightdash/` |

- Single test: `uv run pytest tests/unit/test_provider.py::test_name`
- Unit tests use `respx` and `fakeredis`. Integration tests (`tests/integration`) need the local Lightdash from `make setup`, start the server on port 8765, use Redis db 15, and skip themselves when Lightdash is down. They modify the demo data: run `make reset` after an interrupted run.
- CI runs `uv sync --locked`, ruff and pytest on Python 3.15.
- Run `make lint` and `make test` before a PR, and update `docs/` in the same change as the code.

## Architecture

One process built on the official MCP Python SDK (`MCPServer`, Streamable HTTP). It is both the MCP server and the OAuth authorization server its clients sign in with, and it calls the Lightdash REST API with each user's own Lightdash token. All state is in Redis, encrypted with `FERNET_KEY`. Details in `docs/architecture.md`.

- `server.py`: `create_server` wires the auth settings, the custom routes (`/oauth/consent`, `/oauth/lightdash/callback`) and each tools module's `register(server, provider)`. `transport_security` adds `PUBLIC_URL`'s host to the SDK's localhost-only allowed hosts.
- `auth/provider.py`: `LightdashOAuthProvider` proxies sign-in to Lightdash OAuth. A grant (one sign-in) holds the Lightdash tokens; clients only get the server's own tokens, which point to the grant. Lightdash tokens never leave the server. Refreshes run under a Redis lock per grant and save new tokens before use. `invalid_grant` from Lightdash ends the grant; other errors keep it.
- `auth/store.py`: encrypted Redis storage and locks. Keys are `kizaru-mcp:{client,transaction,code,access,refresh,grant}:<id>`, token keys are sha256 digests.
- `lightdash.py`: async `LightdashClient` and `LightdashError`.
- `tools/common.py`: every tool body runs inside `async with lightdash(provider) as ld:`, which gets the signed-in user's token (refreshing it if needed) and maps Lightdash errors to `ToolError` (401 ends the grant). It also defines the tool annotations (`READ`, `WRITE`, `CREATE`, `DESTRUCTIVE`) and the `Uuid` / `Name` argument types, which must be used for anything interpolated into a Lightdash URL path.
- `tools/{access,content,schedulers,data}.py`: the tools, each module with a `register` function. Destructive tools take `dry_run` and use the `DESTRUCTIVE` annotation. Every tool is listed in `docs/tools.md` with the Lightdash API it calls.

## Configuration

Settings come from `.env` (`config.py`, pydantic-settings). Required: `LIGHTDASH_CLIENT_ID`, `LIGHTDASH_CLIENT_SECRET` (an OAuth client registered with Lightdash, redirect `<PUBLIC_URL>/oauth/lightdash/callback`) and `FERNET_KEY`. See `docs/configuration.md`. Local demo login: `demo@lightdash.com` / `demo_password!`.
