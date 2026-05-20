from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base_record import BaseRecordMixin
from app.models.p3_item_v2 import P3ItemV2


class P3Record(BaseRecordMixin, Base):
    __tablename__ = "p3_records"

    production_date_yyyymmdd: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Production Date (YYYYMMDD)"
    )

    machine_no: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Machine No (e.g. P24)"
    )

    mold_no: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Mold No (e.g. 238-2)"
    )

    product_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Derived Product ID (YYYYMMDD_machine_mold_lot)",
    )

    # Relationships
    items_v2 = relationship(
        P3ItemV2, back_populates="p3_record", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "production_date_yyyymmdd",
            "machine_no",
            "mold_no",
            "lot_no_norm",
            name="uq_p3_composite_key",
        ),
        Index("ix_p3_tenant_lot_norm", "tenant_id", "lot_no_norm"),
        Index(
            "ix_p3_tenant_prod_machine_mold",
            "tenant_id",
            "production_date_yyyymmdd",
            "machine_no",
            "mold_no",
        ),
    )
