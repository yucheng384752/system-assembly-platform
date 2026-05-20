"""
上傳錯誤模型

記錄檔案上傳驗證過程中發現的錯誤資訊。
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from .upload_job import UploadJob


class UploadError(Base):
    """
    上傳錯誤模型

    記錄檔案驗證過程中發現的具體錯誤資訊，包括錯誤位置、類型和描述。
    """

    __tablename__ = "upload_errors"

    # 主鍵 - 使用 UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="錯誤記錄ID"
    )

    # 關聯的上傳工作
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_jobs.id", ondelete="CASCADE"),
        nullable=False,
        comment="關聯的上傳工作ID",
    )

    # 錯誤位置資訊
    row_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="發生錯誤的行索引（從0開始）"
    )

    field: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="發生錯誤的欄位名稱"
    )

    # 錯誤詳細資訊
    error_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="錯誤程式碼，如：INVALID_FORMAT、REQUIRED_FIELD等",
    )

    message: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="錯誤訊息描述"
    )

    # 時間戳記
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="錯誤記錄建立時間",
    )

    # 關聯關係
    job: Mapped["UploadJob"] = relationship(
        "UploadJob", back_populates="errors", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<UploadError(id={self.id}, job_id={self.job_id}, "
            f"row={self.row_index}, field='{self.field}', "
            f"error_code='{self.error_code}')>"
        )


# 為常查欄位建立複合索引
Index(
    "ix_upload_errors_job_id_row_index",
    UploadError.job_id,
    UploadError.row_index,
    postgresql_using="btree",
)
