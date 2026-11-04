"""Creates .env for the local Lightdash (make dev): registers an OAuth client with it and generates FERNET_KEY."""

from pathlib import Path

import httpx
from cryptography.fernet import Fernet

LIGHTDASH = "http://localhost:8080"
# make clean deletes .env only when it starts with this line.
MARKER = "# Created by make dev for the local Lightdash: make clean deletes it."

registered = (
    httpx.post(
        f"{LIGHTDASH}/api/v1/oauth/register",
        json={
            "client_name": "kizaru-mcp",
            "redirect_uris": ["http://localhost:8000/oauth/lightdash/callback"],
            "scope": "read write",
        },
    )
    .raise_for_status()
    .json()
)
values = {
    "LIGHTDASH_CLIENT_ID": registered["client_id"],
    "LIGHTDASH_CLIENT_SECRET": registered["client_secret"],
    "FERNET_KEY": Fernet.generate_key().decode(),
}

lines = [MARKER]
for line in Path(".env.example").read_text().splitlines():
    key = line.partition("=")[0]
    lines.append(f"{key}={values[key]}" if key in values else line)
Path(".env").write_text("\n".join(lines) + "\n")
print("Created .env")
