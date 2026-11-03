"""Writes the MCP server's settings for the local Lightdash: an OAuth client and a Fernet key.

They live in the given file (.lightdash/mcp.env), next to the Lightdash checkout they belong to, and take
precedence over .env, which is left alone. A client Lightdash no longer knows, as after `make reset`, is
registered again. The Fernet key is kept, so what Redis holds stays readable.
"""

import sys
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from kizaru_mcp.config import Settings


def read(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def client_is_known(settings: Settings, client_id: str, client_secret: str) -> bool:
    """Lightdash answers a refresh with a made-up token with invalid_grant for a known client, invalid_client otherwise."""
    response = httpx.post(
        f"{settings.lightdash_base}/api/v1/oauth/token",
        data={"grant_type": "refresh_token", "refresh_token": "probe", "client_id": client_id, "client_secret": client_secret},
    )
    return response.json().get("error") == "invalid_grant"


def register(settings: Settings) -> dict[str, str]:
    response = httpx.post(
        f"{settings.lightdash_base}/api/v1/oauth/register",
        json={"client_name": "kizaru-mcp-dev", "redirect_uris": [settings.callback_url], "scope": "read write"},
    )
    response.raise_for_status()
    client = response.json()
    return {"LIGHTDASH_CLIENT_ID": client["client_id"], "LIGHTDASH_CLIENT_SECRET": client["client_secret"]}


def main() -> None:
    path = Path(sys.argv[1])
    settings = Settings()
    env = read(path)
    if not env.get("LIGHTDASH_CLIENT_ID") or not client_is_known(settings, env["LIGHTDASH_CLIENT_ID"], env.get("LIGHTDASH_CLIENT_SECRET", "")):
        env |= register(settings)
        print(f"Registered OAuth client {env['LIGHTDASH_CLIENT_ID']} with {settings.lightdash_base}")
    env.setdefault("FERNET_KEY", Fernet.generate_key().decode())
    path.write_text("".join(f"{key}={value}\n" for key, value in env.items()))
    path.chmod(0o600)


if __name__ == "__main__":
    main()
