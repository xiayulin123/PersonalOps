import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parent
_ENV_FILE = _API_ROOT / ".env"
_REPO_DATA = (_API_ROOT / ".." / ".." / "data").resolve()
_USER_DATA = Path.home() / ".personalops" / "data"


def resolve_data_dir() -> Path:
    override = os.environ.get("PERSONALOPS_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if _REPO_DATA.exists():
        return _REPO_DATA
    return _USER_DATA


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: str = ""
    database_url: str = ""
    openai_api_key: str = ""
    chroma_persist_dir: str = ""
    tavily_api_key: str = ""
    web_search_provider: str = "tavily"
    ocr_provider: str = "tesseract"
    tesseract_cmd: str = ""
    ocr_lang: str = "eng"
    ocr_max_pages: int = 150
    ocr_dpi: int = 200
    azure_vision_endpoint: str = ""
    azure_vision_key: str = ""
    azure_ocr_batch_max_pages: int = 2
    azure_ocr_request_delay_sec: float = 4.0
    azure_ocr_max_retries: int = 3
    azure_ocr_poll_timeout_sec: int = 180
    azure_ocr_poll_interval_sec: float = 2.0
    agent_history_turns: int = 5
    cursor_api_key: str = ""
    chat_default_mode: str = "langgraph"
    cursor_agent_model: str = "composer-2.5"
    cursor_agent_timeout_sec: int = 300
    cursor_bridge_startup_timeout_sec: int = 20
    ms_graph_client_id: str = ""
    ms_graph_client_secret: str = ""
    ms_graph_tenant_id: str = "common"
    # Desktop loopback OAuth uses a public client (PKCE, no client_secret in token calls).
    ms_graph_public_client: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""
    google_public_client: bool = True
    life_outlook_poll_sec: int = 120
    life_google_scopes: str = (
        "openid email https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/calendar.readonly"
    )
    life_outlook_scopes: str = (
        "offline_access User.Read Mail.Read Calendars.Read"
    )
    life_oauth_callback_port: int = 8765
    life_oauth_api_port: int = 8000
    life_oauth_microsoft_redirect_uri: str = ""
    life_oauth_google_redirect_uri: str = ""
    github_token: str = ""
    ripgrep_bin: str = ""
    watcher_debounce_sec: float = 2.0
    metrics_enabled: bool = True
    personalization_enabled: bool = True
    prompt_log_retention_days: int = 90
    prompt_log_raw_retention_days: int = 30
    prompt_daily_threshold: int = 100
    prompt_weekly_threshold: int = 700
    prompt_distill_model: str = "gpt-4o-mini"
    auto_memory_require_approval: bool = True
    personalization_distill_schedule: str = "both"
    cloud_archive_enabled: bool = False
    cloud_archive_provider: str = "gcs"
    personalization_archive_key: str = ""
    gcs_archive_bucket: str = ""
    s3_archive_bucket: str = ""
    aws_region: str = "us-east-1"
    google_application_credentials: str = ""
    # "local" = desktop/default; "cloud" = Plan B web (LangGraph only, no Cursor bridge)
    deployment_mode: str = "local"
    jwt_secret: str = ""
    jwt_expire_hours: int = 168
    credentials_encryption_key: str = ""
    gcs_app_bucket: str = ""
    gcs_storage_enabled: bool = True
    admin_email: str = ""
    admin_password: str = ""
    resend_api_key: str = ""
    email_from: str = "PersonalOps <noreply@personalops.live>"
    auth_email_code_ttl_minutes: int = 15
    auth_email_resend_cooldown_sec: int = 60

    def model_post_init(self, __context: object) -> None:
        base = resolve_data_dir()
        base.mkdir(parents=True, exist_ok=True)
        object.__setattr__(self, "data_dir", str(base))

        if not self.database_url:
            db_path = base / "personalops.db"
            object.__setattr__(
                self,
                "database_url",
                f"sqlite+aiosqlite:///{db_path}",
            )
        elif self.database_url.startswith("sqlite") and ":///" in self.database_url:
            # Resolve relative sqlite paths against data_dir when not absolute.
            prefix, _, raw_path = self.database_url.partition(":///")
            path = Path(raw_path)
            if not path.is_absolute():
                resolved = (base / path).resolve()
                object.__setattr__(
                    self,
                    "database_url",
                    f"{prefix}:///{resolved}",
                )

        if not self.chroma_persist_dir:
            object.__setattr__(self, "chroma_persist_dir", str(base / "chroma"))
        else:
            chroma_path = Path(self.chroma_persist_dir)
            if not chroma_path.is_absolute():
                object.__setattr__(
                    self,
                    "chroma_persist_dir",
                    str((base / chroma_path).resolve()),
                )

        if not self.life_oauth_microsoft_redirect_uri.strip():
            if self.deployment_mode.strip().lower() == "cloud":
                port = self.life_oauth_api_port
            else:
                port = self.life_oauth_callback_port
            object.__setattr__(
                self,
                "life_oauth_microsoft_redirect_uri",
                f"http://127.0.0.1:{port}/oauth/microsoft/callback",
            )
        if not self.life_oauth_google_redirect_uri.strip():
            if self.deployment_mode.strip().lower() == "cloud":
                port = self.life_oauth_api_port
            else:
                port = self.life_oauth_callback_port
            object.__setattr__(
                self,
                "life_oauth_google_redirect_uri",
                f"http://127.0.0.1:{port}/oauth/google/callback",
            )

    @property
    def uploads_dir(self) -> str:
        import os

        return os.path.join(self.data_dir, "uploads")

    @property
    def sync_database_url(self) -> str:
        """Sync DB URL for Alembic (async drivers -> sync drivers)."""
        url = self.database_url
        if url.startswith("sqlite+aiosqlite:"):
            return url.replace("sqlite+aiosqlite:", "sqlite:", 1)
        if url.startswith("postgresql+asyncpg:"):
            return url.replace("postgresql+asyncpg:", "postgresql+psycopg2:", 1)
        return url


settings = Settings()
