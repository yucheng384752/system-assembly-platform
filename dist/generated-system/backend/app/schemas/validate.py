import uuid
from datetime import datetime
from pydantic import BaseModel


class ErrorItem(BaseModel):
    row_index: int
    field: str
    error_code: str
    message: str


class ErrorNotFoundResponse(BaseModel):
    detail: str
    process_id: str
    error_code: str


class ValidateResult(BaseModel):
    job_id: uuid.UUID
    process_id: uuid.UUID
    filename: str
    status: str
    created_at: datetime
    statistics: dict
    errors: list[ErrorItem]
    pagination: dict