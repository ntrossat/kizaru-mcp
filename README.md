# lightdash-mcp

MCP server for Lightdash admin, governance and content lifecycle. Every call runs as the signed-in user, through Lightdash OAuth.

```bash
make dev
```

Starts Lightdash with the jaffle shop dbt project and sample data on http://localhost:8080 (`demo@lightdash.com` / `demo_password!`), Redis, and the MCP server on http://localhost:8000/mcp.

See [PLAN.md](PLAN.md) for the roadmap and all make targets.
