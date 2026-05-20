import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class P1Record(Base):
    __tablename__ = "p1_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Lot Info
    lot_no_raw: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="原始批號 (#######-##)"
    )
    lot_no_norm: Mapped[int] = mapped_column(
        BigInteger, nullable=False, index=True, comment="正規化批號 (純數字)"
    )

    # Business Data
    product_name: Mapped[str | None] = mapped_column(String(100))
    material_code: Mapped[str | None] = mapped_column(String(50))
    quantity: Mapped[int | None] = mapped_column(Integer)
    production_date: Mapped[Date | None] = mapped_column(Date)

    # Metadata
    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "lot_no_norm", name="uq_p1_tenant_lot"),
    )


class P2Record(Base):
    __tablename__ = "p2_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Lot Info
    lot_no_raw: Mapped[str] = mapped_column(String(50), nullable=False)
    lot_no_norm: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # P2 Specific
    winder_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="分條編號"
    )
    sheet_width: Mapped[float | None] = mapped_column(
        String(50), comment="雖然是數值但為了彈性有時存字串，或依需求改Float"
    )
    # Note: User requirement said "winder 必填", "lot 欄位 Semi-finished productsLOT NO"

    # Metadata
    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "lot_no_norm", "winder_number", name="uq_p2_tenant_lot_winder"
        ),
    )


class P3Record(Base):
    __tablename__ = "p3_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Lot Info
    lot_no_raw: Mapped[str] = mapped_column(String(50), nullable=False)
    lot_no_norm: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # P3 Specific (Unique Key Components)
    production_date_yyyymmdd: Mapped[str] = mapped_column(
        String(8), nullable=False, comment="YYYYMMDD"
    )
    machine_no: Mapped[str] = mapped_column(String(50), nullable=False)
    mold_no: Mapped[str] = mapped_column(String(50), nullable=False)

    # Metadata
    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "production_date_yyyymmdd",
            "machine_no",
            "mold_no",
            "lot_no_norm",
            name="uq_p3_composite",
        ),
    )
