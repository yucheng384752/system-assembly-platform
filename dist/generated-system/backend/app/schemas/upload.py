import uuid
from pydantic import BaseModel


class UploadErrorResponse(BaseModel):
    row_index: int
    field: str
    error_code: str
    message: str


class FileUploadResponse(BaseModel):
    process_id: uuid.UUID
    total_rows: int
    valid_rows: int
    invalid_rows: int
    sample_errors: list[UploadErrorResponse]


class UpdateUploadContentRequest(BaseModel):
    csv_text: str
    reason_id: str | None = None
    reason_text: str | None = None