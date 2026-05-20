"""
Form Analysis Backend API

A FastAPI-based service for file upload, validation, and data import operations.
Supports CSV and Excel file formats with comprehensive validation rules.

Main application entry point.
"""

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

# 添加專案根目錄到 Python 路徑，以便直接執行時能找到模組
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import ProgrammingError
from starlette.middleware.gzip import GZipMiddleware

from app.api import constants as routes_constants
from app.api import (
    routes_analytics,
    routes_audit_events,
    routes_auth,
    routes_edit,
    routes_export,
    routes_health,
    routes_import,
    routes_import_v2,
    routes_logs,
    routes_query_v2,
    routes_tenants,
    routes_upload,
    routes_ut,
    routes_validate,
)
from app.api import routes_stations, traceability as routes_traceability
from app.api.deps import get_current_tenant
from app.core.auth import hash_api_key
from app.core.config import get_settings
from app.core.database import Base, init_db
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware, add_process_time_header

# Import all models to ensure they're registered with Base
from app.models import (
    AuditEvent,
)
from app.models.core.tenant_api_key import TenantApiKey
from app.models.core.tenant_user import TenantUser

# Initialize application settings
settings = get_settings()

# Setup structured logging
setup_logging(settings.log_level, settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Database initialization
    - Connection pool setup
    - Resource cleanup
    """
    # Startup - 驗證PostgreSQL或SQLite配置
    if not settings.database_url.startswith(
        "postgresql"
    ) and not settings.database_url.startswith("sqlite"):
        raise ValueError(
            f" 系統只支援PostgreSQL或SQLite資料庫！當前配置: {settings.database_url[:30]}..."
        )

    # Initialize database connection
    await init_db()

    # Import engine after initialization
    from app.core.database import engine

    # Create all tables
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
            print(" Database tables created/verified")
        except ProgrammingError as e:
            # 忽略 "type ... already exists" 錯誤
            # 這是因為 Alembic 可能已經創建了該類型，而 SQLAlchemy create_all 又嘗試創建
            if "already exists" in str(e):
                print(
                    f" Note: Database objects already exist (safe to ignore): {str(e).splitlines()[0]}"
                )
            else:
                raise e

    # Seed minimal registry data (required by Import V2) + ensure at least one tenant exists.
    # Important: do NOT let failures in registry seeding prevent tenant creation.
    try:
        from app.core.database import async_session_factory

        if async_session_factory:
            # 1) Table registry
            try:
                from app.models.core.schema_registry import TableRegistry

                async with async_session_factory() as db:
                    existing = set(
                        (await db.execute(select(TableRegistry.table_code)))
                        .scalars()
                        .all()
                    )
                    for code in ("P1", "P2", "P3"):
                        if code not in existing:
                            db.add(TableRegistry(table_code=code, display_name=code))
                    await db.commit()
            except Exception as e:
                # Do not block startup if seeding fails; import routes will still surface the error.
                print(f" Warning: failed to seed table_registry: {e}")

            # 2) Default tenant
            try:
                from app.models.core.tenant import Tenant

                async with async_session_factory() as db:
                    tenant_count = (
                        await db.execute(select(func.count(Tenant.id)))
                    ).scalar() or 0
                    if tenant_count == 0:
                        db.add(
                            Tenant(
                                name="Default",
                                code="default",
                                is_default=True,
                                is_active=True,
                            )
                        )
                        await db.commit()
            except Exception as e:
                print(f" Warning: failed to seed default tenant: {e}")

            # 2.5) Normalize legacy roles (admin -> manager)
            try:
                async with async_session_factory() as db:
                    result = await db.execute(
                        update(TenantUser)
                        .where(TenantUser.role == "admin")
                        .values(role="manager")
                    )
                    await db.commit()
                    if result.rowcount:
                        print(
                            f" Normalized tenant roles: admin -> manager ({result.rowcount})"
                        )
            except Exception as e:
                print(f" Warning: failed to normalize tenant roles: {e}")

            # 2.6) Seed generic station definitions (Phase 1 generalization)
            if settings.use_generic_schema:
                try:
                    from app.core.seed_stations import seed_stations

                    await seed_stations(async_session_factory)
                    print(" Generic station definitions seeded")
                except Exception as e:
                    print(f" Warning: failed to seed stations: {e}")

            # 3) Optional: bootstrap a manager user (for first-time setup)
            try:
                from app.core.bootstrap import bootstrap_manager_user_if_configured

                res = await bootstrap_manager_user_if_configured(
                    async_session_factory=async_session_factory,
                    settings=settings,
                )
                if res.attempted:
                    if res.created:
                        print(
                            f" Bootstrap manager user created: tenant={res.tenant_code} username={res.username}"
                        )
                    else:
                        print(
                            f" Bootstrap manager user skipped: reason={res.reason} tenant={res.tenant_code} username={res.username}"
                        )
            except Exception as e:
                print(f" Warning: failed to bootstrap manager user: {e}")
    except Exception as e:
        print(f" Warning: failed to run startup seed: {e}")

    print(f" Form Analysis API starting on {settings.api_host}:{settings.api_port}")
    print(
        f" Database: PostgreSQL - {settings.database_url.split('@')[-1]}"
    )  # Hide credentials
    print(f" Upload limit: {settings.max_upload_size_mb}MB")
    print(f" CORS origins: {settings.cors_origins}")
    print(" Database Type: PostgreSQL Only (固定使用PostgreSQL)")

    yield

    # Shutdown
    print(" Form Analysis API shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Form Analysis API",
    description="""
    ## File Upload Validation System
    
    A comprehensive API for uploading, validating, and importing CSV/Excel files.
    
    ### Key Features:
    - **File Upload**: Support for CSV (UTF-8) and Excel (.xlsx) formats
    - **Real-time Validation**: Immediate format and content validation
    - **Data Preview**: Preview of importable data with error highlighting  
    - **Batch Import**: Transaction-safe bulk data import
    - **Error Export**: Download error data as CSV for correction
    - **Audit Tracking**: Complete operation tracking with process_id
    
    ### Supported File Formats:
    - CSV files (UTF-8 encoding, with or without BOM)
    - Excel files (.xlsx format only)
    - Maximum file size: 10MB
    
    ### Validation Rules:
    - **lot_no**: 7digits_2digits format (e.g., 1234567_01)
    - **product_name**: 1-100 characters, non-empty
    - **quantity**: Non-negative integer
    - **production_date**: YYYY-MM-DD format
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time", "X-Request-ID"],
)

# Gzip compression middleware (支援多 server 並發呼叫)
# 自動壓縮 ≥1KB 的回應，對於大資料量查詢（200+ 筆）壓縮率可達 70-80%
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Custom middleware for request logging and timing
app.add_middleware(RequestLoggingMiddleware)
app.middleware("http")(add_process_time_header)


@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    """Optional lightweight API-key auth.

    Enable with env: AUTH_MODE=api_key
    Behavior:
    - Protects prefixes from settings.auth_protect_prefixes (default: /api)
    - Requires header settings.auth_api_key_header (default: X-API-Key)
    - Resolves key -> tenant_id and binds it to request.state.auth_tenant_id
    """
    mode = (getattr(settings, "auth_mode", "off") or "off").strip().lower()
    if mode != "api_key":
        return await call_next(request)

    path = request.url.path
    prefixes = getattr(settings, "auth_protect_prefixes", ["/api"])
    if not any(path.startswith(p) for p in prefixes):
        return await call_next(request)

    exempt_paths = getattr(
        settings, "auth_exempt_paths", ["/healthz", "/docs", "/redoc", "/openapi.json"]
    )
    if any(path.startswith(p) for p in exempt_paths):
        return await call_next(request)

    # Admin key (privileged operations like creating tenants).
    # If valid, mark request as admin.
    # - For bootstrap endpoints (e.g. POST /api/tenants), admin key can be used without a tenant API key.
    # - If an X-API-Key is also provided, still validate it so audit/events keep actor info.
    admin_header_name = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_provided = request.headers.get(admin_header_name)
    admin_keys = getattr(settings, "admin_api_keys", set())
    is_admin = bool(
        admin_provided
        and isinstance(admin_keys, set)
        and admin_provided.strip() in admin_keys
    )
    if is_admin:
        request.state.is_admin = True
        request.state.admin_key_label = "admin"

    header_name = getattr(settings, "auth_api_key_header", "X-API-Key")
    provided = request.headers.get(header_name)
    if not provided:
        # Allow admin-only bootstrap for tenant creation without a tenant API key.
        bootstrap_prefixes = (
            "/api/tenants",
            "/api/auth/users",
            "/api/auth/admin/tenant-api-keys",
            "/api/auth/whoami",
            "/api/auth/bootstrap-status",
            "/api/auth/bootstrap/manager-status",
        )
        if is_admin and any(path.startswith(p) for p in bootstrap_prefixes):
            return await call_next(request)

        # In development, give a more actionable hint for bootstrap endpoints.
        try:
            is_dev = bool(getattr(settings, "is_development", False))
        except Exception:
            is_dev = False

        if is_dev and any(path.startswith(p) for p in bootstrap_prefixes):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        f"Unauthorized: missing {header_name}. "
                        f"For bootstrap endpoints you may use {admin_header_name} "
                        f"(and ensure ADMIN_API_KEYS is configured on the server)."
                    )
                },
            )

        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    try:
        key_hash = hash_api_key(
            raw_key=provided.strip(), secret_key=settings.secret_key
        )
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    from app.core.database import async_session_factory

    if async_session_factory is None:
        return JSONResponse(
            status_code=500, content={"detail": "Database not initialized"}
        )

    async with async_session_factory() as db:
        result = await db.execute(
            select(TenantApiKey).where(
                TenantApiKey.key_hash == key_hash,
                TenantApiKey.is_active == True,
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        request.state.auth_tenant_id = api_key.tenant_id
        request.state.auth_api_key_id = api_key.id
        request.state.auth_api_key_label = api_key.label

        # Optional: resolve actor user & role for RBAC-style checks.
        request.state.actor_user_id = None
        request.state.actor_role = None
        request.state.must_change_password = False
        try:
            if getattr(api_key, "user_id", None):
                actor = (
                    await db.execute(
                        select(TenantUser).where(
                            TenantUser.id == api_key.user_id,
                            TenantUser.tenant_id == api_key.tenant_id,
                            TenantUser.is_active == True,
                        )
                    )
                ).scalar_one_or_none()
                if actor:
                    request.state.actor_user_id = actor.id
                    request.state.actor_role = actor.role
                    request.state.must_change_password = bool(
                        getattr(actor, "must_change_password", False)
                    )
        except Exception:
            # Best-effort: do not block request if actor resolution fails.
            request.state.actor_user_id = None
            request.state.actor_role = None
            request.state.must_change_password = False

        # Best-effort last_used update (do not block request).
        try:
            api_key.last_used_at = func.now()
            await db.commit()
        except Exception:
            await db.rollback()

    # Enforce forced password change after reset/temporary password.
    # Allow only a minimal set of endpoints until the user changes their password.
    try:
        must_change = bool(
            getattr(getattr(request, "state", None), "must_change_password", False)
        )
        if must_change:
            path = request.url.path
            allowed_prefixes = (
                "/api/auth/me/password",
                "/api/auth/whoami",
                "/api/auth/bootstrap-status",
            )
            if not any(path.startswith(p) for p in allowed_prefixes):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Password change required"},
                )
    except Exception:
        # Best-effort: do not block request due to enforcement logic errors.
        pass

    return await call_next(request)


@app.middleware("http")
async def audit_events_middleware(request: Request, call_next):
    """Optional DB audit events.

    Controlled by env:
    - AUDIT_EVENTS_ENABLED=true

    Notes:
    - Best-effort, non-blocking: audit write failures do not fail the request.
    - Never stores raw API keys or request bodies.
    """
    response = await call_next(request)

    if not getattr(settings, "audit_events_enabled", False):
        return response

    method = (request.method or "").upper()
    if method not in getattr(
        settings, "audit_events_methods", {"POST", "PUT", "PATCH", "DELETE"}
    ):
        return response

    path = request.url.path

    # Avoid auditing clearly non-business endpoints by default.
    exempt_paths = getattr(
        settings, "auth_exempt_paths", ["/healthz", "/docs", "/redoc", "/openapi.json"]
    )
    if any(path.startswith(p) for p in exempt_paths):
        return response

    # If auth is configured to protect only some prefixes, keep audit aligned.
    prefixes = getattr(settings, "auth_protect_prefixes", ["/api"])
    if prefixes and not any(path.startswith(p) for p in prefixes):
        return response

    from app.core.database import async_session_factory

    if async_session_factory is None:
        return response

    tenant_id = getattr(getattr(request, "state", None), "tenant_id", None) or getattr(
        getattr(request, "state", None), "auth_tenant_id", None
    )
    actor_api_key_id = getattr(getattr(request, "state", None), "auth_api_key_id", None)
    actor_api_key_label = getattr(
        getattr(request, "state", None), "auth_api_key_label", None
    )
    request_id = getattr(getattr(request, "state", None), "request_id", None)

    # Keep metadata small and non-sensitive.
    query = dict(request.query_params) if request.query_params else {}
    metadata = {
        "query": query,
    }

    try:
        async with async_session_factory() as db:
            db.add(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_api_key_id=actor_api_key_id,
                    actor_label_snapshot=actor_api_key_label,
                    request_id=str(request_id) if request_id else None,
                    method=method,
                    path=path,
                    status_code=int(response.status_code),
                    client_host=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    action="http.write",
                    metadata_json=metadata,
                )
            )
            await db.commit()
    except Exception:
        # Best-effort: never block user requests due to audit logging.
        pass

    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


# Include API routers
tenant_deps = [Depends(get_current_tenant)]

app.include_router(routes_health.router, prefix="/healthz", tags=["Health Check"])

app.include_router(routes_auth.router, prefix="/api/auth", tags=["Authentication"])
# 檔案上傳路由
app.include_router(
    routes_upload.router,
    prefix="/api",
    tags=["檔案上傳"],
    dependencies=tenant_deps,
)

# 驗證結果查詢路由
app.include_router(
    routes_validate.router,
    prefix="/api",
    tags=["驗證結果查詢"],
    dependencies=tenant_deps,
)

# 資料匯入路由
app.include_router(
    routes_import.router,
    prefix="/api",
    tags=["資料匯入"],
    dependencies=tenant_deps,
)

# V2 Import Routes
app.include_router(
    routes_import_v2.router,
    prefix="/api/v2/import",
    tags=["Import V2"],
    dependencies=tenant_deps,
)

# 資料匯出路由
app.include_router(
    routes_export.router,
    prefix="/api",
    tags=["資料匯出"],
    dependencies=tenant_deps,
)

# 日誌管理路由
app.include_router(
    routes_logs.router,
    prefix="/api/logs",
    tags=["日誌管理"],
    dependencies=tenant_deps,
)

# Tenant Routes
app.include_router(routes_tenants.router, tags=["Tenants"])

# 系統常數查詢路由
app.include_router(
    routes_constants.router,
    tags=["系統常數"],
    dependencies=tenant_deps,
)

# 生產追溯查詢路由
app.include_router(
    routes_traceability.router,
    tags=["生產追溯"],
    dependencies=tenant_deps,
)

# 分析用追溯資料扁平化路由（支援多 server 並發呼叫）
app.include_router(
    routes_analytics.router,
    tags=["Analytics"],
    dependencies=tenant_deps,
)


app.include_router(
    routes_query_v2.router,
    prefix="/api/v2/query",
    tags=["Query V2"],
    dependencies=tenant_deps,
)

app.include_router(
    routes_edit.router,
    prefix="/api/edit",
    tags=["Inline Edit"],
    dependencies=tenant_deps,
)

app.include_router(
    routes_audit_events.router,
    tags=["Audit Events"],
)

# UT API (侑特資料查詢)
app.include_router(
    routes_ut.router,
    tags=["UT Data"],
    dependencies=tenant_deps,
)

# Generic Station API (Phase 2 — gated by USE_GENERIC_SCHEMA)
if settings.use_generic_schema:
    app.include_router(
        routes_stations.router,
        tags=["Stations (Generic)"],
        dependencies=tenant_deps,
    )


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint with basic API information."""
    return {
        "message": "Form Analysis API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/healthz",
    }


if __name__ == "__main__":
    # Run the application directly (for development)
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
        access_log=True,
    )
