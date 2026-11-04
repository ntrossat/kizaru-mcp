# Kizaru - Open-source MCP server for Lightdash

[![License](https://img.shields.io/badge/license-MIT-yellow)](https://github.com/ntrossat/kizaru-mcp/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.15+-blue)](https://github.com/ntrossat/kizaru-mcp/blob/main/pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-compatible-green)](https://modelcontextprotocol.io)
[![CI](https://github.com/ntrossat/kizaru-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ntrossat/kizaru-mcp/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

**Kizaru is an open-source [MCP](https://modelcontextprotocol.io) server for self-hosted [Lightdash](https://www.lightdash.com), with per-user sign-in.**

Query your Lightdash data, and manage its access, content and deliveries, from any AI assistant with your Lightdash permissions.

Works with Claude, ChatGPT, Claude Code and any MCP client that supports OAuth.

![Claude Code querying revenue by country and explaining project access through Kizaru](https://raw.githubusercontent.com/ntrossat/kizaru-mcp/main/docs/demo.gif)

## Use cases

- ["Create a monthly report of Jaffle Shop."](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#monthly-report)

  ![Claude writing a monthly report of Jaffle Shop with its revenue trend chart](https://raw.githubusercontent.com/ntrossat/kizaru-mcp/main/docs/use-cases/1-monthly-report-trend.jpg)

- ["What was our revenue by country last quarter?"](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#revenue-by-country)
- ["Who can see the Finance space, and why?"](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#space-access)
- ["Which dashboards has nobody opened in 90 days? Move them to an Archive space."](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#unused-dashboards)
- ["List the broken charts and what's wrong with them."](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#broken-charts)
- ["Give alice@example.com editor access to Jaffle Shop."](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#project-access)
- ["Pause the weekly sales delivery."](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md#deliveries)

See [all use cases with screenshots](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/use-cases.md).

## Features

- **Data:** list explores and their dimensions and metrics, and run queries with filters, sorts and a row limit.
- **Access:** list users, groups and roles. See who can reach a project or a space and why. Grant, change and revoke project access, and manage group membership.
- **Content:** find charts and dashboards nobody views, list validation errors, move and delete content.
- **Deliveries:** list scheduled deliveries with their latest run, pause, edit and delete them.

See [all tools](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/tools.md).

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

   Or run the package from PyPI, from the directory with `.env`:

   ```bash
   uvx kizaru-mcp
   ```

   Or run the Docker image instead, as in [Run](https://github.com/ntrossat/kizaru-mcp/blob/main/docs/configuration.md#run):

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
