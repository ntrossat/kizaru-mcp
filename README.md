# Kizaru - Open Source MCP server for self-hosted Lightdash

Query your data from any AI assistant with your Lightdash permissions. And run your instance from the same chat: who has access to what, which content is broken or unused, and which deliveries go out.

Works with Claude, ChatGPT, Claude Code and any MCP client.

![Claude Code querying revenue by country and explaining project access through Kizaru](docs/demo.gif)


## Principles

- **Acts as you.** Users sign in with Lightdash OAuth. Every call runs with their own role, so the assistant can never do more than they can.
- **Safe by default.** Destructive tools take `dry_run` and are marked destructive, so clients ask before running them. Lightdash tokens never leave the server.
- **Small and focused.** Data queries through the semantic layer, plus the administration, governance and content lifecycle.

## Features

- **Data:** list explores and their dimensions and metrics, and run queries with filters, sorts and a row limit.
- **Access:** list users, groups and roles. See who can reach a project or a space and why. Grant, change and revoke project access, and manage group membership.
- **Content:** find charts and dashboards nobody views, list validation errors, move and delete content.
- **Deliveries:** list scheduled deliveries with their latest run, pause, edit and delete them.

See [all tools](docs/tools.md).

## Quick start

### Try it on a local Lightdash

Needs Docker and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ntrossat/kizaru-mcp && cd kizaru-mcp
cp .env.example .env   # an OAuth client registered with the local Lightdash and a FERNET_KEY
make dev
```

This starts Lightdash with demo data on http://localhost:8080 and runs the MCP server on http://localhost:8000/mcp. Register the OAuth client once Lightdash is up, as in [Configuration](docs/configuration.md), fill in `.env`, then run `make dev` again.

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
uv run kizaru-mcp
```

See [Configuration](docs/configuration.md).

## Documentation

- [Configuration](docs/configuration.md): run the server and connect clients
- [Tools](docs/tools.md): every tool and the Lightdash API it calls
- [Architecture](docs/architecture.md): sign-in, tokens, storage and errors
- [Development](docs/development.md): local Lightdash, make targets and tests

## Contributing

Issues and pull requests are welcome. Run `make lint` and `make test` before opening a pull request, and update `docs/` in the same change as the code.

## Security

Report vulnerabilities privately, as in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
