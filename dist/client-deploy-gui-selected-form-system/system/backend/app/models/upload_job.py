"""
上傳工作模型

代表每次檔案上傳的工作記錄，包含處理狀態、統計資訊等。
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.upload_error import UploadError


class JobStatus(str, Enum):
    """上傳工作狀態列舉"""

    PENDING = "PENDING"  # 等待處理
    VALIDATED = "VALIDATED"  # 已驗證
    IMPORTED = "IMPORTED"  # 已匯入


class UploadJob(Base):
    """
    上傳工作模型

    記錄每次檔案上傳的基本資訊、處理狀態和統計資料。
    """

    __tablename__ = "upload_jobs"

    # 主鍵 - 使用 UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="工作ID"
    )

    # 基本資訊
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="上傳的檔案名稱"
    )

    # 檔案內容儲存
    file_content: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, comment="上傳檔案的二進位內容，用於重新處理"
    )

    # 時間戳記
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="建立時間",
    )

    # Traceability
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
        comment="Tenant ID (for traceability)",
    )
    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_api_keys.id"),
        nullable=True,
        index=True,
        comment="API key ID (who initiated/last updated the job)",
    )
    actor_label_snapshot: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="API key label snapshot"
    )

    last_status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="When status was last changed"
    )
    last_status_actor_kind: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Who changed status last (e.g., user/system)"
    )
    last_status_actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenant_api_keys.id"),
        nullable=True,
        index=True,
        comment="API key ID for last status change (if any)",
    )
    last_status_actor_label_snapshot: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="API key label snapshot for last status change",
    )

    # 處理狀態
    status: Mapped[JobStatus] = mapped_column(
        ENUM(JobStatus, name="job_status_enum"),
        default=JobStatus.PENDING,
        nullable=False,
        comment="處理狀態",
    )

    # 統計資訊
    total_rows: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="總行數"
    )

    valid_rows: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="有效行數"
    )

    invalid_rows: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="無效行數"
    )

    # 處理識別碼 - 用於追蹤整個處理流程
    process_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid.uuid4,
        index=True,  # 為 process_id 建立索引
        comment="處理流程識別碼，用於追蹤整個上傳處理過程",
    )

    # 關聯關係
    errors: Mapped[list["UploadError"]] = relationship(
        "UploadError", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<UploadJob(id={self.id}, filename='{self.filename}', "
            f"status={self.status}, process_id={self.process_id})>"
        )
