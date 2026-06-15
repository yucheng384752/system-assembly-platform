"""MOD Subscription models — external subscription state and audit log."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.db_types import JsonBColumn


class ModSubscription(Base):
    """One row per (tenant, external_subscription_id) — tracks current plan and status."""

    __tablename__ = "mod_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_subscription_id", name="uq_mod_sub_tenant_external"),
        Index("ix_mod_sub_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonBColumn(), nullable=True)

    events: Mapped[list[ModSubscriptionEvent]] = relationship(
        "ModSubscriptionEvent", back_populates="subscription", cascade="all, delete-orphan"
    )


class ModSubscriptionEvent(Base):
    """Audit log — one row per sync, webhook, or entitlement change event."""

    __tablename__ = "mod_subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mod_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    detail: Mapped[dict[str, Any] | None] = mapped_column(JsonBColumn(), nullable=True)

    subscription: Mapped[ModSubscription] = relationship("ModSubscription", back_populates="events")
