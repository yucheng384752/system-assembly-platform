import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ImportJobStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    VALIDATING = "VALIDATING"
    FAILED = "FAILED"
    READY = "READY"
    COMMITTING = "COMMITTING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("table_registry.id"), nullable=False
    )
    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schema_versions.id"), nullable=True
    )

    # 批次識別碼，方便人類閱讀與查詢
    batch_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), default=ImportJobStatus.UPLOADED, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)

    total_files: Mapped[int] = mapped_column(Integer, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    error_summary: Mapped[dict[str, Any]] = mapped_column(
        JSON, server_default="{}", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Traceability
    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_api_keys.id"),
        nullable=True,
        index=True,
    )
    actor_label_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)

    last_status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_actor_kind: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    last_status_actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_api_keys.id"),
        nullable=True,
        index=True,
    )
    last_status_actor_label_snapshot: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    # Relationships
    files: Mapped[list["ImportFile"]] = relationship(
        "ImportFile", back_populates="job", cascade="all, delete-orphan"
    )
    staging_rows: Mapped[list["StagingRow"]] = relationship(
        "StagingRow", back_populates="job", cascade="all, delete-orphan"
    )


class ImportFile(Base):
    __tablename__ = "import_files"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("table_registry.id"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA-256"
    )
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    row_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    job: Mapped["ImportJob"] = relationship("ImportJob", back_populates="files")
    staging_rows: Mapped[list["StagingRow"]] = relationship(
        "StagingRow", back_populates="file"
    )


class StagingRow(Base):
    __tablename__ = "staging_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("import_files.id", ondelete="CASCADE"), nullable=False
    )

    row_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Original row number in file (1-based)"
    )

    parsed_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    errors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    job: Mapped["ImportJob"] = relationship("ImportJob", back_populates="staging_rows")
    file: Mapped["ImportFile"] = relationship(
        "ImportFile", back_populates="staging_rows"
    )
