from __future__ import annotations

import secrets
import time
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.auth import generate_api_key, hash_api_key
from app.core.config import get_settings
from app.core.password import hash_password, verify_password
from app.models.core.tenant import Tenant
from app.models.core.tenant_api_key import TenantApiKey
from app.models.core.tenant_user import TenantUser
from app.services.audit_events import write_audit_event_best_effort

router = APIRouter()

_ALLOWED_TENANT_ROLES = {"manager", "user"}


class LoginRequest(BaseModel):
    tenant_code: str | None = Field(
        default=None,
        description="Tenant code (場域代碼). If omitted, auto-resolves when exactly one tenant exists.",
    )
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    tenant_id: str
    tenant_code: str
    api_key: str
    api_key_header: str
    must_change_password: bool = False

    model_config = ConfigDict(from_attributes=True)


class CreateUserRequest(BaseModel):
    tenant_code: str | None = Field(default=None, description="Tenant code (場域代碼).")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(
        min_length=8, max_length=200, description="Minimum 8 characters"
    )
    role: str = Field(default="user", min_length=1, max_length=30)

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        role = (value or "").strip() or "user"
        if role not in _ALLOWED_TENANT_ROLES:
            raise ValueError("role must be manager or user")
        return role


class CreateUserResponse(BaseModel):
    id: str
    tenant_id: str
    tenant_code: str
    username: str
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TenantUserResponse(BaseModel):
    id: str
    tenant_id: str
    tenant_code: str | None = None
    username: str
    role: str
    is_active: bool
    must_change_password: bool = False
    created_at: str | None = None
    last_login_at: str | None = None


class UpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    role: str | None = Field(default=None, min_length=1, max_length=30)
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        role = value.strip() or "user"
        if role not in _ALLOWED_TENANT_ROLES:
            raise ValueError("role must be manager or user")
        return role


class RebindUserTenantRequest(BaseModel):
    tenant_id: str | None = Field(default=None, description="Target tenant UUID")
    tenant_code: str | None = Field(default=None, description="Target tenant code")
    revoke_api_keys: bool = Field(
        default=True, description="Revoke existing active API keys for this user"
    )


class IssueTenantApiKeyRequest(BaseModel):
    tenant_id: str | None = Field(default=None, description="Target tenant UUID")
    tenant_code: str | None = Field(default=None, description="Target tenant code")
    label: str | None = Field(
        default=None, description="Key label; default is admin impersonation label"
    )
    revoke_existing_same_label: bool = Field(
        default=True, description="Rotate: revoke existing active keys with same label"
    )


class IssueTenantApiKeyResponse(BaseModel):
    tenant_id: str
    tenant_code: str
    api_key: str
    api_key_header: str
    api_key_label: str

    model_config = ConfigDict(from_attributes=True)


class WhoAmIResponse(BaseModel):
    is_admin: bool
    tenant_id: str | None = None
    actor_user_id: str | None = None
    actor_role: str | None = None
    api_key_label: str | None = None
    must_change_password: bool = False


def _is_admin_key(request: Request) -> bool:
    settings = get_settings()
    admin_header = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_keys = getattr(settings, "admin_api_keys", set())
    provided = request.headers.get(admin_header)
    return bool(provided and provided.strip() in admin_keys)


def _is_tenant_privileged(actor_role: str | None, auth_tenant_id) -> bool:
    # Tenant-scoped privileged roles (day-to-day operations).
    # NOTE: 'admin' is not a tenant role; break-glass admin uses X-Admin-API-Key.
    return bool(auth_tenant_id and actor_role in {"manager"})


def _ensure_manager_not_targeting_admin(
    *,
    is_admin_key: bool,
    actor_role: str | None,
    target_role: str | None,
    action: str,
) -> None:
    """Disallow manager from creating/updating/deleting admin users.

    This is a centralized guard to avoid scattered role checks.
    """
    if is_admin_key or actor_role != "manager":
        return
    if str(target_role or "").strip() == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Manager cannot {action} admin users",
        )


async def _count_other_active_privileged_users(
    db: AsyncSession, tenant_id, exclude_user_id: UUID
) -> int:
    stmt = select(func.count(TenantUser.id)).where(
        TenantUser.tenant_id == tenant_id,
        TenantUser.is_active == True,
        TenantUser.role.in_(["manager"]),
        TenantUser.id != exclude_user_id,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(request: Request):
    state = getattr(request, "state", None)
    return WhoAmIResponse(
        is_admin=bool(getattr(state, "is_admin", False)),
        tenant_id=str(getattr(state, "auth_tenant_id", "")) or None,
        actor_user_id=str(getattr(state, "actor_user_id", "")) or None,
        actor_role=getattr(state, "actor_role", None),
        api_key_label=getattr(state, "auth_api_key_label", None),
        must_change_password=bool(getattr(state, "must_change_password", False)),
    )


class ChangeMyPasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(
        min_length=8, max_length=200, description="Minimum 8 characters"
    )


class ResetUserPasswordRequest(BaseModel):
    # If omitted, server will generate a temporary password.
    new_password: str | None = Field(default=None, min_length=8, max_length=200)


class ResetUserPasswordResponse(BaseModel):
    user_id: str
    username: str
    must_change_password: bool
    temporary_password: str | None = None


_PW_CHANGE_FAIL_WINDOW_SECONDS = 60.0
_PW_CHANGE_FAIL_MAX = 10
_pw_change_failures_by_user: dict[str, list[float]] = {}


def _check_password_change_throttle(*, user_id: str) -> None:
    now = time.monotonic()
    window_start = now - _PW_CHANGE_FAIL_WINDOW_SECONDS
    recent = [
        t for t in _pw_change_failures_by_user.get(user_id, []) if t >= window_start
    ]
    if len(recent) >= _PW_CHANGE_FAIL_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts",
        )
    _pw_change_failures_by_user[user_id] = recent


def _record_password_change_failure(*, user_id: str) -> None:
    now = time.monotonic()
    window_start = now - _PW_CHANGE_FAIL_WINDOW_SECONDS
    recent = [
        t for t in _pw_change_failures_by_user.get(user_id, []) if t >= window_start
    ]
    recent.append(now)
    _pw_change_failures_by_user[user_id] = recent


class BootstrapStatusResponse(BaseModel):
    auth_mode: str
    auth_api_key_header: str
    auth_protect_prefixes: list[str]
    auth_exempt_paths: list[str]
    admin_api_key_header: str
    admin_keys_configured: bool

    bootstrap_manager_enabled: bool = False
    bootstrap_manager_configured: bool = False


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
async def bootstrap_status():
    settings = get_settings()
    admin_keys = getattr(settings, "admin_api_keys", set())

    manager_enabled = bool(getattr(settings, "bootstrap_manager_enabled", False))
    manager_username = (
        getattr(settings, "bootstrap_manager_username", "") or ""
    ).strip()
    manager_password = (
        getattr(settings, "bootstrap_manager_password", "") or ""
    ).strip()
    manager_configured = bool(manager_username and manager_password)

    return BootstrapStatusResponse(
        auth_mode=str(getattr(settings, "auth_mode", "off")),
        auth_api_key_header=str(getattr(settings, "auth_api_key_header", "X-API-Key")),
        auth_protect_prefixes=list(
            getattr(settings, "auth_protect_prefixes", ["/api"])
        ),
        auth_exempt_paths=list(getattr(settings, "auth_exempt_paths", ["/healthz"])),
        admin_api_key_header=str(
            getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
        ),
        admin_keys_configured=bool(isinstance(admin_keys, set) and len(admin_keys) > 0),
        bootstrap_manager_enabled=manager_enabled,
        bootstrap_manager_configured=manager_configured,
    )


class BootstrapManagerStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    tenant_code: str | None = None
    username: str | None = None
    exists: bool
    role: str | None = None


@router.get("/bootstrap/manager-status", response_model=BootstrapManagerStatusResponse)
async def bootstrap_manager_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Inspect bootstrap manager config + existence.

    Requires X-Admin-API-Key.
    """

    if not _is_admin_key(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    settings = get_settings()
    enabled = bool(getattr(settings, "bootstrap_manager_enabled", False))
    username = (
        getattr(settings, "bootstrap_manager_username", "") or ""
    ).strip() or None
    tenant_code = (
        getattr(settings, "bootstrap_manager_tenant_code", "") or ""
    ).strip() or None
    configured = bool(
        username and (getattr(settings, "bootstrap_manager_password", "") or "").strip()
    )

    if not enabled or not configured or not username:
        return BootstrapManagerStatusResponse(
            enabled=enabled,
            configured=configured,
            tenant_code=tenant_code,
            username=username,
            exists=False,
            role=None,
        )

    tenant: Tenant | None = None
    if tenant_code:
        tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.code == tenant_code, Tenant.is_active == True
                )
            )
        ).scalar_one_or_none()
    else:
        tenants = (
            (await db.execute(select(Tenant).where(Tenant.is_active == True)))
            .scalars()
            .all()
        )
        if len(tenants) == 1:
            tenant = tenants[0]
        else:
            tenant = (
                await db.execute(
                    select(Tenant).where(
                        Tenant.is_default == True, Tenant.is_active == True
                    )
                )
            ).scalar_one_or_none()

    if not tenant:
        return BootstrapManagerStatusResponse(
            enabled=enabled,
            configured=configured,
            tenant_code=tenant_code,
            username=username,
            exists=False,
            role=None,
        )

    user = (
        await db.execute(
            select(TenantUser).where(
                TenantUser.tenant_id == tenant.id,
                TenantUser.username == username,
                TenantUser.is_active == True,
            )
        )
    ).scalar_one_or_none()

    return BootstrapManagerStatusResponse(
        enabled=enabled,
        configured=configured,
        tenant_code=str(getattr(tenant, "code", "")) or tenant_code,
        username=username,
        exists=bool(user),
        role=(str(user.role) if user else None),
    )


@router.post(
    "/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED
)
async def create_user(
    request: Request,
    payload: CreateUserRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Create a tenant user.

    Allowed callers:
    - Break-glass bootstrap: valid ADMIN_API_KEYS (X-Admin-API-Key), can target any tenant by tenant_code.
    - Day-to-day: authenticated API key whose linked user has role=manager, can only create users in its own tenant.
    """

    is_admin_key = _is_admin_key(request)

    actor_role = getattr(getattr(request, "state", None), "actor_role", None)
    auth_tenant_id = getattr(getattr(request, "state", None), "auth_tenant_id", None)
    is_tenant_privileged = _is_tenant_privileged(actor_role, auth_tenant_id)

    if not is_admin_key and not is_tenant_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager privileges required",
        )

    # Managers may not mint tenant 'admin' users (legacy safeguard).
    if not is_admin_key and actor_role == "manager":
        requested_role = (payload.role or "").strip() or "user"
        _ensure_manager_not_targeting_admin(
            is_admin_key=is_admin_key,
            actor_role=actor_role,
            target_role=requested_role,
            action="create",
        )

    tenant: Tenant | None = None
    if is_admin_key:
        tenant_code = (payload.tenant_code or "").strip() or None
        if tenant_code:
            tenant = (
                await db.execute(
                    select(Tenant).where(
                        Tenant.code == tenant_code, Tenant.is_active == True
                    )
                )
            ).scalar_one_or_none()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Unknown tenant_code",
                )
        else:
            tenants = (
                (await db.execute(select(Tenant).where(Tenant.is_active == True)))
                .scalars()
                .all()
            )
            if len(tenants) != 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="tenant_code required when multiple tenants exist",
                )
            tenant = tenants[0]
    else:
        # role=manager via API key: tenant is bound by middleware
        tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.id == auth_tenant_id, Tenant.is_active == True
                )
            )
        ).scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown tenant"
            )

    username = payload.username.strip()
    existing = (
        await db.execute(
            select(TenantUser).where(
                TenantUser.tenant_id == tenant.id, TenantUser.username == username
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User already exists"
        )

    user = TenantUser(
        tenant_id=tenant.id,
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role.strip() or "user",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return CreateUserResponse(
        id=str(user.id),
        tenant_id=str(tenant.id),
        tenant_code=str(tenant.code),
        username=user.username,
        role=user.role,
        is_active=bool(user.is_active),
    )


@router.get("/users", response_model=list[TenantUserResponse])
async def list_users(
    request: Request,
    tenant_id: str | None = None,
    tenant_code: str | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List tenant users.

    Allowed callers:
    - Break-glass bootstrap: valid ADMIN_API_KEYS (X-Admin-API-Key), can list across tenants.
    - Day-to-day: authenticated API key whose linked user has role=manager, lists only its own tenant.
    """

    is_admin_key = _is_admin_key(request)
    actor_role = getattr(getattr(request, "state", None), "actor_role", None)
    auth_tenant_id = getattr(getattr(request, "state", None), "auth_tenant_id", None)
    is_tenant_privileged = _is_tenant_privileged(actor_role, auth_tenant_id)

    if not is_admin_key and not is_tenant_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager privileges required",
        )

    stmt = select(TenantUser, Tenant.code).join(
        Tenant, Tenant.id == TenantUser.tenant_id
    )

    if is_tenant_privileged:
        stmt = stmt.where(TenantUser.tenant_id == auth_tenant_id)
    else:
        # Admin key: optional filters.
        if tenant_id and tenant_id.strip():
            try:
                tenant_uuid = UUID(tenant_id.strip())
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id"
                )
            stmt = stmt.where(TenantUser.tenant_id == tenant_uuid)
        if tenant_code and tenant_code.strip():
            stmt = stmt.where(Tenant.code == tenant_code.strip())

    if not include_inactive:
        stmt = stmt.where(TenantUser.is_active == True)

    stmt = stmt.order_by(Tenant.code.asc(), TenantUser.username.asc())
    rows = (await db.execute(stmt)).all()

    out: list[TenantUserResponse] = []
    for user, t_code in rows:
        created_at = None
        last_login_at = None
        try:
            created_at = (
                user.created_at.isoformat()
                if getattr(user, "created_at", None)
                else None
            )
        except Exception:
            created_at = None
        try:
            last_login_at = (
                user.last_login_at.isoformat()
                if getattr(user, "last_login_at", None)
                else None
            )
        except Exception:
            last_login_at = None

        out.append(
            TenantUserResponse(
                id=str(user.id),
                tenant_id=str(user.tenant_id),
                tenant_code=str(t_code) if t_code is not None else None,
                username=str(user.username),
                role=str(user.role),
                is_active=bool(user.is_active),
                must_change_password=bool(getattr(user, "must_change_password", False)),
                created_at=created_at,
                last_login_at=last_login_at,
            )
        )

    return out


@router.patch("/users/{user_id}", response_model=TenantUserResponse)
async def update_user(
    user_id: UUID,
    request: Request,
    payload: UpdateUserRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant user (username/role/is_active).

    Password changes are intentionally not implemented yet.
    """

    is_admin_key = _is_admin_key(request)
    actor_role = getattr(getattr(request, "state", None), "actor_role", None)
    auth_tenant_id = getattr(getattr(request, "state", None), "auth_tenant_id", None)
    is_tenant_privileged = _is_tenant_privileged(actor_role, auth_tenant_id)

    if not is_admin_key and not is_tenant_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager privileges required",
        )

    row = (
        await db.execute(
            select(TenantUser, Tenant.code)
            .join(Tenant, Tenant.id == TenantUser.tenant_id)
            .where(TenantUser.id == user_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user, t_code = row

    orig_role = str(getattr(user, "role", ""))
    orig_is_active = bool(getattr(user, "is_active", False))

    if is_tenant_privileged and user.tenant_id != auth_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users in another tenant",
        )

    # Managers may not manage tenant admins, and may not assign role=admin (legacy safeguard).
    if not is_admin_key and actor_role == "manager":
        _ensure_manager_not_targeting_admin(
            is_admin_key=is_admin_key,
            actor_role=actor_role,
            target_role=getattr(user, "role", None),
            action="manage",
        )
        if payload.role is not None:
            next_role = payload.role.strip() or "user"
            _ensure_manager_not_targeting_admin(
                is_admin_key=is_admin_key,
                actor_role=actor_role,
                target_role=next_role,
                action="assign",
            )

    did_change = False

    if payload.username is not None:
        new_username = payload.username.strip()
        if not new_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="username must not be empty",
            )

        if new_username != user.username:
            existing = (
                await db.execute(
                    select(TenantUser).where(
                        TenantUser.tenant_id == user.tenant_id,
                        TenantUser.username == new_username,
                        TenantUser.id != user.id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="username already exists",
                )
            user.username = new_username
            did_change = True

    if payload.role is not None:
        new_role = payload.role.strip() or "user"
        if new_role != user.role:
            user.role = new_role
            did_change = True

    if payload.is_active is not None:
        if bool(payload.is_active) != bool(user.is_active):
            user.is_active = bool(payload.is_active)
            did_change = True

    # Prevent lockout: do not allow removing the last active privileged user
    # via tenant-scoped calls. Break-glass admin key can override.
    if not is_admin_key:
        before_privileged = bool(orig_is_active) and orig_role.strip() in {"manager"}
        after_privileged = bool(user.is_active) and str(user.role).strip() in {
            "manager"
        }
        if before_privileged and not after_privileged:
            other_count = await _count_other_active_privileged_users(
                db, user.tenant_id, user.id
            )
            if other_count <= 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last manager user in this tenant",
                )

    if not did_change:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided"
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update violates uniqueness constraints",
        )

    created_at = None
    last_login_at = None
    try:
        created_at = (
            user.created_at.isoformat() if getattr(user, "created_at", None) else None
        )
    except Exception:
        created_at = None
    try:
        last_login_at = (
            user.last_login_at.isoformat()
            if getattr(user, "last_login_at", None)
            else None
        )
    except Exception:
        last_login_at = None

    return TenantUserResponse(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        tenant_code=str(t_code) if t_code is not None else None,
        username=str(user.username),
        role=str(user.role),
        is_active=bool(user.is_active),
        must_change_password=bool(getattr(user, "must_change_password", False)),
        created_at=created_at,
        last_login_at=last_login_at,
    )


@router.delete("/users/{user_id}", response_model=TenantUserResponse)
async def delete_user(
    user_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete tenant user (safe delete).

    For safety, this performs a soft-delete by setting is_active=False.
    """

    is_admin_key = _is_admin_key(request)
    actor_role = getattr(getattr(request, "state", None), "actor_role", None)
    auth_tenant_id = getattr(getattr(request, "state", None), "auth_tenant_id", None)
    is_tenant_privileged = _is_tenant_privileged(actor_role, auth_tenant_id)

    if not is_admin_key and not is_tenant_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager privileges required",
        )

    row = (
        await db.execute(
            select(TenantUser, Tenant.code)
            .join(Tenant, Tenant.id == TenantUser.tenant_id)
            .where(TenantUser.id == user_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user, t_code = row

    if is_tenant_privileged and user.tenant_id != auth_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users in another tenant",
        )

    # Managers may not manage tenant admins (legacy safeguard).
    if not is_admin_key and actor_role == "manager":
        _ensure_manager_not_targeting_admin(
            is_admin_key=is_admin_key,
            actor_role=actor_role,
            target_role=getattr(user, "role", None),
            action="manage",
        )

    # Prevent lockout: do not allow deactivating the last active privileged user.
    if not is_admin_key:
        before_privileged = bool(user.is_active) and str(user.role).strip() in {
            "manager"
        }
        if before_privileged:
            other_count = await _count_other_active_privileged_users(
                db, user.tenant_id, user.id
            )
            if other_count <= 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last manager user in this tenant",
                )

    if bool(user.is_active):
        user.is_active = False
        await db.commit()
    else:
        await db.commit()

    created_at = None
    last_login_at = None
    try:
        created_at = (
            user.created_at.isoformat() if getattr(user, "created_at", None) else None
        )
    except Exception:
        created_at = None
    try:
        last_login_at = (
            user.last_login_at.isoformat()
            if getattr(user, "last_login_at", None)
            else None
        )
    except Exception:
        last_login_at = None

    return TenantUserResponse(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        tenant_code=str(t_code) if t_code is not None else None,
        username=str(user.username),
        role=str(user.role),
        is_active=bool(user.is_active),
        must_change_password=bool(getattr(user, "must_change_password", False)),
        created_at=created_at,
        last_login_at=last_login_at,
    )


@router.patch("/users/{user_id}/tenant", response_model=TenantUserResponse)
async def rebind_user_tenant(
    user_id: UUID,
    request: Request,
    payload: RebindUserTenantRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Rebind a user to another tenant.

    Safety:
    - Admin API key only (highest admin).
    - Enforces (tenant_id, username) uniqueness in the target tenant.
    - By default revokes existing active API keys owned by this user.
    """

    if not _is_admin_key(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    tenant_id_raw = (payload.tenant_id or "").strip() or None
    tenant_code_raw = (payload.tenant_code or "").strip() or None
    if not tenant_id_raw and not tenant_code_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id or tenant_code is required",
        )

    target_tenant: Tenant | None = None
    if tenant_id_raw:
        try:
            target_uuid = UUID(tenant_id_raw)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id"
            ) from exc
        target_tenant = (
            await db.execute(select(Tenant).where(Tenant.id == target_uuid))
        ).scalar_one_or_none()
    else:
        target_tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.code == tenant_code_raw,
                    Tenant.is_active == True,
                )
            )
        ).scalar_one_or_none()

    if not target_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target tenant not found"
        )

    row = (
        await db.execute(
            select(TenantUser, Tenant.code)
            .join(Tenant, Tenant.id == TenantUser.tenant_id)
            .where(TenantUser.id == user_id)
        )
    ).first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user, _current_code = row

    if user.tenant_id == target_tenant.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already bound to this tenant",
        )

    conflict = (
        await db.execute(
            select(TenantUser).where(
                TenantUser.tenant_id == target_tenant.id,
                TenantUser.username == user.username,
                TenantUser.id != user.id,
            )
        )
    ).scalar_one_or_none()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Target tenant already has a user with the same username (rename first)",
        )

    user.tenant_id = target_tenant.id

    if bool(payload.revoke_api_keys):
        await db.execute(
            update(TenantApiKey)
            .where(
                TenantApiKey.user_id == user.id,
                TenantApiKey.is_active == True,
            )
            .values(is_active=False, revoked_at=func.now())
        )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rebind violates uniqueness constraints",
        )

    created_at = None
    last_login_at = None
    try:
        created_at = (
            user.created_at.isoformat() if getattr(user, "created_at", None) else None
        )
    except Exception:
        created_at = None
    try:
        last_login_at = (
            user.last_login_at.isoformat()
            if getattr(user, "last_login_at", None)
            else None
        )
    except Exception:
        last_login_at = None

    return TenantUserResponse(
        id=str(user.id),
        tenant_id=str(user.tenant_id),
        tenant_code=str(target_tenant.code),
        username=str(user.username),
        role=str(user.role),
        is_active=bool(user.is_active),
        must_change_password=bool(getattr(user, "must_change_password", False)),
        created_at=created_at,
        last_login_at=last_login_at,
    )


@router.post("/admin/tenant-api-keys", response_model=IssueTenantApiKeyResponse)
async def issue_tenant_api_key(
    request: Request,
    payload: IssueTenantApiKeyRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Issue (or rotate) a tenant API key for admin tenant switching.

    Security:
    - Admin API key only (highest admin).
    - Returns a raw API key token; treat it as a session token.
    """

    if not _is_admin_key(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    settings = get_settings()

    tenant_id_raw = (payload.tenant_id or "").strip() or None
    tenant_code_raw = (payload.tenant_code or "").strip() or None

    tenant: Tenant | None = None
    if tenant_id_raw:
        try:
            tenant_uuid = UUID(tenant_id_raw)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant_id"
            ) from exc
        tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.id == tenant_uuid,
                    Tenant.is_active == True,
                )
            )
        ).scalar_one_or_none()
    elif tenant_code_raw:
        tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.code == tenant_code_raw,
                    Tenant.is_active == True,
                )
            )
        ).scalar_one_or_none()
    else:
        tenants = (
            (await db.execute(select(Tenant).where(Tenant.is_active == True)))
            .scalars()
            .all()
        )
        if len(tenants) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_id or tenant_code required when multiple tenants exist",
            )
        tenant = tenants[0]

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target tenant not found"
        )

    label = (payload.label or "").strip() or f"admin:impersonation:{tenant.code}"

    if bool(payload.revoke_existing_same_label):
        await db.execute(
            update(TenantApiKey)
            .where(
                TenantApiKey.tenant_id == tenant.id,
                TenantApiKey.label == label,
                TenantApiKey.is_active == True,
            )
            .values(is_active=False, revoked_at=func.now())
        )

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key=raw_key, secret_key=settings.secret_key)

    api_key_row = TenantApiKey(
        tenant_id=tenant.id,
        key_hash=key_hash,
        label=label,
        is_active=True,
        user_id=None,
    )
    db.add(api_key_row)
    await db.commit()

    header_name = getattr(settings, "auth_api_key_header", "X-API-Key")
    return IssueTenantApiKeyResponse(
        tenant_id=str(tenant.id),
        tenant_code=str(tenant.code),
        api_key=raw_key,
        api_key_header=header_name,
        api_key_label=label,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Password login to obtain an API key.

    Design:
    - Keeps existing X-API-Key auth for all business APIs.
    - This endpoint is exempted from AUTH_MODE=api_key middleware so users can log in.

    Security notes:
    - Returns raw api_key (token) to client; treat it as a session token.
    - Rotates the per-user key (revokes previous active key with same label).
    """

    tenant_code = (payload.tenant_code or "").strip() or None

    tenant: Tenant | None = None
    if tenant_code:
        tenant = (
            await db.execute(
                select(Tenant).where(
                    Tenant.code == tenant_code, Tenant.is_active == True
                )
            )
        ).scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown area_code"
            )
    else:
        # If tenant_code is omitted, prefer the configured default tenant.
        # This keeps login UX simple for the common "default area" flow.
        tenant = (
            await db.execute(
                select(Tenant)
                .where(Tenant.is_active == True, Tenant.is_default == True)
                .order_by(Tenant.id)
                .limit(1)
            )
        ).scalar_one_or_none()

        if not tenant:
            tenants = (
                (await db.execute(select(Tenant).where(Tenant.is_active == True)))
                .scalars()
                .all()
            )
            if len(tenants) != 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="area_code required when multiple areas exist",
                )
            tenant = tenants[0]

    username = payload.username.strip()
    user = (
        await db.execute(
            select(TenantUser).where(
                TenantUser.tenant_id == tenant.id,
                TenantUser.username == username,
                TenantUser.is_active == True,
            )
        )
    ).scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    settings = get_settings()

    # Rotate per-user API key (one active key per username per tenant).
    label = f"login:{username}"
    await db.execute(
        update(TenantApiKey)
        .where(
            TenantApiKey.tenant_id == tenant.id,
            TenantApiKey.label == label,
            TenantApiKey.is_active == True,
        )
        .values(is_active=False, revoked_at=func.now())
    )

    raw_key = generate_api_key()
    key_hash = hash_api_key(raw_key=raw_key, secret_key=settings.secret_key)

    api_key_row = TenantApiKey(
        tenant_id=tenant.id,
        key_hash=key_hash,
        label=label,
        is_active=True,
        user_id=user.id,
    )
    db.add(api_key_row)

    # Best-effort last_login tracking.
    try:
        user.last_login_at = func.now()
    except Exception:
        pass

    await db.commit()

    header_name = getattr(settings, "auth_api_key_header", "X-API-Key")
    return LoginResponse(
        tenant_id=str(tenant.id),
        tenant_code=str(tenant.code),
        api_key=raw_key,
        api_key_header=header_name,
        must_change_password=bool(getattr(user, "must_change_password", False)),
    )


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_my_password(
    request: Request,
    payload: ChangeMyPasswordRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """User self-service password change.

    Requirements:
    - Must be authenticated with an API key that is linked to a tenant_user.
    - Must provide the old password.
    - Clears must_change_password flag.
    """

    state = getattr(request, "state", None)
    auth_tenant_id = getattr(state, "auth_tenant_id", None)
    actor_user_id = getattr(state, "actor_user_id", None)
    auth_api_key_id = getattr(state, "auth_api_key_id", None)

    if not auth_tenant_id or not actor_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User authentication required"
        )

    user = (
        await db.execute(
            select(TenantUser).where(
                TenantUser.id == actor_user_id,
                TenantUser.tenant_id == auth_tenant_id,
                TenantUser.is_active == True,
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    actor_user_id_str = str(user.id)
    _check_password_change_throttle(user_id=actor_user_id_str)

    if payload.old_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different",
        )

    if not verify_password(payload.old_password, user.password_hash):
        _record_password_change_failure(user_id=actor_user_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid old password"
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False

    # Revoke other active keys for this user (keep the current key if possible).
    stmt = (
        update(TenantApiKey)
        .where(
            TenantApiKey.user_id == user.id,
            TenantApiKey.is_active == True,
        )
        .values(is_active=False, revoked_at=func.now())
    )
    if auth_api_key_id:
        stmt = stmt.where(TenantApiKey.id != auth_api_key_id)
    await db.execute(stmt)

    await db.commit()

    await write_audit_event_best_effort(
        tenant_id=user.tenant_id,
        actor_api_key_id=getattr(state, "auth_api_key_id", None),
        actor_label_snapshot=getattr(state, "auth_api_key_label", None),
        request_id=getattr(state, "request_id", None),
        method=request.method,
        path=request.url.path,
        status_code=204,
        action="auth.password.change",
        metadata={"target_user_id": str(user.id)},
        client_host=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return None


@router.post(
    "/users/{user_id}/password-reset", response_model=ResetUserPasswordResponse
)
async def reset_user_password(
    user_id: UUID,
    request: Request,
    payload: ResetUserPasswordRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Manager reset another user's password.

    Behavior:
    - Requires tenant-scoped manager API key OR break-glass admin API key.
    - Revokes all active API keys for the target user.
    - Sets must_change_password=True.
    - Returns a generated temporary password if new_password is omitted.
    """

    state = getattr(request, "state", None)
    is_admin_key = _is_admin_key(request)
    actor_role = getattr(state, "actor_role", None)
    auth_tenant_id = getattr(state, "auth_tenant_id", None)
    is_tenant_privileged = _is_tenant_privileged(actor_role, auth_tenant_id)

    if not is_admin_key and not is_tenant_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager privileges required",
        )

    if not is_admin_key and not getattr(state, "actor_user_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User authentication required"
        )

    target = (
        await db.execute(
            select(TenantUser).where(
                TenantUser.id == user_id,
                TenantUser.is_active == True,
            )
        )
    ).scalar_one_or_none()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Tenant-scoped callers may only manage their own tenant.
    if is_tenant_privileged and target.tenant_id != auth_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage users in another tenant",
        )

    # Prevent bypass: self reset should use /me/password.
    if getattr(state, "actor_user_id", None) and str(state.actor_user_id) == str(
        target.id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Use /api/auth/me/password"
        )

    # Managers may not manage tenant admins (legacy safeguard).
    if not is_admin_key and actor_role == "manager":
        _ensure_manager_not_targeting_admin(
            is_admin_key=is_admin_key,
            actor_role=actor_role,
            target_role=getattr(target, "role", None),
            action="manage",
        )

    new_password = (payload.new_password or "").strip() or None
    generated = False
    if not new_password:
        # Ensure >= 8 chars, URL-safe.
        new_password = secrets.token_urlsafe(12)
        generated = True

    target.password_hash = hash_password(new_password)
    target.must_change_password = True

    # Force logout: revoke all active keys for the target user.
    await db.execute(
        update(TenantApiKey)
        .where(TenantApiKey.user_id == target.id, TenantApiKey.is_active == True)
        .values(is_active=False, revoked_at=func.now())
    )

    await db.commit()

    await write_audit_event_best_effort(
        tenant_id=target.tenant_id,
        actor_api_key_id=getattr(state, "auth_api_key_id", None),
        actor_label_snapshot=getattr(state, "auth_api_key_label", None),
        request_id=getattr(state, "request_id", None),
        method=request.method,
        path=request.url.path,
        status_code=200,
        action="auth.password.reset",
        metadata={"target_user_id": str(target.id), "generated": generated},
        client_host=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return ResetUserPasswordResponse(
        user_id=str(target.id),
        username=str(target.username),
        must_change_password=True,
        temporary_password=new_password if generated else None,
    )
