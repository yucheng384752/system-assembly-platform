"""Analytics field mapping — config-driven replacement for analytics_field_mapping.py."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalyticsMapping(Base):
    """Maps a JSONB path in record data to a named analytics output column."""

    __tablename__ = "analytics_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "station_id",
            "output_column",
            name="uq_analytics_mappings_col",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_path: Mapped[str] = mapped_column(String(200), nullable=False)
    output_column: Mapped[str] = mapped_column(String(100), nullable=False)
    output_order: Mapped[int] = mapped_column(Integer, nullable=False)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")
    null_if_missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
