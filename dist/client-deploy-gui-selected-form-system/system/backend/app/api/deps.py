from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tenant_resolver import resolve_tenant_or_raise
from app.models.core.tenant import Tenant


async def get_current_tenant(
    request: Request = None,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Resolve current tenant from Header or Default.

    Logic:
    1. If X-Tenant-Id header is present, use it to find tenant.
    2. If header is missing:
       - If only 1 tenant exists in DB, use it.
       - If multiple tenants exist, check for is_default=True.
       - If exactly one default tenant exists, use it.
         - Otherwise, raise 400 error requiring explicit tenant ID.
    """
    if request is not None:
        state = getattr(request, "state", None)
        auth_tenant_id = getattr(state, "auth_tenant_id", None)
        is_admin = bool(getattr(state, "is_admin", False))
        if auth_tenant_id and not is_admin:
            # When auth is enabled, tenant is bound to the API key.
            tenant = await resolve_tenant_or_raise(
                db=db, x_tenant_id=str(auth_tenant_id)
            )
            request.state.tenant_id = tenant.id
            request.state.tenant_code = tenant.code
            return tenant

        if auth_tenant_id and is_admin:
            # Highest admin: allow explicit override via X-Tenant-Id.
            # If override header is not provided, fall back to the bound tenant.
            effective_tenant_id = x_tenant_id or str(auth_tenant_id)
            tenant = await resolve_tenant_or_raise(
                db=db, x_tenant_id=str(effective_tenant_id)
            )
            request.state.tenant_id = tenant.id
            request.state.tenant_code = tenant.code
            return tenant

    tenant = await resolve_tenant_or_raise(db=db, x_tenant_id=x_tenant_id)
    if request is not None:
        request.state.tenant_id = tenant.id
        request.state.tenant_code = tenant.code
    return tenant
