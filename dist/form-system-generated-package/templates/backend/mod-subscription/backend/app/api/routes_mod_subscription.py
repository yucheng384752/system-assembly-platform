from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.services.mod_subscription import (
    InvalidModWebhookSignature,
    ModSubscriptionInput,
    entitlements_for,
    get_subscription,
    upsert_subscription,
    verify_webhook_signature,
)

router = APIRouter(prefix="/api/mod/subscriptions", tags=["mod-subscriptions"])


class ModSubscriptionSyncRequest(BaseModel):
    tenant_id: uuid.UUID
    external_subscription_id: str = Field(min_length=1, max_length=128)
    plan_code: str = Field(min_length=1, max_length=80)
    status: str = Field(min_length=1, max_length=40)
    external_customer_id: str | None = Field(default=None, max_length=128)
    entitlement_payload: dict[str, Any] = Field(default_factory=dict)
    current_period_end: datetime | None = None


class ModSubscriptionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    external_subscription_id: str
    plan_code: str
    status: str
    entitlement_payload: dict[str, Any]
    current_period_end: datetime | None
    last_synced_at: datetime | None


def subscription_response(subscription) -> ModSubscriptionResponse:
    return ModSubscriptionResponse(
        id=subscription.id,
        tenant_id=subscription.tenant_id,
        external_subscription_id=subscription.external_subscription_id,
        plan_code=subscription.plan_code,
        status=subscription.status.value,
        entitlement_payload=subscription.entitlement_payload,
        current_period_end=subscription.current_period_end,
        last_synced_at=subscription.last_synced_at,
    )


@router.post("/sync", response_model=ModSubscriptionResponse)
async def sync_subscription(
    payload: ModSubscriptionSyncRequest,
    db: AsyncSession = Depends(get_db),
):
    subscription = await upsert_subscription(
        db,
        ModSubscriptionInput(**payload.model_dump()),
        source="api",
        raw_payload=payload.model_dump(mode="json"),
    )
    await db.commit()
    return subscription_response(subscription)


@router.post("/webhook", response_model=ModSubscriptionResponse)
async def receive_subscription_webhook(
    request: Request,
    x_mod_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    try:
        verify_webhook_signature(
            body,
            x_mod_signature,
            getattr(settings, "MOD_WEBHOOK_SECRET", None),
        )
    except InvalidModWebhookSignature as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    payload = ModSubscriptionSyncRequest.model_validate(await request.json())
    subscription = await upsert_subscription(
        db,
        ModSubscriptionInput(**payload.model_dump()),
        source="webhook",
        raw_payload=payload.model_dump(mode="json"),
    )
    await db.commit()
    return subscription_response(subscription)


@router.get("/{external_subscription_id}", response_model=ModSubscriptionResponse)
async def read_subscription(
    external_subscription_id: str,
    db: AsyncSession = Depends(get_db),
):
    subscription = await get_subscription(db, external_subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MOD subscription not found")
    return subscription_response(subscription)


@router.get("/{external_subscription_id}/entitlements")
async def read_subscription_entitlements(
    external_subscription_id: str,
    db: AsyncSession = Depends(get_db),
):
    subscription = await get_subscription(db, external_subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MOD subscription not found")
    return entitlements_for(subscription)
