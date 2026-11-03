# Development

## Start

Needs Docker, git, curl and [uv](https://docs.astral.sh/uv/).

```bash
make dev
```

`make dev` sets everything up, then runs the MCP server:

1. Sparse-clones Lightdash at `LIGHTDASH_VERSION` into `.lightdash/` (git-ignored): the jaffle shop demo, its Docker files and `swagger.json`.
2. Starts the demo with the same image tag, layered with `dev/lightdash.compose.yml` (site URL, scheduler, groups, and MinIO for the S3 storage Lightdash requires) and `dev/entrypoint.sh`, which fixes upstream's reset and seed.
3. Starts Redis, runs `uv sync`, and waits for Lightdash on http://localhost:8080.
4. Registers an OAuth client with the local Lightdash and generates a Fernet key, kept in `.lightdash/mcp.env` (`dev/env.py`). A client Lightdash no longer knows is registered again. These values take precedence over `.env`.
5. Runs the MCP server on http://localhost:8000/mcp.

Nothing needs to go in `.env`. Set `PUBLIC_URL` there to run behind a tunnel: the client is registered with that callback URL.

## Make targets

| Command | Does |
| --- | --- |
| `make dev` | Set up everything, then run the MCP server |
| `make setup` | Set up everything, without the server |
| `make run` | Run the MCP server with `.env` only, as in [Configuration](configuration.md) |
| `make test` | Run the tests |
| `make reset` | Restart Lightdash with a clean database and the sample data |
| `make logs` | Follow the Lightdash logs |
| `make down` | Stop Lightdash and Redis |
| `make clean` | Stop and delete the containers, volumes and `.lightdash/`, with `mcp.env` |

Use another Lightdash release with `make dev LIGHTDASH_VERSION=<tag>`. Run `make clean` before switching.

## The local Lightdash

The demo comes from the Lightdash repository:

- **Database:** one Postgres is both the Lightdash database and the warehouse. dbt seeds the data into the `jaffle` schema.
- **dbt project:** the jaffle shop, mounted at `/usr/app/dbt`, connected to a project named "Jaffle shop".
- **Content:** charts, dashboards, nested spaces, groups and scheduled deliveries.
- **Users:** all with the password `demo_password!`.

| User | Role |
| --- | --- |
| `demo@lightdash.com` | Organization 1 admin |
| `demo2@lightdash.com` | Organization 1 editor |
| `demo3@lightdash.com` | Organization 1 viewer |
| `another@lightdash.com` | Organization 2 admin |

- Every container start drops the Lightdash schemas, migrates and reseeds. Anything created is lost, and so are registered OAuth clients. The next `make dev` registers a new one, and MCP clients sign in again.
- The image is `linux/amd64`. On Apple Silicon it runs under emulation and is slower.

## Tests

```bash
make test
```

| Suite | Runs against | Covers |
| --- | --- | --- |
| `tests/unit` | `respx` and `fakeredis` | Encryption at rest, refresh under the lock, ended sign-ins, error mapping, revocation, separate grants, the Lightdash client |
| `tests/integration` | The local Lightdash and Redis database 15 | The whole sign-in over HTTP, every tool, admin against viewer, refresh, revoke, PKCE, the consent cookie |

- The integration tests register their own OAuth clients, start the server on port 8765, and sign in as `demo@` (admin) and `demo3@` (viewer). They need nothing in `.env`, and they are skipped when Lightdash is down.
- They change the local Lightdash: they create and delete spaces and schedulers, grant and revoke access, and move a chart and back. They expect the seeded demo data, so run `make reset` if a run was interrupted.

## Lightdash API models

The tools don't use generated models: each picks the fields it returns. Running `datamodel-codegen` on `swagger.json` doesn't work as-is (3.93.6):

- With `--output models.py`, it stops with "Modular references require an output directory": 601 of 3,121 schema names contain dots.
- With an output directory, it fails on file names longer than the OS limit.
- After renaming the schemas, it writes 32,000 lines that don't import: an email `pattern` isn't a valid regex for pydantic-core.

The schema also has errors: creating a chart scheduler requires `appUuid` and `appName`, which only apply to data apps. Send them as `null`.
