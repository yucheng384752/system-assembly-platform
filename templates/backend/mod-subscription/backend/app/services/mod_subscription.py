from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mod_subscription import (
    ModSubscription,
    ModSubscriptionEvent,
    ModSubscriptionStatus,
)


class ModSubscriptionError(RuntimeError):
    pass


class InvalidModWebhookSignature(ModSubscriptionError):
    pass


@dataclass(frozen=True)
class ModSubscriptionInput:
    tenant_id: uuid.UUID
    external_subscription_id: str
    plan_code: str
    status: str
    external_customer_id: str | None = None
    entitlement_payload: dict[str, Any] | None = None
    current_period_end: datetime | None = None


async def upsert_subscription(
    db: AsyncSession,
    payload: ModSubscriptionInput,
    *,
    source: str,
    raw_payload: dict[str, Any] | None = None,
) -> ModSubscription:
    result = await db.execute(
        select(ModSubscription).where(
            ModSubscription.external_subscription_id == payload.external_subscription_id
        )
    )
    subscription = result.scalar_one_or_none()

    if subscription is None:
        subscription = ModSubscription(
            tenant_id=payload.tenant_id,
            external_subscription_id=payload.external_subscription_id,
        )
        db.add(subscription)

    subscription.external_customer_id = payload.external_customer_id
    subscription.plan_code = payload.plan_code
    subscription.status = normalize_status(payload.status)
    subscription.entitlement_payload = payload.entitlement_payload or {}
    subscription.current_period_end = payload.current_period_end
    subscription.last_synced_at = datetime.utcnow()

    db.add(
        ModSubscriptionEvent(
            subscription=subscription,
            event_type="subscription.synced",
            source=source,
            payload=raw_payload or {},
        )
    )
    await db.flush()
    await db.refresh(subscription)
    return subscription


async def get_subscription(
    db: AsyncSession,
    external_subscription_id: str,
) -> ModSubscription | None:
    result = await db.execute(
        select(ModSubscription).where(
            ModSubscription.external_subscription_id == external_subscription_id
        )
    )
    return result.scalar_one_or_none()


def entitlements_for(subscription: ModSubscription) -> dict[str, Any]:
    return {
        "plan_code": subscription.plan_code,
        "status": subscription.status.value,
        "active": subscription.status in {ModSubscriptionStatus.ACTIVE, ModSubscriptionStatus.TRIALING},
        "entitlements": subscription.entitlement_payload,
        "current_period_end": subscription.current_period_end.isoformat()
        if subscription.current_period_end
        else None,
    }


def normalize_status(value: str) -> ModSubscriptionStatus:
    try:
        return ModSubscriptionStatus(value.lower())
    except ValueError:
        return ModSubscriptionStatus.UNKNOWN


def verify_webhook_signature(body: bytes, signature: str | None, secret: str | None) -> None:
    if not secret:
        return
    if not signature:
        raise InvalidModWebhookSignature("Missing MOD webhook signature")

    digest = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    if not hmac.compare_digest(digest, signature):
        raise InvalidModWebhookSignature("Invalid MOD webhook signature")
