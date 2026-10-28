from functools import lru_cache
from typing import Annotated, Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Hard ceiling also enforced by a database CHECK on bookings/settlements.
ABSOLUTE_FEE_CEILING_BPS = 2000


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

    # --- ILLUSTRATIVE example inputs only (not pricing) ---
    # Live pricing comes exclusively from the active row in `fee_policies` (0006), managed with
    # `python -m app.cli.fee_policy`. These two values are used only by `bootstrap-example`, which activates a
    # labelled illustrative policy for local development when no policy is active. They are not final pricing.
    platform_fee_bps: int = 1000
    platform_fee_cap_bps: int = 1500

    # --- External RFC 3161 timestamping of ledger checkpoints (0005; optional) ---
    # Only the 32-byte checkpoint digest and a random nonce are sent. TSA_CA_FILE is the *pinned* trust
    # anchor used to verify responses; a certificate inside a response is never trusted on its own.
    tsa_url: str | None = None
    tsa_name: str | None = None
    tsa_ca_file: str | None = None
    tsa_timeout_seconds: float = 15.0
    anchor_max_attempts: int = 5
    anchor_retry_base_seconds: int = 30
    # Background loop in the API process that creates checkpoints and submits them after commit.
    anchor_worker_enabled: bool = False
    anchor_worker_interval_seconds: int = 20

    # --- Local development identity (never production auth; see MVP_MARKETPLACE_CONTRACT §9) ---
    dev_auth_enabled: bool = False
    dev_auth_secret: str | None = None
    dev_auth_passcode: str | None = None
    dev_auth_email_domain: str = "demo.sahakar.test"

    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def validate_policies(self) -> "Settings":
        if not 0 <= self.platform_fee_cap_bps <= ABSOLUTE_FEE_CEILING_BPS:
            raise ValueError(f"PLATFORM_FEE_CAP_BPS must be between 0 and {ABSOLUTE_FEE_CEILING_BPS}")
        if not 0 <= self.platform_fee_bps <= self.platform_fee_cap_bps:
            raise ValueError("PLATFORM_FEE_BPS must be between 0 and PLATFORM_FEE_CAP_BPS")
        if self.dev_auth_enabled:
            if self.app_env.lower() != "development":
                raise ValueError("DEV_AUTH_ENABLED is only permitted when APP_ENV=development")
            if not self.dev_auth_secret or len(self.dev_auth_secret) < 32:
                raise ValueError("DEV_AUTH_SECRET must be set (at least 32 characters) when dev auth is enabled")
            if not self.dev_auth_passcode or len(self.dev_auth_passcode) < 8:
                raise ValueError("DEV_AUTH_PASSCODE must be set (at least 8 characters) when dev auth is enabled")
        if (self.tsa_url and not self.tsa_ca_file) or (self.tsa_ca_file and not self.tsa_url):
            raise ValueError("TSA_URL and TSA_CA_FILE must be configured together (pinned trust anchor required)")
        return self

    @property
    def tsa_configured(self) -> bool:
        return bool(self.tsa_url and self.tsa_ca_file)

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
