"""MOD Subscription service — sync from external API and entitlement mapping."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mod_subscription import ModSubscription, ModSubscriptionEvent

# plan_code → list of capability strings granted to this tenant
_PLAN_ENTITLEMENTS: dict[str, list[str]] = {
    "basic":      ["upload", "query"],
    "standard":   ["upload", "query", "analytics", "export"],
    "enterprise": ["upload", "query", "analytics", "export", "admin", "api_access"],
}


async def sync_subscription(
    db: AsyncSession,
    tenant_id: str,
    external_subscription_id: str,
    mod_api_base_url: str,
    api_key: str | None = None,
) -> ModSubscription:
    """Fetch subscription from MOD API and upsert into local DB."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{mod_api_base_url.rstrip('/')}/subscriptions/{external_subscription_id}",
            headers=headers,
        )
        resp.raise_for_status()
        payload: dict = resp.json()

    result = await db.execute(
        select(ModSubscription).where(
            ModSubscription.tenant_id == tenant_id,
            ModSubscription.external_subscription_id == external_subscription_id,
        )
    )
    sub = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    plan_code: str = payload.get("plan_code", "unknown")
    status: str = payload.get("status", "active")
    raw_expires = payload.get("expires_at")
    expires_at = datetime.fromisoformat(raw_expires) if raw_expires else None

    if sub is None:
        sub = ModSubscription(
            tenant_id=tenant_id,
            external_subscription_id=external_subscription_id,
            plan_code=plan_code,
            status=status,
            expires_at=expires_at,
            synced_at=now,
            raw_payload=payload,
        )
        db.add(sub)
        await db.flush()  # generate id before linking event
    else:
        sub.plan_code = plan_code
        sub.status = status
        sub.expires_at = expires_at
        sub.synced_at = now
        sub.raw_payload = payload

    db.add(ModSubscriptionEvent(
        subscription_id=sub.id,
        event_type="sync",
        occurred_at=now,
        detail={"plan_code": plan_code, "status": status},
    ))
    await db.commit()
    await db.refresh(sub)
    return sub


async def process_webhook(
    db: AsyncSession,
    external_subscription_id: str,
    event: str,
    plan_code: str | None,
    status: str | None,
) -> ModSubscription:
    """Apply a webhook event to the matching subscription record."""
    result = await db.execute(
        select(ModSubscription).where(
            ModSubscription.external_subscription_id == external_subscription_id
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise LookupError(f"No subscription found for external_id={external_subscription_id!r}")

    now = datetime.now(timezone.utc)
    if status:
        sub.status = status
    if plan_code:
        sub.plan_code = plan_code
    sub.synced_at = now

    db.add(ModSubscriptionEvent(
        subscription_id=sub.id,
        event_type="webhook",
        occurred_at=now,
        detail={"event": event, "plan_code": plan_code, "status": status},
    ))
    await db.commit()
    await db.refresh(sub)
    return sub


def get_entitlements(subscription: ModSubscription) -> list[str]:
    """Return capability strings granted by the subscription plan."""
    if subscription.status != "active":
        return []
    return list(_PLAN_ENTITLEMENTS.get(subscription.plan_code, []))
