from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
ENV_FILES = (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="经营归因分析系统", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    database_url: str = Field(
        default=(
            "mysql+aiomysql://insight:insight_password@127.0.0.1:3306/"
            "insight_agent?charset=utf8mb4"
        ),
        alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    database_pool_size: int = Field(default=10, ge=1, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=20, ge=0, alias="DATABASE_MAX_OVERFLOW")

    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")
    redis_socket_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        alias="REDIS_SOCKET_TIMEOUT_SECONDS",
    )

    frontend_base_url: str = Field(
        default="http://127.0.0.1:5173",
        alias="FRONTEND_BASE_URL",
    )
    oidc_issuer: str = Field(default="", alias="OIDC_ISSUER")
    oidc_client_id: str = Field(default="", alias="OIDC_CLIENT_ID")
    oidc_client_secret: str = Field(default="", alias="OIDC_CLIENT_SECRET")
    oidc_redirect_uri: str = Field(
        default="http://127.0.0.1:8000/auth/callback",
        alias="OIDC_REDIRECT_URI",
    )
    oidc_scopes: str = Field(default="openid profile email", alias="OIDC_SCOPES")
    oidc_state_ttl_seconds: int = Field(default=600, ge=60, alias="OIDC_STATE_TTL_SECONDS")
    oidc_http_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        alias="OIDC_HTTP_TIMEOUT_SECONDS",
    )

    session_cookie_name: str = Field(default="insight_session", alias="SESSION_COOKIE_NAME")
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")
    session_cookie_http_only: bool = Field(
        default=True,
        alias="SESSION_COOKIE_HTTP_ONLY",
    )
    session_cookie_same_site: Literal["lax", "strict", "none"] = Field(
        default="lax",
        alias="SESSION_COOKIE_SAME_SITE",
    )
    session_ttl_seconds: int = Field(default=28800, ge=300, alias="SESSION_TTL_SECONDS")

    websocket_token_ttl_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        alias="WEBSOCKET_TOKEN_TTL_SECONDS",
    )
    task_queue_name: str = Field(default="insight:task_queue", alias="TASK_QUEUE_NAME")
    task_event_channel_prefix: str = Field(
        default="insight:task_events:",
        alias="TASK_EVENT_CHANNEL_PREFIX",
    )
    task_cancel_ttl_seconds: int = Field(
        default=86400,
        ge=300,
        alias="TASK_CANCEL_TTL_SECONDS",
    )
    task_worker_block_timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        alias="TASK_WORKER_BLOCK_TIMEOUT_SECONDS",
    )
    task_worker_redis_socket_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        alias="TASK_WORKER_REDIS_SOCKET_TIMEOUT_SECONDS",
    )
    task_queue_marker_ttl_seconds: int = Field(
        default=300,
        ge=30,
        alias="TASK_QUEUE_MARKER_TTL_SECONDS",
    )
    task_queue_recovery_interval_seconds: int = Field(
        default=30,
        ge=5,
        alias="TASK_QUEUE_RECOVERY_INTERVAL_SECONDS",
    )
    task_event_replay_limit: int = Field(
        default=500,
        ge=10,
        le=2000,
        alias="TASK_EVENT_REPLAY_LIMIT",
    )
    clarification_timeout_seconds: int = Field(
        default=86400,
        ge=300,
        alias="CLARIFICATION_TIMEOUT_SECONDS",
    )

    model_provider: str = Field(default="", alias="MODEL_PROVIDER")
    model_name: str = Field(default="", alias="MODEL_NAME")
    api_key: str = Field(default="", alias="API_KEY")
    base_url: str = Field(default="", alias="BASE_URL")
    model_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        alias="MODEL_TIMEOUT_SECONDS",
    )
    analysis_agent_model_provider: str = Field(
        default="",
        alias="ANALYSIS_AGENT_MODEL_PROVIDER",
    )
    analysis_agent_model_name: str = Field(
        default="",
        alias="ANALYSIS_AGENT_MODEL_NAME",
    )
    analysis_agent_api_key: str = Field(default="", alias="ANALYSIS_AGENT_API_KEY")
    analysis_agent_base_url: str = Field(default="", alias="ANALYSIS_AGENT_BASE_URL")
    analysis_agent_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        alias="ANALYSIS_AGENT_TIMEOUT_SECONDS",
    )
    agent_model_provider: str = Field(default="", alias="AGENT_MODEL_PROVIDER")
    agent_model_name: str = Field(default="", alias="AGENT_MODEL_NAME")
    agent_model_api_key: str = Field(default="", alias="AGENT_MODEL_API_KEY")
    agent_model_base_url: str = Field(default="", alias="AGENT_MODEL_BASE_URL")
    agent_model_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        alias="AGENT_MODEL_TIMEOUT_SECONDS",
    )
    data_agent_base_url: str = Field(default="", alias="DATA_AGENT_BASE_URL")
    data_agent_api_key: str = Field(default="", alias="DATA_AGENT_API_KEY")
    data_agent_database_url: str = Field(default="", alias="DATA_AGENT_DATABASE_URL")
    data_agent_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        alias="DATA_AGENT_TIMEOUT_SECONDS",
    )
    data_agent_max_scanned_rows: int = Field(
        default=5_000_000,
        ge=1,
        alias="DATA_AGENT_MAX_SCANNED_ROWS",
    )
    data_agent_allowed_tables: str = Field(default="", alias="DATA_AGENT_ALLOWED_TABLES")
    data_agent_model_provider: str = Field(
        default="",
        alias="DATA_AGENT_MODEL_PROVIDER",
    )
    data_agent_model_name: str = Field(default="", alias="DATA_AGENT_MODEL_NAME")
    data_agent_model_api_key: str = Field(default="", alias="DATA_AGENT_MODEL_API_KEY")
    data_agent_model_base_url: str = Field(default="", alias="DATA_AGENT_MODEL_BASE_URL")
    data_agent_model_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        alias="DATA_AGENT_MODEL_TIMEOUT_SECONDS",
    )
    agent_data_root: Path = Field(default=PROJECT_ROOT / "data", alias="AGENT_DATA_ROOT")
    agent_context_message_limit: int = Field(
        default=20,
        ge=1,
        le=100,
        alias="AGENT_CONTEXT_MESSAGE_LIMIT",
    )
    context_summary_message_threshold: int = Field(
        default=30,
        ge=5,
        alias="CONTEXT_SUMMARY_MESSAGE_THRESHOLD",
    )
    context_summary_char_threshold: int = Field(
        default=12_000,
        ge=1000,
        alias="CONTEXT_SUMMARY_CHAR_THRESHOLD",
    )
    context_summary_retain_messages: int = Field(
        default=10,
        ge=1,
        alias="CONTEXT_SUMMARY_RETAIN_MESSAGES",
    )
    agent_max_file_bytes: int = Field(
        default=52_428_800,
        ge=1024,
        alias="AGENT_MAX_FILE_BYTES",
    )
    agent_max_rows: int = Field(default=200_000, ge=1, alias="AGENT_MAX_ROWS")
    agent_preview_rows: int = Field(
        default=20,
        ge=1,
        le=100,
        alias="AGENT_PREVIEW_ROWS",
    )

    trace_id_header: str = Field(default="X-Trace-ID", alias="TRACE_ID_HEADER")
    check_dependencies_on_startup: bool = Field(
        default=False,
        alias="CHECK_DEPENDENCIES_ON_STARTUP",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def data_agent_allowed_table_list(self) -> set[str]:
        return {
            table.strip().lower()
            for table in self.data_agent_allowed_tables.split(",")
            if table.strip()
        }

    @property
    def analysis_model_provider(self) -> str:
        return (
            self.analysis_agent_model_provider
            or self.agent_model_provider
            or self.model_provider
        )

    @property
    def analysis_model_name(self) -> str:
        return self.analysis_agent_model_name or self.agent_model_name or self.model_name

    @property
    def analysis_model_api_key(self) -> str:
        return self.analysis_agent_api_key or self.agent_model_api_key or self.api_key

    @property
    def analysis_model_base_url(self) -> str:
        return self.analysis_agent_base_url or self.agent_model_base_url or self.base_url

    @property
    def analysis_model_timeout_seconds(self) -> float:
        return (
            self.analysis_agent_timeout_seconds
            or self.agent_model_timeout_seconds
            or self.model_timeout_seconds
        )

    @property
    def data_query_model_provider(self) -> str:
        return self.data_agent_model_provider or self.analysis_model_provider

    @property
    def data_query_model_name(self) -> str:
        return self.data_agent_model_name or self.analysis_model_name

    @property
    def data_query_model_api_key(self) -> str:
        return self.data_agent_model_api_key or self.analysis_model_api_key

    @property
    def data_query_model_base_url(self) -> str:
        return self.data_agent_model_base_url or self.analysis_model_base_url

    @property
    def data_query_model_timeout_seconds(self) -> float:
        return self.data_agent_model_timeout_seconds or self.analysis_model_timeout_seconds

    @property
    def effective_worker_redis_socket_timeout_seconds(self) -> float:
        return max(
            self.task_worker_redis_socket_timeout_seconds,
            self.task_worker_block_timeout_seconds + 5.0,
        )

    @field_validator("agent_data_root", mode="after")
    @classmethod
    def resolve_agent_data_root(cls, value: Path) -> Path:
        if value.is_absolute():
            return value.resolve()
        return (BACKEND_ROOT / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
