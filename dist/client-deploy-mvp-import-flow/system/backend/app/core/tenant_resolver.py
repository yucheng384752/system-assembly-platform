from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core.tenant import Tenant


async def resolve_tenant_or_raise(
    *, db: AsyncSession, x_tenant_id: str | None
) -> Tenant:
    """Resolve current tenant from header or DB defaults.

    Behavior matches the API dependency in `app.api.deps.get_current_tenant`:
    - If `x_tenant_id` is provided: validates UUID, loads tenant, 404 if missing.
    - If not provided:
      - 404 if no tenants exist.
      - returns the only tenant if exactly one exists.
      - returns the unique default tenant if multiple exist and exactly one has `is_default=True`.
            - otherwise 400 to require explicit header.
    """

    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid X-Tenant-Id format",
            ) from exc

        result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
            )
        return tenant

    count_result = await db.execute(select(func.count(Tenant.id)))
    total_count = count_result.scalar() or 0

    if total_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenants exist. Create one via /api/tenants before calling tenant-scoped APIs.",
        )

    if total_count == 1:
        result = await db.execute(select(Tenant))
        return result.scalar_one()

    result = await db.execute(select(Tenant).where(Tenant.is_default == True))
    default_tenants = result.scalars().all()
    if len(default_tenants) == 1:
        return default_tenants[0]

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="X-Tenant-Id header is required (Multiple tenants exist and no unique default)",
    )


async def resolve_tenant_or_none(
    *, db: AsyncSession, x_tenant_id: str | None
) -> Tenant | None:
    """Best-effort tenant resolution.

    This is intentionally non-raising and is used for optional/background work
    (e.g. analytics sync) where we prefer to "skip" rather than fail the request.

    Rules:
    - If `x_tenant_id` is provided but not a valid UUID -> None
    - If `x_tenant_id` is provided but tenant not found -> None
    - If not provided:
      - returns the only tenant if exactly one exists
      - returns the unique default tenant if multiple exist and exactly one has `is_default=True`
      - otherwise None
    """

    if x_tenant_id:
        try:
            tenant_uuid = UUID(x_tenant_id)
        except ValueError:
            return None

        result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        return result.scalar_one_or_none()

    count_result = await db.execute(select(func.count(Tenant.id)))
    total_count = count_result.scalar() or 0

    if total_count == 1:
        result = await db.execute(select(Tenant))
        return result.scalar_one()

    if total_count > 1:
        result = await db.execute(select(Tenant).where(Tenant.is_default == True))
        default_tenants = result.scalars().all()
        if len(default_tenants) == 1:
            return default_tenants[0]

    return None
