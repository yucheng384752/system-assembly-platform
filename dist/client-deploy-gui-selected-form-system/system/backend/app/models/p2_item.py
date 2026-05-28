import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.record import Record


class P2Item(Base):
    __tablename__ = "p2_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    winder_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness1: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness2: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness3: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness4: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness5: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness6: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness7: Mapped[float | None] = mapped_column(Float, nullable=True)
    appearance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rough_edge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slitting_result: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    record: Mapped["Record"] = relationship("Record", back_populates="p2_items")
