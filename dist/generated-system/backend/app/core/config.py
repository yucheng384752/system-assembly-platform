"""Application configuration management using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_files() -> list[str]:
    """
    回傳 .env 候選絕對路徑（依優先序，後者覆蓋前者）。

    config.py 位於 system/backend/app/core/config.py，故：
      parents[2] = backend/   parents[3] = system/
    安裝精靈把 .env 寫在 system/.env，但後端常從 backend/ 啟動，
    因此 pydantic 預設的相對 ".env"（依 cwd）會找不到。改用絕對路徑涵蓋兩處。
    """
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    try:
        backend_dir = here.parents[2]
        system_dir = here.parents[3]
        candidates.extend([system_dir / ".env", backend_dir / ".env"])
    except IndexError:
        pass
    # cwd 的 .env 優先序最高（最後載入），保留既有行為（Docker 等）
    candidates.append(Path(os.getcwd()) / ".env")
    # 去重並保留順序
    seen: set[str] = set()
    out: list[str] = []
    for p in candidates:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Uses Pydantic Settings for type validation and automatic loading
    from .env files and environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        enable_decoding=False,
        extra="ignore",
    )

    # Database settings
    database_url: str = Field(
        default="postgresql+asyncpg://app:app_secure_password@localhost:5432/form_analysis_db",
        description="Database connection URL",
        validation_alias=AliasChoices("database_url", "DATABASE_URL"),
    )

    # API server settings
    api_host: str = Field(default="127.0.0.1", description="API server host")
    api_port: int = Field(default=8000, ge=1, le=65535, description="API server port")

    # File upload settings
    max_upload_size_mb: int = Field(
        default=10, ge=1, le=100, description="Maximum file upload size in MB"
    )
    upload_temp_dir: str = Field(
        default="./uploads", description="Temporary directory for file uploads"
    )
    allowed_extensions: list[str] = Field(
        default=["csv", "xlsx", "pdf"], description="Allowed file extensions"
    )
    max_concurrent_uploads: int = Field(
        default=10, ge=1, le=100, description="Maximum concurrent upload operations"
    )

    # External PDF conversion server (optional)
    pdf_server_url: str = Field(
        default="",
        description="Base URL of external PDF conversion service (optional)",
        alias="PDF_SERVER_URL",
    )
    # pdf_server_convert_path: str = Field(
    #     default="/process",
    #     description="Convert endpoint path on PDF server",
    #     alias="PDF_SERVER_CONVERT_PATH",
    # )
    pdf_server_timeout_seconds: int = Field(
        default=1800,
        ge=1,
        le=3600,
        description="Read-timeout (seconds) for PDF server requests; controls how long to wait for a response from the external PDF conversion service",
        alias="PDF_SERVER_TIMEOUT_SECONDS",
    )
    pdf_server_max_concurrent: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max concurrent PDF conversion requests to external server",
        alias="PDF_SERVER_MAX_CONCURRENT",
    )

    pdf_server_table: str = Field(
        default="",
        description="Default table name required by some PDF servers (e.g. /process expects table=P1/P2/P3)",
        alias="PDF_SERVER_TABLE",
    )

    # CORS settings (using string for environment variable compatibility)
    cors_origins_str: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated CORS origins",
        alias="CORS_ORIGINS",
    )

    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json or text)")

    # Development settings
    debug: bool = Field(default=False, description="Enable debug mode")
    reload: bool = Field(default=False, description="Enable auto-reload (development)")
    environment: str = Field(
        default="production", description="Application environment"
    )

    # Multi-tenant mode
    # When enabled, legacy import endpoints (/api/upload, /api/errors.csv, /api/import)
    # are disabled to prevent data from landing only in legacy tables.
    multi_tenant_enabled: bool = Field(
        default=False,
        description="Enable multi-tenant mode; disables legacy import endpoints",
        alias="MULTI_TENANT_ENABLED",
    )

    # Security settings
    secret_key: str = Field(
        default="qI5s1RT9GCr8wlqnfh1XxOZBO_47lSqedali3vHGOVk",
        min_length=32,
        description="Secret key for JWT and other crypto operations",
    )

    # Lightweight auth (API key) - for blocking public scanning/attacks
    # Prefer a reverse proxy / WAF for stronger protection.
    auth_mode: str = Field(
        default="api_key",
        description="Auth mode: off|api_key",
        alias="AUTH_MODE",
    )
    allow_auth_off: bool = Field(
        default=False,
        description="Explicitly allow AUTH_MODE=off. Never enable in production.",
        alias="ALLOW_AUTH_OFF",
    )
    auth_api_key_header: str = Field(
        default="X-API-Key",
        description="Header name for API key",
        alias="AUTH_API_KEY_HEADER",
    )
    auth_protect_prefixes_str: str = Field(
        default="/api",
        description="Comma-separated path prefixes to protect (e.g. /api,/api/v2)",
        alias="AUTH_PROTECT_PREFIXES",
    )

    auth_exempt_paths_str: str = Field(
        default="/healthz,/docs,/redoc,/openapi.json,/api/auth/login",
        description=(
            "Comma-separated path prefixes to exempt from auth when AUTH_MODE=api_key "
            "(e.g. /healthz,/docs,/openapi.json)."
        ),
        alias="AUTH_EXEMPT_PATHS",
    )

    # Admin bootstrap/auth (for privileged ops like creating tenants)
    # Comma-separated raw keys. Keep this small and rotate as needed.
    admin_api_keys_str: str = Field(
        default="",
        description="Comma-separated admin API keys for privileged operations",
        alias="ADMIN_API_KEYS",
    )

    admin_api_key_header: str = Field(
        default="X-Admin-API-Key",
        description="Header name for admin API key",
        alias="ADMIN_API_KEY_HEADER",
    )

    # -----------------------------
    # Bootstrap Manager User (optional)
    # -----------------------------
    # For first-time startup, you may want the server to auto-create a tenant manager.
    # This is best-effort and will never block startup.
    bootstrap_manager_enabled: bool = Field(
        default=False,
        description="Enable bootstrapping a manager user on startup",
        alias="BOOTSTRAP_MANAGER_ENABLED",
    )

    bootstrap_manager_tenant_code: str = Field(
        default="",
        description="Tenant code for the bootstrap manager user (optional)",
        alias="BOOTSTRAP_MANAGER_TENANT_CODE",
    )

    bootstrap_manager_username: str = Field(
        default="",
        description="Username for the bootstrap manager user",
        alias="BOOTSTRAP_MANAGER_USERNAME",
    )

    bootstrap_manager_password: str = Field(
        default="",
        description="Password for the bootstrap manager user",
        alias="BOOTSTRAP_MANAGER_PASSWORD",
    )

    bootstrap_manager_must_change_password: bool = Field(
        default=False,
        description="Force password change for the bootstrap manager user after first login",
        alias="BOOTSTRAP_MANAGER_MUST_CHANGE_PASSWORD",
    )

    @property
    def admin_api_keys(self) -> set[str]:
        keys = [
            k.strip() for k in (self.admin_api_keys_str or "").split(",") if k.strip()
        ]
        return set(keys)

    @property
    def auth_protect_prefixes(self) -> list[str]:
        prefixes = [
            p.strip()
            for p in (self.auth_protect_prefixes_str or "").split(",")
            if p.strip()
        ]
        return prefixes or ["/api"]

    @property
    def auth_exempt_paths(self) -> list[str]:
        paths = [
            p.strip()
            for p in (self.auth_exempt_paths_str or "").split(",")
            if p.strip()
        ]
        # Default keeps health/docs available to ease local operations.
        return paths or ["/healthz", "/docs", "/redoc", "/openapi.json"]

    # Audit events (DB) - optional persistence for important operations.
    # Keep disabled by default; enable explicitly when you want long-term querying/reporting.
    audit_events_enabled: bool = Field(
        default=False,
        description="Enable DB audit_events persistence",
        alias="AUDIT_EVENTS_ENABLED",
    )
    audit_events_methods_str: str = Field(
        default="POST,PUT,PATCH,DELETE",
        description="Comma-separated HTTP methods to persist as audit events",
        alias="AUDIT_EVENTS_METHODS",
    )

    @property
    def audit_events_methods(self) -> set[str]:
        methods = [
            m.strip().upper()
            for m in (self.audit_events_methods_str or "").split(",")
            if m.strip()
        ]
        return set(methods) or {"POST", "PUT", "PATCH", "DELETE"}

    # Remote monitoring (LogCollectClient)
    monitor_server_url: str = Field(
        default="",
        description="Remote monitor server URL, e.g. http://192.168.178.151:8000. Empty = disabled.",
        alias="MONITOR_SERVER_URL",
    )
    monitor_source: str = Field(
        default="form-analysis-server",
        description="Source label sent with every heartbeat / log to the monitor.",
        alias="MONITOR_SOURCE",
    )
    monitor_heartbeat_interval: int = Field(
        default=60,
        ge=10,
        description="Heartbeat interval in seconds.",
        alias="MONITOR_HEARTBEAT_INTERVAL",
    )
    monitor_log_min_level: str = Field(
        default="WARNING",
        description="Minimum structlog level to forward to the monitor (WARNING | ERROR | CRITICAL).",
        alias="MONITOR_LOG_MIN_LEVEL",
    )

    # Generic schema feature flag (Phase 1 dual-write)
    use_generic_schema: bool = Field(
        default=False,
        description="Enable generic schema tables (stations/generic_records). False = legacy P1/P2/P3 only.",
        alias="USE_GENERIC_SCHEMA",
    )

    # Database connection pool settings
    database_echo: bool = Field(
        default=False, description="Enable SQLAlchemy SQL logging"
    )
    database_pool_size: int = Field(
        default=5, ge=1, description="Database connection pool size"
    )
    database_pool_recycle: int = Field(
        default=3600, ge=300, description="Database pool recycle time in seconds"
    )
    db_pool_size: int = Field(
        default=5, ge=1, description="Database connection pool size"
    )
    db_max_overflow: int = Field(
        default=10, ge=0, description="Database max overflow connections"
    )
    db_pool_timeout: int = Field(
        default=30, ge=1, description="Database pool timeout seconds"
    )

    # Performance settings
    request_timeout: int = Field(
        default=30, ge=1, description="Request timeout in seconds"
    )
    health_check_interval: int = Field(
        default=30, ge=5, description="Health check interval"
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse CORS origins from the string configuration."""
        if not self.cors_origins_str.strip():
            return ["http://localhost:5173", "http://localhost:3000"]
        return [
            origin.strip()
            for origin in self.cors_origins_str.split(",")
            if origin.strip()
        ]

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v: Any) -> list[str]:
        """Parse allowed extensions from string or list."""
        if isinstance(v, str):
            return [ext.strip().lower() for ext in v.split(",") if ext.strip()]
        return v

    @field_validator("upload_temp_dir")
    @classmethod
    def ensure_upload_dir_exists(cls, v: str) -> str:
        """Ensure upload directory exists, owned by the non-root user when run via sudo."""
        upload_path = Path(v)
        upload_path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt" and os.getuid() == 0:
            import pwd
            sudo_user = os.environ.get("SUDO_USER", "")
            if sudo_user:
                try:
                    pw = pwd.getpwnam(sudo_user)
                    os.chown(upload_path, pw.pw_uid, pw.pw_gid)
                except (KeyError, OSError):
                    pass
        return v

    @property
    def max_upload_size_bytes(self) -> int:
        """Get maximum upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return (
            self.debug
            or self.reload
            or os.getenv("DEV_MODE", "false").lower() == "true"
        )

    @model_validator(mode="after")
    def validate_security_defaults(self) -> "Settings":
        env = (self.environment or "").strip().lower()
        auth_mode = (self.auth_mode or "").strip().lower()
        if env == "production" and auth_mode == "off" and not self.allow_auth_off:
            raise ValueError(
                "AUTH_MODE=off is not allowed in production unless "
                "ALLOW_AUTH_OFF=true is explicitly set"
            )

        insecure_secret_keys = {
            "qI5s1RT9GCr8wlqnfh1XxOZBO_47lSqedali3vHGOVk",
            "change-this-in-production-must-be-32-chars-minimum",
            "your_secret_key_here_minimum_32_characters_required",
            "demo-secret-key-at-least-32-characters",
            "dev-secret-key-at-least-32-characters-long",
            "development-secret-key-32-chars-min",
            "test-secret-key-change-in-production",
        }
        if env == "production" and self.secret_key in insecure_secret_keys:
            raise ValueError("Production SECRET_KEY must be rotated from example values")

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses lru_cache to ensure settings are loaded only once
    and cached for subsequent calls.
    """
    return Settings()
