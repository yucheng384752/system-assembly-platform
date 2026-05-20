"""P3 Items V2 Model - Stores expanded P3 production details"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class P3ItemV2(Base):
    """P3 明細資料 - 每筆生產明細"""

    __tablename__ = "p3_items_v2"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    p3_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("p3_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    row_no = Column(Integer, nullable=False)

    # P3 Data Fields
    product_id = Column(String(100), unique=True)
    lot_no = Column(String(50), nullable=False)
    production_date = Column(Date)
    machine_no = Column(String(20))
    mold_no = Column(String(50))
    production_lot = Column(Integer)
    source_winder = Column(Integer)
    specification = Column(String(100))
    bottom_tape_lot = Column(String(50))

    # Original row data from CSV
    row_data = Column(JSONB)

    @staticmethod
    def _utcnow():
        return datetime.now(UTC)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    p3_record = relationship("P3Record", back_populates="items_v2")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index("ix_p3_items_v2_p3_record_id", "p3_record_id"),
        Index("ix_p3_items_v2_tenant_id", "tenant_id"),
        Index("ix_p3_items_v2_lot_no", "lot_no"),
        Index("ix_p3_items_v2_product_id", "product_id"),
        Index("ix_p3_items_v2_machine_no", "machine_no"),
        Index("ix_p3_items_v2_mold_no", "mold_no"),
        Index("ix_p3_items_v2_source_winder", "source_winder"),
        Index("ix_p3_items_v2_production_date", "production_date"),
        Index("ix_p3_items_v2_row_data_gin", "row_data", postgresql_using="gin"),
        UniqueConstraint("p3_record_id", "row_no", name="uq_p3_items_v2_record_row"),
    )

    def __repr__(self):
        return f"<P3ItemV2(id={self.id}, p3_record_id={self.p3_record_id}, row={self.row_no})>"
