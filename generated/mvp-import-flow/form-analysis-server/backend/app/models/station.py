"""Station models — generic workstation definitions, schemas, and linkage."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Station(Base):
    """Workstation definition (e.g. P1, P2, P3)."""

    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_stations_tenant_code"),
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
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_items: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    schemas: Mapped[list["StationSchema"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class StationSchema(Base):
    """Schema version for a station — defines fields, CSV mapping, and unique keys."""

    __tablename__ = "station_schemas"
    __table_args__ = (
        UniqueConstraint("station_id", "version", name="uq_station_schemas_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    record_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    item_fields: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    unique_key_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    csv_signature_columns: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True
    )
    csv_filename_pattern: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    csv_field_mapping: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    station: Mapped["Station"] = relationship(back_populates="schemas")


class StationLink(Base):
    """Traceability link between two stations."""

    __tablename__ = "station_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "from_station_id",
            "to_station_id",
            name="uq_station_links_pair",
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
    from_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stations.id"), nullable=False
    )
    to_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stations.id"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)
    link_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
