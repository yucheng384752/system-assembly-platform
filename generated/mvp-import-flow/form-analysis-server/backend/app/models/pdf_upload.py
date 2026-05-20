import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PdfUpload(Base):
    __tablename__ = "pdf_uploads"

    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="PDF process id (also used as filename key)",
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
        comment="Tenant ID",
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename",
    )

    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="PDF file size in bytes",
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Storage path on server",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Created time",
    )

    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_api_keys.id"),
        nullable=True,
        index=True,
        comment="API key ID (who uploaded)",
    )

    actor_label_snapshot: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="API key label snapshot",
    )
