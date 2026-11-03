# lightdash-mcp

An MCP server for running a Lightdash instance: who has access to what, which content is broken or unused, and which deliveries go out. Ask an AI assistant, and it answers and acts as you, with your Lightdash permissions.

## Principles

- **Acts as you.** Users sign in with Lightdash OAuth. Every call runs with their own role, so the assistant can never do more than they can.
- **Safe by default.** Destructive tools take `dry_run` and are marked destructive, so clients ask before running them. Lightdash tokens never leave the server.
- **Small and focused.** Administration, governance and content lifecycle: what the official Lightdash MCP doesn't cover.

## Features

- **Access:** list users, groups and roles. See who can reach a project or a space and why. Grant, change and revoke project access, and manage group membership.
- **Content:** find charts and dashboards nobody views, list validation errors, move and delete content.
- **Deliveries:** list scheduled deliveries with their latest run, pause, edit and delete them.

See [all tools](docs/tools.md).

## Quick start

### Try it on a local Lightdash

Needs Docker and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ntrossat/lightdash-mcp && cd lightdash-mcp
make dev
```

This starts Lightdash with demo data on http://localhost:8080, registers the server's OAuth client with it, and runs the MCP server on http://localhost:8000/mcp. Nothing to configure.

Add `http://localhost:8000/mcp` to your MCP client, then sign in as `demo@lightdash.com` with `demo_password!`:

```bash
claude mcp add --transport http lightdash http://localhost:8000/mcp
```

See [Development](docs/development.md).

### Run it on your Lightdash

Needs Python 3.10+, uv, Redis, and Lightdash with its OAuth server (open source, tested on 3.93.6).

```bash
cp .env.example .env   # the Lightdash URL, its OAuth client and a FERNET_KEY
uv sync
uv run lightdash-mcp
```

See [Configuration](docs/configuration.md).

## Documentation

- [Configuration](docs/configuration.md): run the server and connect clients
- [Tools](docs/tools.md): every tool and the Lightdash API it calls
- [Architecture](docs/architecture.md): sign-in, tokens, storage and errors
- [Development](docs/development.md): local Lightdash, make targets and tests
- [Roadmap](docs/roadmap.md): what is done and what is next

## Contributing

Issues and pull requests are welcome. Run `make test` before opening a pull request, and update `docs/` in the same change as the code.

## License

[MIT](LICENSE)
