import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EditReason(Base):
    """Per-tenant catalog of reason codes a user must pick from when correcting
    a row in a table that was already imported (see RowEdit.reason_id)."""

    __tablename__ = "edit_reasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(100), nullable=False, comment="機器可讀代碼")
    label: Mapped[str] = mapped_column(String(255), nullable=False, comment="顯示給使用者的原因文字")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_edit_reasons_tenant_code"),
    )
