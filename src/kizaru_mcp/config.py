from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    lightdash_url: str = "http://localhost:8080"
    lightdash_client_id: str = ""
    lightdash_client_secret: str = ""
    public_url: str = "http://localhost:8000"
    fernet_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    host: str = "127.0.0.1"
    port: int = 8000

    def check(self) -> None:
        missing = [
            name.upper()
            for name in ("lightdash_client_id", "lightdash_client_secret", "fernet_key")
            if not getattr(self, name)
        ]
        if missing:
            raise SystemExit(f"Missing settings: {', '.join(missing)}. See .env.example.")

    @property
    def lightdash_base(self) -> str:
        return self.lightdash_url.rstrip("/")

    @property
    def public_base(self) -> str:
        return self.public_url.rstrip("/")

    @property
    def callback_url(self) -> str:
        return f"{self.public_base}/oauth/lightdash/callback"
