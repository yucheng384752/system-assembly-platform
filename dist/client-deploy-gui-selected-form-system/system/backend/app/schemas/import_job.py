import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class ImportFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_hash: str
    file_size: int
    row_count: int
    created_at: datetime


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    table_id: uuid.UUID
    batch_id: str
    status: str
    progress: int
    total_files: int
    total_rows: int
    error_count: int
    error_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    actor_label_snapshot: str | None = None
    last_status_changed_at: datetime | None = None
    last_status_actor_kind: str | None = None
    last_status_actor_label_snapshot: str | None = None
    files: list[ImportFileRead] = []


class ImportJobErrorRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_index: int
    is_valid: bool
    parsed_json: dict[str, Any]
    errors_json: list[dict[str, Any]] | None = None