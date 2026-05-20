from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ModSubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class ModSubscription(Base):
    __tablename__ = "mod_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    external_subscription_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    external_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    plan_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ModSubscriptionStatus] = mapped_column(
        Enum(ModSubscriptionStatus),
        default=ModSubscriptionStatus.UNKNOWN,
        nullable=False,
    )
    entitlement_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    events: Mapped[list["ModSubscriptionEvent"]] = relationship(
        "ModSubscriptionEvent",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )


class ModSubscriptionEvent(Base):
    __tablename__ = "mod_subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mod_subscriptions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscription: Mapped[ModSubscription] = relationship("ModSubscription", back_populates="events")


Index("ix_mod_subscriptions_tenant_status", ModSubscription.tenant_id, ModSubscription.status)
