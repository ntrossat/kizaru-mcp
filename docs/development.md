# Development

## Start

Needs Docker, git, curl and [uv](https://docs.astral.sh/uv/).

```bash
make dev
```

`make dev` sets everything up, then runs the MCP server:

1. Sparse-clones Lightdash at `LIGHTDASH_VERSION` into `.lightdash/` (git-ignored): the jaffle shop demo and its Docker files.
2. Starts the demo with the same image tag, layered with `dev/lightdash.compose.yml` (site URL, scheduler, groups, MinIO for the S3 storage Lightdash requires, and Redis) and `dev/entrypoint.sh`, which sets up the database only when it is empty and fixes upstream's reset and seed.
3. Waits for Lightdash on http://localhost:8080.
4. Runs the MCP server on http://localhost:8000/mcp, with `.env`.

Fill in `.env` first, as in [Configuration](configuration.md): register the OAuth client with the local Lightdash and generate a Fernet key.

## Make targets

| Command | Does |
| --- | --- |
| `make dev` | Set up everything, then run the MCP server |
| `make mcp` | Run the MCP server only |
| `make test` | Run the tests |
| `make lint` | Check the code with Ruff: lint and formatting |
| `make reset` | Restart Lightdash with a clean database and the sample data |
| `make logs` | Follow the Lightdash logs |
| `make stop` | Stop Lightdash and Redis |
| `make clean` | Stop and delete the containers, volumes and `.lightdash/` |

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

- The first start seeds the data, migrates and loads the sample content. Later starts keep the database, with what was created and the registered OAuth clients. After `make reset` or `make clean`, register the client again, update `.env`, and MCP clients sign in again.
- The image is `linux/amd64`. On Apple Silicon it runs under emulation and is slower.

## Use your own local Lightdash

`make dev` always starts the demo Lightdash and Redis. To use a Lightdash already running on your machine, skip it:

1. Register an OAuth client with your Lightdash, as in [Configuration](configuration.md), with the redirect URI `http://localhost:8000/oauth/lightdash/callback`.
2. In `.env`, set `LIGHTDASH_URL` to your Lightdash, such as `http://localhost:3000`, with the client's `LIGHTDASH_CLIENT_ID`, `LIGHTDASH_CLIENT_SECRET` and a `FERNET_KEY`.
3. Start a Redis at `REDIS_URL`, such as `docker run -d -p 6379:6379 redis:7-alpine`.
4. Run the server:

```bash
make mcp
```

- The demo stack publishes ports 8080 and 6379: running `make dev` alongside your Lightdash clashes if it uses either.
- The integration tests ignore `.env`: they always target `http://localhost:8080` with the demo users. If your Lightdash is on 8080, `make test` runs them against it and changes its content. Otherwise they skip themselves.

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
