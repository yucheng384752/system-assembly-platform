import uuid
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, Enum as SAEnum, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.p2_item import P2Item
    from app.models.p3_item import P3Item


class DataType(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Record(Base):
    __tablename__ = "records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lot_no: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    data_type: Mapped[DataType] = mapped_column(SAEnum(DataType, name="datatype_enum"), nullable=False)
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    additional_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    machine_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mold_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    production_lot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    p2_items: Mapped[list["P2Item"]] = relationship("P2Item", back_populates="record", cascade="all, delete-orphan")
    p3_items: Mapped[list["P3Item"]] = relationship("P3Item", back_populates="record", cascade="all, delete-orphan")
