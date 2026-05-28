import uuid
from pydantic import BaseModel


class ImportRequest(BaseModel):
    process_id: uuid.UUID


class ImportResponse(BaseModel):
    imported_rows: int
    skipped_rows: int
    elapsed_ms: int
    message: str
    process_id: uuid.UUID


class ImportErrorResponse(BaseModel):
    detail: str
    process_id: str
    error_code: str