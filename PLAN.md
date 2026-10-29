# Lightdash MCP server: plan

## Scope

- Admin, governance and content-lifecycle tools that the official Lightdash MCP doesn't cover.
- Built with the official MCP Python SDK v2 on the Lightdash REST API.
- Every call runs as the signed-in user, through Lightdash OAuth.

## Phase 0: Check the untested parts

- [ ] Register an OAuth client with `POST /api/v1/oauth/register`, using the redirect URI `https://<host>/oauth/lightdash/callback`.
- [ ] Run the authorization-code and PKCE flow by hand without `resource`, then call a REST endpoint with `Authorization: Bearer <token>`.
- [ ] Check whether `/introspect` needs client authentication, and what the `read` and `write` scopes allow.
- [ ] Confirm how refresh-token rotation and reuse revocation behave.
- [ ] Start open-source Lightdash in Docker and check whether `/.well-known/oauth-authorization-server` exists.

**Exit point:** OAuth path confirmed, or fall back to per-user personal access tokens.

## Phase 1: Foundation

- [x] Dependency `mcp>=2,<3` and Python 3.10 or later. Use `MCPServer` from `mcp.server.mcpserver` with Streamable HTTP.
- [ ] Configure `AuthSettings` with `issuer_url` and `resource_server_url`, and turn on client registration and revocation.
- [ ] Write `LightdashOAuthProvider`, implementing `OAuthAuthorizationServerProvider`, with the SDK's simple-auth example as reference:
  - store client registrations (`get_client`, `register_client`)
  - in `authorize`: save the client's transaction, show a consent page, generate its own PKCE, and redirect to Lightdash without `resource`
  - a callback route that exchanges the Lightdash code, stores the Lightdash tokens, and issues its own code to the client
  - `exchange_authorization_code` and `exchange_refresh_token`, which issue the server's own tokens
  - `load_access_token`, `load_refresh_token` and `revoke_token`, which also revoke on the Lightdash side
- [ ] Storage: Redis, encrypted with Fernet. It holds client registrations, pending transactions, codes, and the mapping from the server's tokens to each user's Lightdash tokens.
- [ ] Upstream refresh: when a tool runs and the user's Lightdash token has expired, refresh it under a Redis lock.
- [ ] Lightdash client: Pydantic models generated from `swagger.json` and a thin async httpx wrapper.
- [ ] Map errors: a 401 sends the user back through sign-in, and a 403 becomes a clear permission message.
- [x] Configuration through environment variables: `LIGHTDASH_URL`, client credentials, the Fernet key, and the Redis URL.

## Phase 2: Read-only tools

- [ ] Users, groups and roles.
- [ ] Project access per user.
- [ ] Space permissions.
- [ ] Scheduler list.
- [ ] Content validation errors.
- [ ] Unused content, where the API exposes view data.

## Phase 3: Write tools

- [ ] Grant and revoke project access, and change group membership.
- [ ] Move and delete charts, dashboards and spaces.
- [ ] Edit, pause and delete schedulers.
- [ ] Mark tools with `destructiveHint` and `idempotentHint`, and give destructive tools a `dry_run` parameter.

## Phase 4: Testing

- [ ] Unit tests with a mocked Lightdash client (respx).
- [ ] Provider tests: PKCE at both layers, consent, the callback, refresh under the lock, and revocation.
- [ ] A test with two clients registered at once, to confirm each one's tokens stay separate.
- [ ] Integration tests on a test Lightdash instance with two users of different roles, to confirm permissions follow the user.
- [ ] MCP Inspector, then Claude.ai as a custom connector, then Claude Code.

## Phase 5: Deployment

- [ ] Docker on Fly.io, served over HTTPS, with Redis.
- [ ] Log tool calls per user, without data payloads.

## Phase 6: Release (optional)

- [ ] README, a PyPI package runnable with `uvx`, and listings in MCP registries.

## Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| The REST API rejects OAuth Bearer tokens | Switch to per-user personal access tokens. |
| Open-source self-hosted Lightdash has no OAuth server | Offer a personal-access-token mode for those users. |
| Lightdash revokes the whole sign-in after a refresh-token reuse | The Redis lock prevents this; if it still happens the user signs in again. |
| REST endpoints change | Regenerate the models from `swagger.json` in CI. |
| The SDK v2 is still changing in minor releases | Pin the version and run the tests against each upgrade. |

## Already answered from the Lightdash source (not yet tested at runtime)

- **OAuth server:** part of the open-source core (`src/routers/oauthRouter.ts`, `src/services/OAuthService`), mounted at `/api/v1/oauth`, not under `ee/`. It works on a local instance without a license.
- **REST API:** the auth middleware accepts OAuth Bearer tokens. It checks that each token is for the right audience (API or `/mcp`) and applies a scope policy per route.
- **Official Lightdash MCP:** lives in `ee/`, so a local instance doesn't run it without a license key.

---

# Local environment

Three parts: Lightdash running locally with demo data, this repo, and the MCP clients to test with.

```bash
make dev
```

`make dev` sets everything up, then runs the MCP server:

1. Sparse-clones Lightdash at `LIGHTDASH_VERSION` into `.lightdash/` (git-ignored): the jaffle shop demo and `swagger.json`.
2. Starts the demo with the same image tag, layered with `dev/lightdash.compose.yml` (`SITE_URL`, `SCHEDULER_ENABLED`, `GROUPS_ENABLED`).
3. Starts Redis, runs `uv sync`, waits for http://localhost:8080 to be healthy.
4. Runs the MCP server on http://localhost:8000/mcp.

| Command | Does |
| --- | --- |
| `make dev` | Set up everything, then run the MCP server |
| `make setup` | Set up everything, without the server |
| `make run` | Run the MCP server |
| `make test` | Run the tests |
| `make reset` | Restart Lightdash: clean database and sample data |
| `make logs` | Follow the Lightdash logs |
| `make oauth-client` | Register the OAuth client with Lightdash |
| `make down` | Stop Lightdash and Redis |
| `make clean` | Stop and delete containers, volumes and `.lightdash/` |

Use another Lightdash release with `make dev LIGHTDASH_VERSION=<tag>`. A switch needs `make clean` first.

## 1. Lightdash with a dbt project and demo data

The Lightdash repo includes a ready-made demo: the jaffle shop dbt project, a Postgres warehouse, and seeded users and content.

What you get:

- **Database:** one Postgres serves as both the Lightdash database and the warehouse, with dbt seeding the data into the `jaffle` schema.
- **dbt project:** mounted at `/usr/app/dbt` and already connected to a project named "Jaffle shop".
- **Seeded content:** charts, dashboards, nested spaces, groups, and scheduled deliveries.
- **Users:** all with the password `demo_password!`

| User | Role |
| --- | --- |
| demo@lightdash.com | Org 1 admin |
| demo2@lightdash.com | Org 1 editor |
| demo3@lightdash.com | Org 1 viewer |
| another@lightdash.com | Org 2 admin |

Notes:

- Every container start rolls back all migrations and reseeds, so `make reset` gives a clean state. Anything created is lost.
- The image is `linux/amd64`, so on Apple Silicon it runs under emulation and is slower.

## 2. Register the OAuth client with Lightdash

```bash
make oauth-client
```

Put `client_id` and `client_secret` in `.env` (copy from `.env.example`). Lightdash validates redirect URIs; it's not confirmed that it accepts `http://localhost`. If it refuses, register the tunnel URL from step 4 instead.

## 3. This repo

Layout:

```
lightdash-mcp/
├── Makefile                  # make dev
├── pyproject.toml            # uv; mcp>=2,<3, httpx, pydantic, redis, cryptography
├── compose.dev.yml           # Redis only
├── dev/lightdash.compose.yml # pinned image + flags over the upstream demo
├── .env.example
├── src/lightdash_mcp/
│   ├── server.py             # MCPServer + AuthSettings
│   ├── config.py             # settings from env
│   ├── auth/provider.py      # LightdashOAuthProvider
│   ├── lightdash/client.py   # async httpx wrapper
│   ├── lightdash/models.py   # generated
│   └── tools/
└── tests/
    ├── unit/
    └── integration/          # runs against localhost:8080
```

Models come from `.lightdash/packages/backend/src/generated/swagger.json`. Running `datamodel-codegen` on the full file doesn't work as-is (tested on 3.93.6):

- With `--output models.py`, it stops with "Modular references require an output directory": 601 of 3,121 schema names contain dots.
- With an output directory, it fails on file names longer than the OS limit (TypeScript-generated names).
- After renaming the schemas, it writes 32k lines that don't import: an email `pattern` is not a valid Rust regex for pydantic-core.

Generate models only for the schemas the tools use.

## 4. Clients

- **MCP Inspector:** `npx @modelcontextprotocol/inspector`, connect to `http://localhost:8000/mcp`.
- **Claude Code:** `claude mcp add --transport http lightdash-local http://localhost:8000/mcp`
- **Claude.ai:** needs a public HTTPS URL, so run `cloudflared tunnel --url http://localhost:8000`. Set `PUBLIC_URL` to the tunnel URL, and register the tunnel callback with Lightdash as well.
