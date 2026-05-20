from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.core.tenant import Tenant

router = APIRouter(tags=["Tenants"])


class TenantResponse(BaseModel):
    id: UUID
    name: str
    code: str
    is_active: bool
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


@router.get("/api/tenants", response_model=list[TenantResponse])
async def get_tenants(
    request: Request,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    取得所有 Tenant 列表。
    前端根據回傳數量決定是否顯示選擇器。
    """
    settings = get_settings()
    admin_header = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_keys = getattr(settings, "admin_api_keys", set())

    is_admin_state = bool(getattr(getattr(request, "state", None), "is_admin", False))
    provided = request.headers.get(admin_header)
    is_admin_key = bool(provided and provided.strip() in admin_keys)
    is_admin = bool(is_admin_state or is_admin_key)
    auth_tenant_id = getattr(getattr(request, "state", None), "auth_tenant_id", None)

    stmt = select(Tenant)
    if not include_inactive or not is_admin:
        stmt = stmt.where(Tenant.is_active == True)
    if not is_admin and auth_tenant_id:
        stmt = stmt.where(Tenant.id == auth_tenant_id)

    result = await db.execute(stmt)
    return result.scalars().all()


class TenantCreateRequest(BaseModel):
    """Create a tenant.

    Used by UI bootstrap when no tenants exist.
    """

    name: str = Field(default="UT", min_length=1, max_length=100)
    code: str = Field(default="ut", min_length=1, max_length=50)
    is_active: bool = True
    is_default: bool = True


@router.post(
    "/api/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED
)
async def create_tenant(
    payload: TenantCreateRequest = Body(default_factory=TenantCreateRequest),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Create a tenant.

    Safety:
    - Will not delete/reset any data.
    - If a tenant already exists, returns 409 to avoid surprising mutations.
    """

    settings = get_settings()
    admin_header = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_keys = getattr(settings, "admin_api_keys", set())

    is_admin = (
        bool(getattr(getattr(request, "state", None), "is_admin", False))
        if request is not None
        else False
    )
    provided = request.headers.get(admin_header) if request is not None else None
    if not is_admin and not (provided and provided.strip() in admin_keys):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    tenant_count = (await db.execute(select(func.count(Tenant.id)))).scalar() or 0
    if tenant_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tenant already exists"
        )

    tenant = Tenant(
        name=payload.name,
        code=payload.code,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )

    db.add(tenant)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Another request may have created it concurrently.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tenant already exists"
        )

    await db.refresh(tenant)
    return tenant


class TenantAdminCreateRequest(BaseModel):
    """Create a tenant (admin).

    Unlike POST /api/tenants, this endpoint is intended for day-to-day admin CRUD
    and allows creating additional tenants after initialization.
    """

    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)
    is_active: bool = True
    is_default: bool = False


@router.post(
    "/api/tenants/admin",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_tenant(
    payload: TenantAdminCreateRequest = Body(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    admin_header = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_keys = getattr(settings, "admin_api_keys", set())

    is_admin = (
        bool(getattr(getattr(request, "state", None), "is_admin", False))
        if request is not None
        else False
    )
    provided = request.headers.get(admin_header) if request is not None else None
    if not is_admin and not (provided and provided.strip() in admin_keys):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    if payload.is_default:
        await db.execute(update(Tenant).values(is_default=False))

    tenant = Tenant(
        name=payload.name.strip(),
        code=payload.code.strip(),
        is_default=bool(payload.is_default),
        is_active=bool(payload.is_active),
    )
    db.add(tenant)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Tenant already exists"
        )

    await db.refresh(tenant)
    return tenant


class TenantUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    is_default: bool | None = None


@router.patch("/api/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdateRequest = Body(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Update tenant fields.

    Allowed callers:
    - Admin API key only.

    Notes:
    - We intentionally do not support changing tenant code here to avoid breaking logins and references.
    """

    settings = get_settings()
    admin_header = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_keys = getattr(settings, "admin_api_keys", set())

    is_admin = (
        bool(getattr(getattr(request, "state", None), "is_admin", False))
        if request is not None
        else False
    )
    provided = request.headers.get(admin_header) if request is not None else None
    if not is_admin and not (provided and provided.strip() in admin_keys):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    did_change = False
    if payload.name is not None:
        tenant.name = payload.name.strip()
        did_change = True
    if payload.is_active is not None:
        tenant.is_active = bool(payload.is_active)
        did_change = True

    if payload.is_default is not None:
        next_default = bool(payload.is_default)
        if next_default and not bool(tenant.is_default):
            # Make this tenant the only default.
            await db.execute(update(Tenant).values(is_default=False))
            tenant.is_default = True
            did_change = True
        elif (not next_default) and bool(tenant.is_default):
            tenant.is_default = False
            did_change = True

    if not did_change:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided"
        )

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.delete("/api/tenants/{tenant_id}", response_model=TenantResponse)
async def delete_tenant(
    tenant_id: UUID,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
):
    """Delete a tenant (safe delete).

    For safety, this performs a soft-delete by setting is_active=False.
    """

    settings = get_settings()
    admin_header = getattr(settings, "admin_api_key_header", "X-Admin-API-Key")
    admin_keys = getattr(settings, "admin_api_keys", set())

    is_admin = (
        bool(getattr(getattr(request, "state", None), "is_admin", False))
        if request is not None
        else False
    )
    provided = request.headers.get(admin_header) if request is not None else None
    if not is_admin and not (provided and provided.strip() in admin_keys):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin API key required"
        )

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )

    if bool(tenant.is_active):
        tenant.is_active = False
    if bool(tenant.is_default):
        tenant.is_default = False

    await db.commit()
    await db.refresh(tenant)
    return tenant
