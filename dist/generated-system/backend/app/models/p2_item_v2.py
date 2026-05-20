"""P2 Items V2 Model - Stores expanded P2 row data (one record per winder)"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class P2ItemV2(Base):
    """P2 明細資料 - 每個 winder 一筆記錄"""

    __tablename__ = "p2_items_v2"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    p2_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("p2_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    winder_number = Column(Integer, nullable=False)
    production_date_yyyymmdd = Column(Integer, nullable=True)
    trace_lot_no = Column(String(32), nullable=True)

    # P2 Data Fields
    sheet_width = Column(Float)
    thickness1 = Column(Float)
    thickness2 = Column(Float)
    thickness3 = Column(Float)
    thickness4 = Column(Float)
    thickness5 = Column(Float)
    thickness6 = Column(Float)
    thickness7 = Column(Float)
    appearance = Column(Integer)
    rough_edge = Column(Integer)
    slitting_result = Column(Integer)

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
    p2_record = relationship("P2Record", back_populates="items_v2")
    tenant = relationship("Tenant")

    __table_args__ = (
        Index("ix_p2_items_v2_p2_record_id", "p2_record_id"),
        Index("ix_p2_items_v2_tenant_id", "tenant_id"),
        Index("ix_p2_items_v2_winder_number", "winder_number"),
        Index("ix_p2_items_v2_production_date", "production_date_yyyymmdd"),
        Index("ix_p2_items_v2_tenant_slitting_result", "tenant_id", "slitting_result"),
        Index("ix_p2_items_v2_tenant_trace_lot_no", "tenant_id", "trace_lot_no"),
        Index("ix_p2_items_v2_row_data_gin", "row_data", postgresql_using="gin"),
        UniqueConstraint(
            "p2_record_id", "winder_number", name="uq_p2_items_v2_record_winder"
        ),
    )

    def __repr__(self):
        return f"<P2ItemV2(id={self.id}, p2_record_id={self.p2_record_id}, winder={self.winder_number})>"
