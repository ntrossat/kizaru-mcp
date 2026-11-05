# Kizaru - Open-source MCP server for Lightdash

[![PyPI](https://img.shields.io/pypi/v/kizaru-mcp)](https://pypi.org/project/kizaru-mcp/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?logo=docker&logoColor=white)](https://github.com/ntrossat/kizaru-mcp/pkgs/container/kizaru-mcp)
[![License](https://img.shields.io/badge/license-MIT-yellow)](https://github.com/ntrossat/kizaru-mcp/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.15+-blue)](https://github.com/ntrossat/kizaru-mcp/blob/main/pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-compatible-green)](https://modelcontextprotocol.io)
[![CI](https://github.com/ntrossat/kizaru-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ntrossat/kizaru-mcp/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Kizaru is an open-source [MCP](https://modelcontextprotocol.io) server for self-hosted [Lightdash](https://www.lightdash.com), with per-user sign-in.**

Query your Lightdash data and manage its dashboards, access and deliveries from any AI assistant, with your own Lightdash permissions.

Works with Claude, ChatGPT, Claude Code and any MCP client that supports OAuth.

![Claude Cowork building a Jaffle Shop revenue and orders report with charts through Kizaru](https://raw.githubusercontent.com/ntrossat/kizaru-mcp/main/docs/demo.gif)

## Features

- **Data:** ask anything about your data, within your access rights.
- **Access:** list users, groups and roles. See who can reach a project or a space and why. Grant, change and revoke project access, and manage group membership.
- **Content:** find charts and dashboards nobody views, list validation errors, move and delete content.
- **Deliveries:** list scheduled deliveries with their latest run, pause, edit and delete them.

See [use cases with screenshots](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md) and [all tools](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/tools.md).

## Principles

- **Acts as you.** Users sign in with Lightdash. Every call runs with their own role, so the assistant can never do more than they can.
- **Safe by default.** Deletions only preview what they would remove until confirmed, and your client asks before running them.
- **Private tokens.** Lightdash tokens never leave the server.

## Quick start

### Try it on a local Lightdash

Needs Docker and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ntrossat/kizaru-mcp && cd kizaru-mcp && make dev
```

This starts Lightdash with demo data on http://localhost:8080 and the MCP server on http://localhost:8000/mcp. Add it to your MCP client, then sign in as `demo@lightdash.com` with `demo_password!`:

```bash
claude mcp add --transport http lightdash http://localhost:8000/mcp
```

### Run it on your Lightdash

Needs Python 3.15+, uv, Redis, and a Lightdash instance (tested on 3.93.6). Its OAuth server is part of open-source Lightdash.

1. Register an OAuth client with your Lightdash, as in [Configuration](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/configuration.md#register-an-oauth-client-with-lightdash).
2. Clone the repository, fill in `.env` (your Lightdash URL, the OAuth client and a `FERNET_KEY`), and start the server:

   ```bash
   git clone https://github.com/ntrossat/kizaru-mcp && cd kizaru-mcp
   cp .env.example .env
   uv sync
   uv run kizaru-mcp
   ```

   Or run the [package from PyPI](https://pypi.org/project/kizaru-mcp/), from the directory with `.env`:

   ```bash
   uvx kizaru-mcp
   ```

   Or run the [Docker image](https://github.com/ntrossat/kizaru-mcp/pkgs/container/kizaru-mcp) instead, as in [Run](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/configuration.md#run):

   ```bash
   docker run --env-file .env -p 8000:8000 ghcr.io/ntrossat/kizaru-mcp
   ```

Web clients such as ChatGPT or Claude on the web can't reach `localhost`. Give the server a public HTTPS address, as in [Behind a proxy or a tunnel](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/configuration.md#behind-a-proxy-or-a-tunnel).

## Documentation

- [Configuration](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/configuration.md): run the server and connect clients
- [Use cases](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md): example prompts with screenshots
- [Tools](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/tools.md): every tool and the Lightdash API it calls
- [Architecture](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/architecture.md): sign-in, tokens, storage and errors
- [Development](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/development.md): local Lightdash, make targets and tests

## Contributing

Issues and pull requests are welcome. Run `make lint` and `make test` before opening a pull request, and update `docs/` in the same change as the code.

## Security

Report vulnerabilities privately, as in [SECURITY.md](https://github.com/ntrossat/kizaru-mcp/blob/main/SECURITY.md).

## License

[MIT](https://github.com/ntrossat/kizaru-mcp/blob/main/LICENSE)
