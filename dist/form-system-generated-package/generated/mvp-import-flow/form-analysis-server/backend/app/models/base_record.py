import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class BaseRecordMixin:
    """
    Base Mixin for P1/P2/P3 records.
    Contains common fields required for all record types.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Record ID"
    )

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Tenant ID",
        )

    lot_no_raw: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Original Lot No (e.g. 1234567-01)"
    )

    lot_no_norm: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Normalized Lot No (e.g. 123456701)",
    )

    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="Schema Version ID"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    extras: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default="{}", nullable=False, comment="Extra fields in JSON"
    )
