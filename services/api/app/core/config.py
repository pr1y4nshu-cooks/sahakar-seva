from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+psycopg://sahakar:sahakar@localhost:55432/sahakar_seva"
    # Comma-separated in the environment (ALLOWED_ORIGINS=http://a,http://b); always a list[str] in code.
    # NoDecode disables pydantic-settings' default JSON decoding so the validator below parses the raw string.
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    # Server-only HS256 secret for local token verification (Mode A). Never expose via VITE_* variables.
    supabase_jwt_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            items = value.split(",")
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            raise ValueError("ALLOWED_ORIGINS must be a comma-separated string or a list of origins")

        origins = [str(item).strip() for item in items if str(item).strip()]
        if not origins:
            raise ValueError("ALLOWED_ORIGINS must contain at least one origin")
        if "*" in origins:
            # Credentials are allowed by CORSMiddleware; a wildcard origin is unsafe and not supported.
            raise ValueError("Wildcard '*' is not permitted in ALLOWED_ORIGINS")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
