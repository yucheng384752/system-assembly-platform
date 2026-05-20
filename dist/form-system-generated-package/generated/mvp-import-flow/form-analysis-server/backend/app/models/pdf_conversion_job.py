import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PdfConversionStatus(StrEnum):
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PdfConversionJob(Base):
    __tablename__ = "pdf_conversion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Conversion job id",
    )

    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pdf_uploads.process_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="PDF upload process id",
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
        comment="Tenant ID",
    )

    status: Mapped[PdfConversionStatus] = mapped_column(
        ENUM(PdfConversionStatus, name="pdf_conversion_status_enum"),
        default=PdfConversionStatus.QUEUED,
        nullable=False,
        comment="Conversion status",
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="0-100 progress",
    )

    external_job_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="External PDF server job id (if any)",
    )

    output_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Converted output path (e.g. csv)",
    )

    output_paths: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Converted output paths (e.g. multiple csv files extracted from zip)",
    )

    ingested_upload_jobs: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Upload jobs created from converted outputs (for idempotency)",
    )

    error_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Error summary / diagnostics",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_api_keys.id"),
        nullable=True,
        index=True,
        comment="API key ID (who triggered)",
    )

    actor_label_snapshot: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="API key label snapshot",
    )

    winder_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="P2 winder number provided by user at conversion trigger time (1-20)",
    )
