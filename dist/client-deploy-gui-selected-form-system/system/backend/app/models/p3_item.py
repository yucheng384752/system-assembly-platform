import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.record import Record


class P3Item(Base):
    __tablename__ = "p3_items"
    __table_args__ = (UniqueConstraint("record_id", "product_id", name="uq_p3_item_record_product"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lot_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    production_lot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    machine_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mold_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bottom_tape_lot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    row_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    record: Mapped["Record"] = relationship("Record", back_populates="p3_items")
