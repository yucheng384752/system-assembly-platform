from sqlalchemy import Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base_record import BaseRecordMixin
from app.models.p2_item_v2 import P2ItemV2


class P2Record(BaseRecordMixin, Base):
    __tablename__ = "p2_records"

    winder_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Winder Number (1-20)"
    )

    # Relationships
    items_v2 = relationship(
        P2ItemV2, back_populates="p2_record", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "lot_no_norm", "winder_number", name="uq_p2_tenant_lot_winder"
        ),
        Index("ix_p2_tenant_lot_norm", "tenant_id", "lot_no_norm"),
    )
