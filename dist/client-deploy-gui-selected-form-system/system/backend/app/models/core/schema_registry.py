import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TableRegistry(Base):
    __tablename__ = "table_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="e.g. p1_records"
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    table_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("table_registry.id"), nullable=False
    )

    schema_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="SHA256 of schema_json"
    )
    header_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Hash of sorted headers"
    )
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
