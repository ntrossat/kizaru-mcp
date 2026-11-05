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
| `FERNET_KEY` | Yes | | Encrypts everything stored in Redis |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Where sign-ins, clients and tokens are kept |
| `HOST` | No | `127.0.0.1` | Address the server listens on |
| `PORT` | No | `8000` | Port the server listens on |
| `PUBLIC_URL` | No | `http://localhost:<PORT>` | The address clients reach this server at, as in [Behind a proxy or a tunnel](#behind-a-proxy-or-a-tunnel). It is the OAuth issuer, and its host is accepted on incoming requests |

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

Or run the package from PyPI, from the directory with `.env`:

```bash
uvx kizaru-mcp
```

Or with Docker, which listens on `0.0.0.0` inside the container:

```bash
docker run --env-file .env -p 8000:8000 ghcr.io/ntrossat/kizaru-mcp
```

Inside the container, `localhost` is the container itself. Point `REDIS_URL` at an address the container can reach, such as `redis://host.docker.internal:6379/0` for Redis on the host. `LIGHTDASH_URL` must be reachable from both the container and your browser, which signs in there.

The MCP endpoint is `<PUBLIC_URL>/mcp`, over Streamable HTTP.

MCP clients keep a stream open to the server. On stop, the server gives them 3 seconds, then closes them.

`GET /health` answers 200 when the server can reach Redis, and 503 when it can't. The Docker image uses it as its health check. Lightdash being down doesn't make the server unhealthy: tools say so instead.

The server logs every tool call, with the user, the tool and its arguments, as in [Logs](architecture.md#logs).

## Behind a proxy or a tunnel

The server listens on `HOST:PORT`. Clients, and their browsers during sign-in, reach it at `PUBLIC_URL`. Behind a proxy or a tunnel the two differ:

1. Set `PUBLIC_URL` to the address clients use, at the root of its host: `https://mcp.example.com`, not `https://example.com/mcp`.
2. Add `<PUBLIC_URL>/oauth/lightdash/callback` to the redirect URIs of the Lightdash OAuth client.
3. Restart the server. Clients connect to `<PUBLIC_URL>/mcp`.

The server accepts requests for `PUBLIC_URL`'s host, and marks its consent cookie `Secure` when `PUBLIC_URL` is HTTPS.

### Reverse proxy

- Serve it over HTTPS, and forward every path to `http://<HOST>:<PORT>`. `HOST` stays `127.0.0.1` when the proxy runs on the same machine.
- Don't buffer responses: Streamable HTTP can answer with a stream of server-sent events. With nginx, set `proxy_buffering off`.

### Tunnel

To reach a local server from Claude.ai or ChatGPT, which need a public HTTPS address:

```bash
cloudflared tunnel --url http://localhost:8000
```

Set `PUBLIC_URL` to the address the tunnel prints, such as `https://abc.trycloudflare.com`, then register its callback with Lightdash and restart, as above. A quick tunnel gets a new address on every start, so repeat these steps each time, or use a named tunnel.

## Run it publicly

- Serve it over HTTPS behind a reverse proxy, as above.
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

To connect Claude.ai or ChatGPT to a local server, run a [tunnel](#tunnel).
