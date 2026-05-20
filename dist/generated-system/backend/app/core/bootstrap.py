from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.core.password import hash_password
from app.models.core.tenant import Tenant
from app.models.core.tenant_user import TenantUser


@dataclass(frozen=True)
class BootstrapManagerResult:
    attempted: bool
    created: bool
    reason: str | None = None
    tenant_code: str | None = None
    username: str | None = None


async def bootstrap_manager_user_if_configured(
    *, async_session_factory, settings
) -> BootstrapManagerResult:
    """Best-effort bootstrap for a tenant manager user.

    This is meant for first-time deployments and local/dev environments.
    It never raises on normal failures (missing config, missing tenant, etc)
    and should not block app startup.
    """

    enabled = bool(getattr(settings, "bootstrap_manager_enabled", False))
    if not enabled:
        return BootstrapManagerResult(attempted=False, created=False, reason="disabled")

    username = (getattr(settings, "bootstrap_manager_username", "") or "").strip()
    password = (getattr(settings, "bootstrap_manager_password", "") or "").strip()
    tenant_code = (
        getattr(settings, "bootstrap_manager_tenant_code", "") or ""
    ).strip() or None
    must_change_password = bool(
        getattr(settings, "bootstrap_manager_must_change_password", False)
    )

    if not username or not password:
        return BootstrapManagerResult(
            attempted=True,
            created=False,
            reason="missing_username_or_password",
            tenant_code=tenant_code,
            username=username or None,
        )

    if len(password) < 8:
        return BootstrapManagerResult(
            attempted=True,
            created=False,
            reason="password_too_short",
            tenant_code=tenant_code,
            username=username,
        )

    if async_session_factory is None:
        return BootstrapManagerResult(
            attempted=True,
            created=False,
            reason="db_not_initialized",
            tenant_code=tenant_code,
            username=username,
        )

    async with async_session_factory() as db:
        try:
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
                    return BootstrapManagerResult(
                        attempted=True,
                        created=False,
                        reason="unknown_tenant_code",
                        tenant_code=tenant_code,
                        username=username,
                    )
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
                        return BootstrapManagerResult(
                            attempted=True,
                            created=False,
                            reason="tenant_ambiguous",
                            tenant_code=None,
                            username=username,
                        )

            if tenant is None:
                return BootstrapManagerResult(
                    attempted=True,
                    created=False,
                    reason="tenant_not_found",
                    tenant_code=tenant_code,
                    username=username,
                )

            existing = (
                await db.execute(
                    select(TenantUser).where(
                        TenantUser.tenant_id == tenant.id,
                        TenantUser.username == username,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return BootstrapManagerResult(
                    attempted=True,
                    created=False,
                    reason="already_exists",
                    tenant_code=str(getattr(tenant, "code", "")) or None,
                    username=username,
                )

            user = TenantUser(
                tenant_id=tenant.id,
                username=username,
                password_hash=hash_password(password),
                role="manager",
                is_active=True,
                must_change_password=must_change_password,
            )

            db.add(user)
            await db.commit()

            return BootstrapManagerResult(
                attempted=True,
                created=True,
                reason=None,
                tenant_code=str(getattr(tenant, "code", "")) or None,
                username=username,
            )
        except Exception as e:
            try:
                await db.rollback()
            except Exception:
                pass
            return BootstrapManagerResult(
                attempted=True,
                created=False,
                reason=f"error:{type(e).__name__}",
                tenant_code=tenant_code,
                username=username,
            )
