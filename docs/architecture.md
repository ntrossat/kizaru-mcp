# Architecture

One Python process: an MCP server built on the official MCP Python SDK (`MCPServer`, Streamable HTTP), which is also the OAuth authorization server its clients sign in with. It calls the Lightdash REST API with each user's own Lightdash token. All state is in Redis.

## Modules

| Module | Owns |
| --- | --- |
| `server.py` | Builds the server: auth settings, consent and callback routes, tools, allowed hosts |
| `config.py` | Settings from the environment |
| `auth/provider.py` | The OAuth provider: clients, consent page, Lightdash callback, codes and tokens, upstream refresh |
| `auth/store.py` | Encrypted Redis storage and locks |
| `lightdash/client.py` | The async Lightdash API client and its errors |
| `tools/common.py` | A Lightdash client for the signed-in user, error mapping, tool annotations |
| `tools/access.py` | Users, groups, roles, project and space access |
| `tools/content.py` | Unused content, validation errors, moving and deleting content |
| `tools/schedulers.py` | Scheduled deliveries |
| `tools/data.py` | Explores, fields and metric queries |

## Sign-in

1. The MCP client registers itself (`/register`) and opens `/authorize`.
2. The server saves the request for 10 minutes and shows its consent page (`/oauth/consent`), which names the client and where it returns to. One Lightdash OAuth client serves every MCP client, so Lightdash's own consent page can't tell them apart. The form is protected by a CSRF token in a `SameSite=Lax` cookie, one per sign-in, marked `Secure` when `PUBLIC_URL` is HTTPS, and the page can't be framed.
3. On **Allow**, the server redirects to Lightdash's `/authorize` with its own PKCE and the saved request's id as `state`.
4. Lightdash signs the user in and returns to `/oauth/lightdash/callback`. The callback only goes on in the browser that approved the consent page, checked with the same cookie, so a Lightdash link taken from someone else's consent can't send this user's sign-in to another client. The server exchanges the code, reads the user from `/api/v1/user`, creates a grant, and returns its own single-use code to the client. If Lightdash fails, the client gets `error=server_error`.
5. The client exchanges that code, with its PKCE verifier, for the server's tokens.

## Grants and tokens

- A grant is one sign-in. It holds the user's Lightdash access and refresh tokens.
- The client gets the server's own tokens: an access token for 1 hour and a refresh token for 14 days. Both point to the grant. Lightdash tokens never leave the server.
- Refreshing the client's tokens also refreshes the Lightdash ones, so both sign-ins last as long. A tool call refreshes the Lightdash token when it expires within a minute.
- Refreshes run under a Redis lock per grant, and the new tokens are saved before they are used, so a Lightdash refresh token is never used twice.
- When Lightdash refuses a refresh with `invalid_grant`, the grant ends and the user signs in again. Any other error, such as `invalid_client` from a wrong client secret, or Lightdash being unreachable, keeps the grant and the client's refresh token so it can retry.
- Revoking a token ends the grant here and revokes it on Lightdash. It waits for a refresh in flight on the same grant, so the refresh can't bring the grant back.

## Storage

Redis keys are `kizaru-mcp:{client,transaction,code,access,refresh,grant}:<id>`. Token keys are sha256 digests of the tokens, and every value is encrypted with `FERNET_KEY`. Everything expires: client registrations 30 days after their last use, sign-in requests in 10 minutes, codes in 5, tokens and grants with their lifetimes.

## Errors

| Lightdash returns | The tool says |
| --- | --- |
| 401 | The sign-in has ended: reconnect. The grant is ended |
| 403 | Permission denied, with Lightdash's message |
| 404 | Not found, with Lightdash's message |
| Any other error | `Lightdash error <status>`, with its message |
| No response | Lightdash can't be reached: try again |

## Allowed hosts

The SDK protects against DNS rebinding by accepting only `localhost` hosts. The server also accepts `PUBLIC_URL`'s host, so requests through a tunnel or a proxy get in.

## How Lightdash OAuth behaves

Checked on Lightdash 3.93.6, open source, without a license:

- **Discovery:** `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource` exist. The OAuth server is part of the open-source core, at `/api/v1/oauth`.
- **Registration:** open, and `http://localhost` redirect URIs are accepted.
- **Flow:** authorization code with S256 PKCE works without `resource`. The token is then for the REST API, which accepts it as `Authorization: Bearer`. Permissions follow the user.
- **Consent page:** Lightdash shows its own consent page on every sign-in. Its redirect back is an HTML page with a meta refresh, not a 302. In strict security mode the callback also gets an `iss` parameter.
- **Lifetimes:** access token 1 hour, refresh token 14 days (`AUTH_OAUTH_SERVER_ACCESS_TOKEN_LIFETIME`, `AUTH_OAUTH_SERVER_REFRESH_TOKEN_LIFETIME`).
- **Rotation:** each refresh returns a new refresh token. The old one stays usable for 60 seconds (`AUTH_OAUTH_SERVER_REFRESH_TOKEN_ROTATION_GRACE`), then gets `invalid_grant`. Reuse doesn't revoke the newest tokens.
- **Introspection:** `/introspect` needs a Lightdash session, not client credentials. The server doesn't need it: it keeps the Lightdash tokens itself.
- **Scopes:** `read` and `write` are only enforced behind the `AgentIdentity` and `OAuthScopeEnforcement` feature flags, off by default. A token can do whatever the user's role allows.
- **Official Lightdash MCP:** lives in `ee/`, so it needs a license key.
