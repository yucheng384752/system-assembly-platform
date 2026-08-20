import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class RowEditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    table_code: str
    record_id: uuid.UUID
    reason_id: str | None = None
    reason_text: str | None = None
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    created_by: str | None = None
    created_at: datetime