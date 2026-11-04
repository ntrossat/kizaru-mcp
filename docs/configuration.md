# Configuration

## Requirements

- Python 3.15 or later and [uv](https://docs.astral.sh/uv/).
- Redis.
- A Lightdash instance with its OAuth server. It is part of open-source Lightdash; tested on 3.93.6.

## Register an OAuth client with Lightdash

The server signs users in through one OAuth client registered with Lightdash. Its redirect URI is `<PUBLIC_URL>/oauth/lightdash/callback`, such as `http://localhost:8000/oauth/lightdash/callback`. Change it whenever `PUBLIC_URL` changes.

### In Lightdash

An organization admin registers it in Lightdash:

1. Open **Settings → OAuth applications** (`<LIGHTDASH_URL>/generalSettings/oauthClients`).
2. Click **Register new OAuth application**.
3. Fill in:
   - **Application name**: `Kizaru`, or any name. Users see it when they sign in.
   - **Redirect URI**: `<PUBLIC_URL>/oauth/lightdash/callback`
4. Click **Register application**.
5. Copy the **Client ID** into `LIGHTDASH_CLIENT_ID` and the **Client secret** into `LIGHTDASH_CLIENT_SECRET`. The secret is shown only once.

The client belongs to the organization: only its members can sign in with it. To change the redirect URI later, edit the application in the same list.

### Through the API

Lightdash registration is also open to anyone, without signing in:

```bash
curl -X POST "$LIGHTDASH_URL/api/v1/oauth/register" \
  -H 'Content-Type: application/json' \
  -d '{"client_name":"kizaru-mcp","redirect_uris":["<PUBLIC_URL>/oauth/lightdash/callback"],"scope":"read write"}'
```

Keep the `client_id` and `client_secret` it returns. Lightdash accepts `http://localhost` redirect URIs.

## Environment variables

Copy `.env.example` to `.env` and fill it in.

| Variable | Required | Default | What it does |
| --- | --- | --- | --- |
| `LIGHTDASH_URL` | No | `http://localhost:8080` | The Lightdash instance |
| `LIGHTDASH_CLIENT_ID` | Yes | | The OAuth client from the step above |
| `LIGHTDASH_CLIENT_SECRET` | Yes | | Its secret |
| `PUBLIC_URL` | No | `http://localhost:8000` | The address clients reach this server at. It is the OAuth issuer, and its host is accepted on incoming requests |
| `FERNET_KEY` | Yes | | Encrypts everything stored in Redis |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Where sign-ins, clients and tokens are kept |
| `HOST` | No | `127.0.0.1` | Address the server listens on |
| `PORT` | No | `8000` | Port the server listens on |

Generate a `FERNET_KEY`:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The server stops with `Missing settings: ...` when a required variable is empty.

## Run

```bash
uv sync
uv run kizaru-mcp
```

The MCP endpoint is `<PUBLIC_URL>/mcp`, over Streamable HTTP.

## Run it publicly

- Serve it over HTTPS behind a reverse proxy, with `PUBLIC_URL` set to the HTTPS address. `HOST` stays `127.0.0.1` when the proxy runs on the same machine.
- Rate-limit `/register`, `/authorize` and `/token` at the proxy. Registration is open, as MCP clients need, and each registration or sign-in request is kept in Redis: registrations 30 days after their last use, sign-in requests 10 minutes.
- Keep Redis private, and `FERNET_KEY` and `LIGHTDASH_CLIENT_SECRET` out of the repository.

## Connect a client

| Client | How |
| --- | --- |
| Claude Code | `claude mcp add --transport http lightdash <PUBLIC_URL>/mcp` |
| MCP Inspector | `npx @modelcontextprotocol/inspector`, then connect to `<PUBLIC_URL>/mcp` |
| Claude.ai | Add a custom connector with `<PUBLIC_URL>/mcp`. Claude.ai needs a public HTTPS address |
| ChatGPT | In developer mode, add a connector with `<PUBLIC_URL>/mcp` and OAuth. ChatGPT needs a public HTTPS address |

On first use, the client opens a consent page on this server that names the client and where it returns to. After **Allow**, Lightdash asks the user to sign in and approve, then the client is connected.

To reach a local server from Claude.ai or ChatGPT, run a tunnel such as `cloudflared tunnel --url http://localhost:8000`, set `PUBLIC_URL` to the tunnel address, and register the tunnel's callback URL with Lightdash as well.
