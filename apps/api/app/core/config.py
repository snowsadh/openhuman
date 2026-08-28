import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the project root (apps/api/) regardless of CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# Ensure .env is loaded into os.environ before pydantic-settings reads it.
# This covers Docker and other environments where the .env file may not be
# resolvable at class-definition time.
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)
else:
    load_dotenv(".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/openhuman"
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Agent job worker
    agent_worker_concurrency: int = 4
    agent_job_poll_interval_seconds: float = 1.0
    schedule_poll_interval_seconds: float = 30.0
    schedule_run_timeout_seconds: float = 600.0
    schedule_max_attempts: int = 3
    schedule_delivery_attempts: int = 3

    # Postgres checkpointer (Phase 4) — psycopg-style DSN; falls back to deriving
    # from database_url if empty.
    checkpoint_database_url: str = ""

    # JWT authentication
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    @model_validator(mode="after")
    def validate_db_urls(self) -> "Settings":
        managed_dialect = os.getenv("DB_DIALECT", "").lower()
        managed_host = os.getenv("DB_HOST", "")
        managed_user = os.getenv("DB_USER", "")
        managed_password = os.getenv("DB_PASSWORD", "")
        managed_name = os.getenv("DB_NAME", "")
        managed_port = os.getenv("DB_PORT", "3306")
        if (
            managed_dialect == "mysql"
            and managed_host
            and managed_user
            and managed_password
            and managed_name
        ):
            self.database_url = (
                "mysql+asyncmy://"
                f"{quote(managed_user, safe='')}:{quote(managed_password, safe='')}"
                f"@{managed_host}:{managed_port}/{quote(managed_name, safe='')}"
            )
        elif self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        elif self.database_url.startswith("mysql://"):
            self.database_url = self.database_url.replace("mysql://", "mysql+asyncmy://", 1)
        return self

    # Encryption for bot tokens (AES-256-GCM, 32-byte key)
    encryption_key: str = ""
    encryption_key_previous: str = ""
    """Comma-separated list of previous encryption keys for key rotation.
    When the current key fails to decrypt, each previous key is tried as a fallback.
    Tokens decrypted with an old key should be re-encrypted on next write."""

    # Cognee memory (embedded — SQLite + LanceDB + Kuzu)
    cognee_data_dir: str = "/app/cognee_data"
    cognee_llm_provider: str = "openai"
    cognee_llm_endpoint: str = ""
    cognee_llm_api_key: str = ""
    cognee_llm_model: str = "openai/gpt-4o-mini"
    cognee_embedding_provider: str = "openai"
    cognee_embedding_endpoint: str = ""
    cognee_embedding_api_key: str = ""
    cognee_embedding_model: str = "openai/text-embedding-3-small"
    cognee_skip_connection_test: bool = True

    # Hugging Face (free inference API for tools)
    huggingface_api_key: str = ""

    # OpenAI (used by LangGraph agent)
    openai_api_key: str = ""
    openai_base_url: str = ""  # empty = use OpenAI default; set for compatible APIs
    openai_model: str = "gpt-4o-mini"

    # ArmorIQ — governs MCP execution; missing/unavailable service fails closed.
    armoriq_api_key: str = ""
    armoriq_request_timeout_seconds: int = 30
    armoriq_approval_timeout_seconds: int = 300
    armoriq_register_url: str = "https://api.armoriq.ai/iap/sdk/register"
    armoriq_proxy_url: str = "https://proxy.armoriq.ai"
    armoriq_mcp_public_url: str = ""
    armoriq_mcp_bearer_token: str = ""

    # Document storage
    upload_dir: str = "./uploads"

    # Storage backend: "local" (default) or "s3"
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"
    s3_bucket_name: str = "openhuman-uploads"
    s3_presigned_url_expiry: int = 3600

    # Bot Gateway
    gateway_enabled: bool = False
    """Whether to start the Discord/Slack bot gateway at application startup.
    Should be ``True`` in production or when bot integrations are needed.
    Defaults to ``False`` for local development safety."""

    # Slack App Token (for socket mode) — used in shared mode only
    slack_app_token: str = ""

    # Slack OAuth (for "Connect Slack" onboarding flow) — used in shared mode only
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_oauth_redirect_uri: str = ""

    # Slack identity mode
    slack_identity_mode: str = "fixed"
    """Feature flag: 'fixed' = named bots per employee type (default),
    'shared' = one global Slack app (legacy), 'per_employee' = one
    app slot per AI employee (Pattern A, deprecated)."""

    # Fixed bot credentials — one Slack app per employee type
    # HR bot (Alison)
    slack_bot_hr_client_id: str = ""
    slack_bot_hr_client_secret: str = ""
    slack_bot_hr_app_token: str = ""
    # Support bot (Alex)
    slack_bot_support_client_id: str = ""
    slack_bot_support_client_secret: str = ""
    slack_bot_support_app_token: str = ""
    # Sales bot (Marcus)
    slack_bot_sales_client_id: str = ""
    slack_bot_sales_client_secret: str = ""
    slack_bot_sales_app_token: str = ""
    # General bot (Jordan)
    slack_bot_general_client_id: str = ""
    slack_bot_general_client_secret: str = ""
    slack_bot_general_app_token: str = ""
    # Legal-compliance bot (Taylor)
    slack_bot_legal_client_id: str = ""
    slack_bot_legal_client_secret: str = ""
    slack_bot_legal_app_token: str = ""

    # Frontend URL (used for OAuth redirects back to the dashboard)
    frontend_url: str = "http://localhost:3000"

    # MCP OAuth — per-connector client credentials for the generic MCP OAuth flow.
    # Only connectors that require a registered OAuth app need these (Notion, Vercel,
    # GitHub OAuth mode).  Leave empty for connectors that use PAT / API-key /
    # no-auth modes.
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    notion_client_id: str = ""
    notion_client_secret: str = ""
    vercel_client_id: str = ""
    vercel_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    canva_client_id: str = ""
    canva_client_secret: str = ""

    # The full redirect URI that OAuth providers send the user back to after consent.
    # Must be registered with each provider's OAuth app config.
    # Example: "https://api.example.com/api/mcp/oauth/callback"
    mcp_oauth_redirect_uri: str = ""

    @property
    def mcp_oauth_credentials(self) -> dict[str, dict[str, str]]:
        """Return ``{slug: {client_id, client_secret}}`` for every OAuth connector
        whose credentials are configured in the environment.

        Falls back to ``os.getenv`` for each variable so that values injected
        via ``load_dotenv`` (or set directly in the shell / Docker Compose) are
        picked up even if ``pydantic-settings`` did not set the field.
        """
        creds: dict[str, dict[str, str]] = {}

        def _val(field: str, env: str) -> str:
            return field or os.getenv(env, "")

        if gid := _val(self.gmail_client_id, "GMAIL_CLIENT_ID"):
            creds["gmail"] = {
                "client_id": gid,
                "client_secret": _val(self.gmail_client_secret, "GMAIL_CLIENT_SECRET"),
            }
        if nid := _val(self.notion_client_id, "NOTION_CLIENT_ID"):
            creds["notion"] = {
                "client_id": nid,
                "client_secret": _val(self.notion_client_secret, "NOTION_CLIENT_SECRET"),
            }
        if vid := _val(self.vercel_client_id, "VERCEL_CLIENT_ID"):
            creds["vercel"] = {
                "client_id": vid,
                "client_secret": _val(self.vercel_client_secret, "VERCEL_CLIENT_SECRET"),
            }
        if ghid := _val(self.github_client_id, "GITHUB_CLIENT_ID"):
            creds["github"] = {
                "client_id": ghid,
                "client_secret": _val(self.github_client_secret, "GITHUB_CLIENT_SECRET"),
            }
        if cvid := _val(self.canva_client_id, "CANVA_CLIENT_ID"):
            creds["canva"] = {
                "client_id": cvid,
                "client_secret": _val(self.canva_client_secret, "CANVA_CLIENT_SECRET"),
            }
        return creds

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Fail fast if production is configured with development-only secrets."""
        if self.environment.lower() in {"production", "prod"}:
            if not self.jwt_secret_key or self.jwt_secret_key == "change-me-in-production":
                raise ValueError(
                    "jwt_secret_key must be set to a strong random secret in production"
                )
            if not self.encryption_key or len(self.encryption_key) != 64:
                raise ValueError(
                    "encryption_key must be set to a 32-byte (64 hex character) "
                    "string in production"
                )
            if self.encryption_key_previous.strip():
                for i, part in enumerate(self.encryption_key_previous.split(",")):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        key = bytes.fromhex(part)
                    except ValueError:
                        raise ValueError(
                            f"encryption_key_previous entry #{i + 1} {part!r} "
                            f"is not valid hex"
                        ) from None
                    if len(key) != 32:
                        raise ValueError(
                            f"encryption_key_previous entry #{i + 1} {part!r} "
                            f"is not 32 bytes (64 hex chars)"
                        )
        return self


settings = Settings()
