"""MOD Subscription API — sync, webhook receiver, and entitlement query."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_current_tenant, get_db
from app.models.core.tenant import Tenant
from app.models.mod_subscription import ModSubscription
from app.services.mod_subscription import get_entitlements, process_webhook, sync_subscription

router = APIRouter(prefix="/api/mod", tags=["MOD 訂閱權益"])


class SyncRequest(BaseModel):
    external_subscription_id: str


class WebhookPayload(BaseModel):
    external_subscription_id: str
    event: str            # renewed | cancelled | expired | plan_changed
    plan_code: str | None = None
    status: str | None = None


class SubscriptionResponse(BaseModel):
    external_subscription_id: str
    plan_code: str
    status: str
    expires_at: str | None
    synced_at: str


def _to_response(sub: ModSubscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        external_subscription_id=sub.external_subscription_id,
        plan_code=sub.plan_code,
        status=sub.status,
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
        synced_at=sub.synced_at.isoformat(),
    )


@router.post("/subscriptions/sync", response_model=SubscriptionResponse)
async def sync_mod_subscription(
    body: SyncRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Manually trigger a sync from MOD API for this tenant's subscription."""
    mod_api_base_url = os.getenv("MOD_API_BASE_URL", "")
    if not mod_api_base_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MOD_API_BASE_URL not configured")
    mod_api_key = os.getenv("MOD_API_KEY")
    sub = await sync_subscription(
        db, str(tenant.id), body.external_subscription_id, mod_api_base_url, mod_api_key
    )
    return _to_response(sub)


@router.post("/subscriptions/webhook", status_code=status.HTTP_200_OK)
async def receive_mod_webhook(
    body: WebhookPayload,
    db: AsyncSession = Depends(get_db),
    x_mod_webhook_secret: str | None = Header(default=None, alias="X-Mod-Webhook-Secret"),
):
    """Receive an event webhook from MOD provider."""
    expected = os.getenv("MOD_WEBHOOK_SECRET", "")
    if expected and x_mod_webhook_secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")
    try:
        await process_webhook(
            db,
            external_subscription_id=body.external_subscription_id,
            event=body.event,
            plan_code=body.plan_code,
            status=body.status,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/subscriptions/{external_subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    external_subscription_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Get a subscription record for the current tenant."""
    result = await db.execute(
        select(ModSubscription).where(
            ModSubscription.tenant_id == tenant.id,
            ModSubscription.external_subscription_id == external_subscription_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return _to_response(sub)


@router.get("/subscriptions/{external_subscription_id}/entitlements")
async def get_subscription_entitlements(
    external_subscription_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """Return capability entitlements derived from the subscription plan."""
    result = await db.execute(
        select(ModSubscription).where(
            ModSubscription.tenant_id == tenant.id,
            ModSubscription.external_subscription_id == external_subscription_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return {
        "external_subscription_id": sub.external_subscription_id,
        "plan_code": sub.plan_code,
        "status": sub.status,
        "entitlements": get_entitlements(sub),
    }
