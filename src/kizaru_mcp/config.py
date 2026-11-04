from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lightdash_url: str = "http://localhost:8080"
    lightdash_client_id: str = ""
    lightdash_client_secret: str = ""
    # Defaults to http://localhost:<port>.
    public_url: str = ""
    fernet_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("lightdash_url", "public_url")
    @classmethod
    def _strip_slash(cls, url: str) -> str:
        return url.rstrip("/")

    @model_validator(mode="after")
    def _default_public_url(self) -> Self:
        self.public_url = self.public_url or f"http://localhost:{self.port}"
        return self

    def check(self) -> None:
        missing = [
            name.upper() for name in ("lightdash_client_id", "lightdash_client_secret", "fernet_key") if not getattr(self, name)
        ]
        if missing:
            raise SystemExit(f"Missing settings: {', '.join(missing)}. See .env.example.")

    @property
    def callback_url(self) -> str:
        return f"{self.public_url}/oauth/lightdash/callback"
