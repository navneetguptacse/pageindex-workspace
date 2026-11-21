from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    auth_required: bool = False
    auth_allow_signup: bool = True
    app_public_url: str = "http://localhost:3000"
    resend_api_key: SecretStr = SecretStr("")
    resend_from_email: str = ""
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    secure_cookies: bool = True
    provider_credentials_encryption_key: SecretStr = SecretStr("")
    requests_per_minute: int = Field(default=120, gt=0)
    provider_requests_per_day: int = Field(default=100, gt=0)
    chat_tokens_per_day: int = Field(default=150_000, gt=0)
    pageindex_api_key: str = ""
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    chat_model: str = "deepseek/deepseek-chat"
    chat_allowed_models: list[str] = Field(default_factory=list)
    chat_history_turns: int = Field(default=8, ge=0, le=50)
    chat_history_max_bytes: int = Field(default=16000, ge=0)
    chat_history_default_tokens: int = Field(default=4000, ge=0)
    chat_history_token_budgets: dict[str, int] = Field(default_factory=dict)
    chat_summary_turns: int = Field(default=4, ge=0, le=20)
    chat_retrieval_pages: int = Field(default=5, ge=1, le=10)
    chat_retrieval_documents: int = Field(default=3, ge=1, le=10)
    chat_retrieval_tokens: int = Field(default=3500, ge=256)
    chat_output_tokens: int = Field(default=8192, ge=128)
    chat_max_turns: int = Field(default=12, ge=1)
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    postgres_host: str = ""
    postgres_db: str = "pageindex"
    postgres_user: str = "pageindex"
    postgres_password: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("")
    preview_cache_ttl_seconds: int = Field(default=300, ge=0, le=3600)
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    max_upload_size_mb: int = Field(default=100, gt=0)
    max_batch_upload_size_mb: int = Field(default=200, gt=0)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    @field_validator("app_public_url")
    @classmethod
    def public_origin(cls, value: str) -> str:
        origin = value.strip().rstrip("/")
        url = urlsplit(origin)
        if (
            not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path
            or "?" in origin
            or "#" in origin
            or "\\" in origin
            or any(character.isspace() for character in origin)
            or (
                url.scheme != "https"
                and (
                    url.scheme != "http"
                    or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                )
            )
        ):
            raise ValueError("Use an HTTPS frontend origin or a local HTTP origin")
        host = url.hostname
        if ":" in host:
            host = f"[{host}]"
        port = url.port
        default_port = 443 if url.scheme == "https" else 80
        authority = host if port in {None, default_port} else f"{host}:{port}"
        return f"{url.scheme}://{authority}"

    @property
    def email_enabled(self) -> bool:
        return bool(
            self.resend_api_key.get_secret_value().strip()
            and self.resend_from_email.strip()
        )

    @property
    def oauth_providers(self) -> list[str]:
        return [
            provider
            for provider, client_id, client_secret in (
                ("google", self.google_client_id, self.google_client_secret),
                ("github", self.github_client_id, self.github_client_secret),
            )
            if client_id.strip() and client_secret.get_secret_value().strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
