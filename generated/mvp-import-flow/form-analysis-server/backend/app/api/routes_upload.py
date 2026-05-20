"""
檔案上傳路由

處理檔案上傳、驗證和工作建立的 API 端點。
"""

import hashlib
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_import_v2 import process_import_job_background
from app.core import database
from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.audit import RowEdit
from app.models.core.schema_registry import TableRegistry
from app.models.import_job import ImportFile, ImportJob, ImportJobStatus
from app.models.pdf_conversion_job import PdfConversionJob, PdfConversionStatus
from app.models.pdf_upload import PdfUpload
from app.models.upload_error import UploadError
from app.models.upload_job import JobStatus, UploadJob
from app.schemas.audit import RowEditResponse
from app.schemas.pdf_conversion import (
    PdfConversionStatus as PdfSchemaConversionStatus,
)
from app.schemas.pdf_conversion import (
    PdfConvertIngestedUpload,
    PdfConvertIngestResponse,
    PdfConvertOutputFile,
    PdfConvertOutputsResponse,
    PdfConvertStatusResponse,
    PdfConvertTriggerRequest,
    PdfConvertTriggerResponse,
)
from app.schemas.upload import (
    FileUploadResponse,
    UpdateUploadContentRequest,
    UploadErrorResponse,
)
from app.services.audit_events import write_audit_event_best_effort
from app.services.pdf_conversion import (
    process_pdf_conversion_job_background,
)
from app.services.validation import ValidationError, file_validation_service

# 獲取日誌記錄器
logger = get_logger(__name__)


# 建立路由器
router = APIRouter(tags=["檔案上傳"])


@router.get(
    "/upload/pdf/service-status",
    summary="檢查 PDF 轉檔服務可用性",
    description="回傳 PDF 轉檔服務是否已配置並可使用。",
)
async def get_pdf_service_status() -> dict:
    """Check if PDF conversion service is available."""
    settings = get_settings()
    pdf_url = (getattr(settings, "pdf_server_url", None) or "").strip()
    return {
        "available": bool(pdf_url),
        "message": (
            "PDF 轉檔服務已配置" if pdf_url else "PDF 轉檔服務未設定 (PDF_SERVER_URL)"
        ),
    }


def _is_pdf_bytes(file_content: bytes) -> bool:
    # PDF header is "%PDF-" (bytes). Keep it simple; do not attempt deep validation here.
    return bool(file_content) and file_content[:5] == b"%PDF-"


def _decode_csv_text(file_content: bytes) -> str:
    # Prefer utf-8-sig to handle BOM if present.
    return file_content.decode("utf-8-sig", errors="replace")


async def _create_upload_job_from_csv_bytes(
    *,
    db: AsyncSession,
    http_request: Request,
    filename: str,
    file_content: bytes,
    skip_validate: bool = False,
) -> tuple[UploadJob, FileUploadResponse, str]:
    """Create an UploadJob.

    When skip_validate=True, the job is created as PENDING and validation is deferred.

    Returns: (upload_job, response, csv_text)
    """
    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    actor_api_key_id = getattr(
        getattr(http_request, "state", None), "auth_api_key_id", None
    )
    actor_api_key_label = getattr(
        getattr(http_request, "state", None), "auth_api_key_label", None
    )

    upload_job = UploadJob(
        filename=filename,
        status=JobStatus.PENDING,
        file_content=file_content,
        tenant_id=tenant_id,
        actor_api_key_id=actor_api_key_id,
        actor_label_snapshot=actor_api_key_label,
        last_status_changed_at=datetime.now(UTC),
        last_status_actor_kind="user",
        last_status_actor_api_key_id=actor_api_key_id,
        last_status_actor_label_snapshot=actor_api_key_label,
    )
    db.add(upload_job)
    await db.commit()
    await db.refresh(upload_job)

    if skip_validate:
        csv_text = _decode_csv_text(file_content)
        return (
            upload_job,
            FileUploadResponse(
                process_id=upload_job.process_id,
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
                sample_errors=[],
            ),
            csv_text,
        )

    validation_result = file_validation_service.validate_file(file_content, filename)

    upload_job.status = JobStatus.VALIDATED
    upload_job.last_status_changed_at = datetime.now(UTC)
    upload_job.last_status_actor_kind = "user"
    upload_job.last_status_actor_api_key_id = actor_api_key_id
    upload_job.last_status_actor_label_snapshot = actor_api_key_label
    upload_job.total_rows = validation_result["total_rows"]
    upload_job.valid_rows = validation_result["valid_rows"]
    upload_job.invalid_rows = validation_result["invalid_rows"]

    upload_errors = []
    for error in validation_result["errors"]:
        upload_errors.append(
            UploadError(
                job_id=upload_job.id,
                row_index=error["row_index"],
                field=error["field"],
                error_code=error["error_code"],
                message=error["message"],
            )
        )
    if upload_errors:
        db.add_all(upload_errors)

    await db.commit()
    await db.refresh(upload_job)

    sample_errors = [
        UploadErrorResponse(
            row_index=error["row_index"],
            field=error["field"],
            error_code=error["error_code"],
            message=error["message"],
        )
        for error in validation_result["sample_errors"]
    ]

    csv_text = _decode_csv_text(file_content)

    return (
        upload_job,
        FileUploadResponse(
            process_id=upload_job.process_id,
            total_rows=validation_result["total_rows"],
            valid_rows=validation_result["valid_rows"],
            invalid_rows=validation_result["invalid_rows"],
            sample_errors=sample_errors,
        ),
        csv_text,
    )


def _infer_table_code_from_filename(filename: str) -> str | None:
    name = (filename or "").strip()
    if not name:
        return None
    token = Path(name).name.split("_", 1)[0].upper()
    if token in {"P1", "P2", "P3"}:
        return token
    return None


async def _create_v2_import_job_from_upload_job(
    *,
    db: AsyncSession,
    http_request: Request,
    background_tasks: BackgroundTasks | None,
    tenant_id: uuid.UUID,
    upload_job: UploadJob,
    table_code: str | None = None,
    allow_duplicate: bool = True,
) -> uuid.UUID:
    inferred = (table_code or "").strip().upper() or _infer_table_code_from_filename(
        upload_job.filename
    )
    if not inferred:
        raise HTTPException(
            status_code=400,
            detail="table_code 無法從檔名推論（檔名需以 P1_/P2_/P3_ 開頭）",
        )

    result = await db.execute(
        select(TableRegistry).where(TableRegistry.table_code == inferred)
    )
    table_registry = result.scalar_one_or_none()
    if not table_registry:
        raise HTTPException(status_code=400, detail=f"Invalid table code: {inferred}")

    job_id = uuid.uuid4()
    batch_id = f"{datetime.now().strftime('%Y%m%d')}-{str(job_id)[:8]}"

    actor_api_key_id = getattr(
        getattr(http_request, "state", None), "auth_api_key_id", None
    )
    actor_api_key_label = getattr(
        getattr(http_request, "state", None), "auth_api_key_label", None
    )
    request_id = getattr(getattr(http_request, "state", None), "request_id", None)

    job = ImportJob(
        id=job_id,
        tenant_id=tenant_id,
        table_id=table_registry.id,
        batch_id=batch_id,
        status=ImportJobStatus.UPLOADED,
        total_files=1,
    )
    if actor_api_key_id:
        job.actor_api_key_id = actor_api_key_id
        job.actor_label_snapshot = actor_api_key_label
        job.last_status_actor_api_key_id = actor_api_key_id
        job.last_status_actor_label_snapshot = actor_api_key_label
    job.last_status_changed_at = datetime.now(UTC)
    job.last_status_actor_kind = "user"
    db.add(job)

    settings = get_settings()
    upload_dir = Path(settings.upload_temp_dir) / str(job_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        filename = Path(upload_job.filename).name
        content = bytes(upload_job.file_content or b"")
        file_path = upload_dir / filename
        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)
        file_path.write_bytes(content)

        if not allow_duplicate:
            dup_stmt = select(ImportFile).where(
                ImportFile.tenant_id == tenant_id,
                ImportFile.table_id == table_registry.id,
                ImportFile.file_hash == file_hash,
            )
            dup_result = await db.execute(dup_stmt)
            if dup_result.scalars().first():
                raise HTTPException(
                    status_code=400, detail=f"Duplicate file detected: {filename}"
                )

        import_file = ImportFile(
            job_id=job_id,
            tenant_id=tenant_id,
            table_id=table_registry.id,
            filename=filename,
            file_hash=file_hash,
            storage_path=str(file_path),
            file_size=file_size,
        )
        db.add(import_file)
    except Exception:
        if upload_dir.exists():
            import shutil

            shutil.rmtree(upload_dir)
        raise

    await db.commit()

    await write_audit_event_best_effort(
        tenant_id=tenant_id,
        actor_api_key_id=actor_api_key_id,
        actor_label_snapshot=actor_api_key_label,
        request_id=str(request_id) if request_id else None,
        method=http_request.method,
        path=http_request.url.path,
        status_code=201,
        action="import.job.create.from_pdf_ingest",
        metadata={
            "job_id": str(job_id),
            "batch_id": batch_id,
            "table_code": inferred,
            "upload_process_id": str(upload_job.process_id),
            "allow_duplicate": bool(allow_duplicate),
        },
        client_host=http_request.client.host if http_request.client else None,
        user_agent=http_request.headers.get("user-agent"),
    )

    # Trigger v2 parse/validate in background (if the global async session factory is available).
    if background_tasks and database.async_session_factory:
        background_tasks.add_task(process_import_job_background, job_id)

    return job_id


@router.post(
    "/upload/{process_id}/validate",
    response_model=FileUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="重新驗證既有上傳工作（不變更內容）",
)
async def validate_upload_job(
    process_id: uuid.UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    result = await db.execute(
        select(UploadJob).where(UploadJob.process_id == process_id)
    )
    upload_job = result.scalar_one_or_none()
    if not upload_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的上傳工作"
        )

    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    if (
        upload_job.tenant_id is not None
        and tenant_id
        and upload_job.tenant_id != tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的上傳工作"
        )
    if upload_job.tenant_id is None and tenant_id:
        upload_job.tenant_id = tenant_id

    if not upload_job.file_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="檔案內容為空"
        )

    actor_api_key_id = getattr(
        getattr(http_request, "state", None), "auth_api_key_id", None
    )
    actor_api_key_label = getattr(
        getattr(http_request, "state", None), "auth_api_key_label", None
    )

    # Clear old errors then re-validate current content.
    await db.execute(delete(UploadError).where(UploadError.job_id == upload_job.id))
    validation_result = file_validation_service.validate_file(
        upload_job.file_content, upload_job.filename
    )

    upload_job.status = JobStatus.VALIDATED
    upload_job.last_status_changed_at = datetime.now(UTC)
    upload_job.last_status_actor_kind = "user"
    upload_job.last_status_actor_api_key_id = actor_api_key_id
    upload_job.last_status_actor_label_snapshot = actor_api_key_label
    upload_job.total_rows = validation_result["total_rows"]
    upload_job.valid_rows = validation_result["valid_rows"]
    upload_job.invalid_rows = validation_result["invalid_rows"]

    upload_errors = []
    for error in validation_result["errors"]:
        upload_errors.append(
            UploadError(
                job_id=upload_job.id,
                row_index=error["row_index"],
                field=error["field"],
                error_code=error["error_code"],
                message=error["message"],
            )
        )
    if upload_errors:
        db.add_all(upload_errors)

    await db.commit()
    await db.refresh(upload_job)

    sample_errors = [
        UploadErrorResponse(
            row_index=error["row_index"],
            field=error["field"],
            error_code=error["error_code"],
            message=error["message"],
        )
        for error in validation_result["sample_errors"]
    ]

    return FileUploadResponse(
        process_id=upload_job.process_id,
        total_rows=validation_result["total_rows"],
        valid_rows=validation_result["valid_rows"],
        invalid_rows=validation_result["invalid_rows"],
        sample_errors=sample_errors,
    )


@router.put(
    "/upload/{process_id}/content",
    response_model=FileUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="儲存前端修正後的檔案內容並重新驗證",
    description="""
    前端表格修正後，將修改過的 CSV 內容寫回指定 process_id 的上傳工作，並重新執行驗證。

    - 會更新 upload_jobs.file_content
    - 會清除並重建 upload_errors
    - 會回傳最新的驗證統計與 sample_errors
    """,
)
async def update_upload_content(
    process_id: uuid.UUID,
    request: UpdateUploadContentRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    start_time = time.time()

    def _sha256_hex(data: bytes | None) -> str | None:
        if not data:
            return None
        return hashlib.sha256(data).hexdigest()

    try:
        result = await db.execute(
            select(UploadJob).where(UploadJob.process_id == process_id)
        )
        upload_job = result.scalar_one_or_none()

        if not upload_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到指定的上傳工作",
            )

        tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
        if (
            upload_job.tenant_id is not None
            and tenant_id
            and upload_job.tenant_id != tenant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到指定的上傳工作",
            )
        if upload_job.tenant_id is None and tenant_id:
            upload_job.tenant_id = tenant_id

        actor_api_key_id = getattr(
            getattr(http_request, "state", None), "auth_api_key_id", None
        )
        actor_api_key_label = getattr(
            getattr(http_request, "state", None), "auth_api_key_label", None
        )
        if actor_api_key_id:
            upload_job.actor_api_key_id = actor_api_key_id
            upload_job.actor_label_snapshot = actor_api_key_label

        csv_text = (request.csv_text or "").strip("\ufeff")
        if not csv_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="檔案內容為空",
            )

        before_summary = {
            "entity": "upload_job",
            "job_id": str(upload_job.id),
            "process_id": str(upload_job.process_id),
            "filename": upload_job.filename,
            "file_size": len(upload_job.file_content) if upload_job.file_content else 0,
            "file_sha256": _sha256_hex(upload_job.file_content),
            "total_rows": upload_job.total_rows,
            "valid_rows": upload_job.valid_rows,
            "invalid_rows": upload_job.invalid_rows,
            "status": str(upload_job.status) if upload_job.status else None,
        }

        file_content = csv_text.encode("utf-8-sig")
        upload_job.file_content = file_content

        # 清除舊的錯誤紀錄
        await db.execute(delete(UploadError).where(UploadError.job_id == upload_job.id))

        # 重新驗證
        validation_result = file_validation_service.validate_file(
            file_content,
            upload_job.filename,
        )

        upload_job.status = JobStatus.VALIDATED
        upload_job.last_status_changed_at = datetime.now(UTC)
        upload_job.last_status_actor_kind = "user"
        upload_job.last_status_actor_api_key_id = actor_api_key_id
        upload_job.last_status_actor_label_snapshot = actor_api_key_label
        upload_job.total_rows = validation_result["total_rows"]
        upload_job.valid_rows = validation_result["valid_rows"]
        upload_job.invalid_rows = validation_result["invalid_rows"]

        after_summary = {
            "entity": "upload_job",
            "job_id": str(upload_job.id),
            "process_id": str(upload_job.process_id),
            "filename": upload_job.filename,
            "file_size": len(file_content),
            "file_sha256": _sha256_hex(file_content),
            "total_rows": upload_job.total_rows,
            "valid_rows": upload_job.valid_rows,
            "invalid_rows": upload_job.invalid_rows,
            "status": str(upload_job.status) if upload_job.status else None,
        }

        if upload_job.tenant_id is not None:
            created_by = (
                actor_api_key_label
                or (str(actor_api_key_id) if actor_api_key_id else None)
                or "system"
            )
            row_edit = RowEdit(
                tenant_id=upload_job.tenant_id,
                table_code="UPLOAD",
                record_id=upload_job.id,
                reason_id=request.reason_id,
                reason_text=(request.reason_text or "")[:255] or None,
                before_json=before_summary,
                after_json=after_summary,
                created_by=created_by,
            )
            db.add(row_edit)

        upload_errors = []
        for error in validation_result["errors"]:
            upload_errors.append(
                UploadError(
                    job_id=upload_job.id,
                    row_index=error["row_index"],
                    field=error["field"],
                    error_code=error["error_code"],
                    message=error["message"],
                )
            )

        if upload_errors:
            db.add_all(upload_errors)

        await db.commit()
        await db.refresh(upload_job)

        sample_errors = [
            UploadErrorResponse(
                row_index=error["row_index"],
                field=error["field"],
                error_code=error["error_code"],
                message=error["message"],
            )
            for error in validation_result["sample_errors"]
        ]

        logger.info(
            "上傳工作內容已更新並重新驗證",
            process_id=str(upload_job.process_id),
            filename=upload_job.filename,
            total_rows=upload_job.total_rows,
            valid_rows=upload_job.valid_rows,
            invalid_rows=upload_job.invalid_rows,
            processing_time=time.time() - start_time,
        )

        return FileUploadResponse(
            process_id=upload_job.process_id,
            total_rows=upload_job.total_rows or 0,
            valid_rows=upload_job.valid_rows or 0,
            invalid_rows=upload_job.invalid_rows or 0,
            sample_errors=sample_errors,
        )

    except ValidationError as ve:
        # 驗證流程本身失敗（結構性問題）
        result = await db.execute(
            select(UploadJob).where(UploadJob.process_id == process_id)
        )
        upload_job = result.scalar_one_or_none()
        if upload_job:
            tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
            if upload_job.tenant_id is None and tenant_id:
                upload_job.tenant_id = tenant_id
            actor_api_key_id = getattr(
                getattr(http_request, "state", None), "auth_api_key_id", None
            )
            actor_api_key_label = getattr(
                getattr(http_request, "state", None), "auth_api_key_label", None
            )
            upload_job.status = JobStatus.PENDING
            upload_job.last_status_changed_at = datetime.now(UTC)
            upload_job.last_status_actor_kind = "user"
            upload_job.last_status_actor_api_key_id = actor_api_key_id
            upload_job.last_status_actor_label_snapshot = actor_api_key_label
            await db.commit()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=ve.message,
        )

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"儲存修改內容時發生錯誤：{str(e)}",
        )


@router.get(
    "/upload/{process_id}/edits",
    response_model=list[RowEditResponse],
    status_code=status.HTTP_200_OK,
    summary="查詢上傳工作修改紀錄",
)
async def list_upload_job_edits(
    process_id: uuid.UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[RowEditResponse]:
    result = await db.execute(
        select(UploadJob).where(UploadJob.process_id == process_id)
    )
    upload_job = result.scalar_one_or_none()
    if not upload_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的上傳工作"
        )

    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    if (
        upload_job.tenant_id is not None
        and tenant_id
        and upload_job.tenant_id != tenant_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的上傳工作"
        )
    if upload_job.tenant_id is None and tenant_id:
        upload_job.tenant_id = tenant_id
        await db.commit()
        await db.refresh(upload_job)

    if upload_job.tenant_id is None:
        return []

    edits = (
        (
            await db.execute(
                select(RowEdit)
                .where(
                    RowEdit.tenant_id == upload_job.tenant_id,
                    RowEdit.table_code == "UPLOAD",
                    RowEdit.record_id == upload_job.id,
                )
                .order_by(RowEdit.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return edits


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="檔案上傳與驗證",
    description="""
    上傳 CSV 或 Excel 檔案並進行資料驗證
    
    **支援的檔案格式：**
    - CSV (.csv)
    - Excel (.xlsx, .xls)
    
    **lot_no 擷取規則：**
    - P1/P2檔案：從檔案名稱中擷取 (格式：P1_1234567_01.csv 或 P2_1234567_01.csv)
        - P3檔案：優先從資料列的 "lot no" 欄位取得；若無則從 "P3_No." 取得
            - 支援彈性格式（例如：2507173_02_10 會正規化為 2507173_02）
    
    **驗證規則：**
    - 批號必須為 7位數字_2位數字（或 7位數字_2位數字_其他，會自動截取前 7+2 作為批號）
    - 檔案尾端若存在「整行空白」列會被忽略，不影響驗證結果
    - 其他欄位不進行強制驗證（不再強制要求特定欄位）
    
    **回傳內容：**
    - process_id: 處理流程識別碼
    - 統計資訊：總行數、有效行數、無效行數
    - sample_errors: 前10筆驗證錯誤（如果有的話）
    """,
    responses={
        200: {
            "description": "檔案上傳成功，包含驗證結果",
            "content": {
                "application/json": {
                    "example": {
                        "process_id": "123e4567-e89b-12d3-a456-426614174000",
                        "total_rows": 100,
                        "valid_rows": 95,
                        "invalid_rows": 5,
                        "sample_errors": [
                            {
                                "row_index": 2,
                                "field": "lot_no",
                                "error_code": "INVALID_FORMAT",
                                "message": "批號格式錯誤，應為7位數字_2位數字格式，實際值：123456",
                            }
                        ],
                    }
                }
            },
        },
        422: {
            "description": "檔案格式或內容驗證失敗",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_columns": {
                            "summary": "缺少必要欄位",
                            "value": {"detail": "缺少必要欄位：lot_no, quantity"},
                        },
                        "unknown_columns": {
                            "summary": "未知欄位",
                            "value": {"detail": "發現未知欄位：extra_field"},
                        },
                        "file_format": {
                            "summary": "不支援的檔案格式",
                            "value": {
                                "detail": "不支援的檔案格式，僅支援 CSV 和 Excel 檔案"
                            },
                        },
                    }
                }
            },
        },
        413: {
            "description": "檔案過大",
            "content": {
                "application/json": {"example": {"detail": "檔案大小超過限制"}}
            },
        },
        500: {
            "description": "伺服器內部錯誤",
            "content": {
                "application/json": {
                    "example": {"detail": "檔案處理時發生未預期的錯誤"}
                }
            },
        },
    },
)
async def upload_file(
    http_request: Request,
    file: UploadFile = File(..., description="要上傳的 CSV 或 Excel 檔案"),
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    """
    處理檔案上傳和驗證

    Args:
        file: 上傳的檔案
        db: 資料庫會話

    Returns:
        FileUploadResponse: 上傳結果

    Raises:
        HTTPException: 各種驗證或處理錯誤
    """
    start_time = time.time()

    logger.info("檔案上傳開始", filename=file.filename if file else None)

    if get_settings().multi_tenant_enabled:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={
                "detail": "Legacy upload endpoint is disabled in multi-tenant mode.",
                "hint": "Use v2 import pipeline: POST /api/v2/import/jobs.",
                "error_code": "LEGACY_UPLOAD_DISABLED",
            },
        )

    try:
        # 1. 檢查檔案是否存在
        if not file or not file.filename:
            logger.warning("上傳失敗：未選擇檔案或檔案名稱為空")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="未選擇檔案或檔案名稱為空",
            )

        # 2. 檢查檔案大小（10MB 限制）
        file_content = await file.read()
        file_size = len(file_content)

        if file_size == 0:
            logger.warning("上傳失敗：檔案內容為空", filename=file.filename)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="檔案內容為空"
            )

        if file_size > 10 * 1024 * 1024:  # 10MB
            logger.warning(
                "上傳失敗：檔案超過大小限制",
                filename=file.filename,
                file_size=file_size,
                max_size=10 * 1024 * 1024,
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="檔案大小超過 10MB 限制",
            )

        # 3. 建立上傳工作記錄
        tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
        actor_api_key_id = getattr(
            getattr(http_request, "state", None), "auth_api_key_id", None
        )
        actor_api_key_label = getattr(
            getattr(http_request, "state", None), "auth_api_key_label", None
        )
        upload_job = UploadJob(
            filename=file.filename,
            status=JobStatus.PENDING,
            file_content=file_content,  # 儲存檔案內容以供後續匯入使用
            tenant_id=tenant_id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_api_key_label,
            last_status_changed_at=datetime.now(UTC),
            last_status_actor_kind="user",
            last_status_actor_api_key_id=actor_api_key_id,
            last_status_actor_label_snapshot=actor_api_key_label,
        )

        db.add(upload_job)
        await db.commit()
        await db.refresh(upload_job)

        logger.info(
            "上傳工作已建立",
            process_id=str(upload_job.process_id),
            filename=file.filename,
            file_size=file_size,
        )

        try:
            # 4. 執行檔案驗證
            logger.info("開始檔案驗證", process_id=str(upload_job.process_id))
            validation_result = file_validation_service.validate_file(
                file_content, file.filename
            )

            # 5. 更新上傳工作統計資訊
            upload_job.status = JobStatus.VALIDATED
            upload_job.last_status_changed_at = datetime.now(UTC)
            upload_job.last_status_actor_kind = "user"
            upload_job.last_status_actor_api_key_id = actor_api_key_id
            upload_job.last_status_actor_label_snapshot = actor_api_key_label
            upload_job.total_rows = validation_result["total_rows"]
            upload_job.valid_rows = validation_result["valid_rows"]
            upload_job.invalid_rows = validation_result["invalid_rows"]

            # 6. 儲存驗證錯誤到資料庫
            upload_errors = []
            for error in validation_result["errors"]:
                upload_error = UploadError(
                    job_id=upload_job.id,
                    row_index=error["row_index"],
                    field=error["field"],
                    error_code=error["error_code"],
                    message=error["message"],
                )
                upload_errors.append(upload_error)

            if upload_errors:
                db.add_all(upload_errors)

            await db.commit()

            # 7. 準備回應資料
            sample_errors = [
                UploadErrorResponse(
                    row_index=error["row_index"],
                    field=error["field"],
                    error_code=error["error_code"],
                    message=error["message"],
                )
                for error in validation_result["sample_errors"]
            ]

            # 8. 記錄處理時間
            processing_time = time.time() - start_time

            logger.info(
                "檔案上傳和驗證完成",
                process_id=str(upload_job.process_id),
                filename=file.filename,
                total_rows=validation_result["total_rows"],
                valid_rows=validation_result["valid_rows"],
                invalid_rows=validation_result["invalid_rows"],
                processing_time=processing_time,
            )

            return FileUploadResponse(
                process_id=upload_job.process_id,
                total_rows=validation_result["total_rows"],
                valid_rows=validation_result["valid_rows"],
                invalid_rows=validation_result["invalid_rows"],
                sample_errors=sample_errors,
            )

        except ValidationError as ve:
            # 驗證錯誤：更新工作狀態但不刪除記錄
            upload_job.status = JobStatus.PENDING  # 保持 PENDING 狀態表示驗證失敗
            await db.commit()

            logger.error(
                "檔案驗證失敗",
                process_id=str(upload_job.process_id),
                filename=file.filename,
                error_message=ve.message,
            )

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=ve.message
            )

        except Exception as e:
            # 其他錯誤：回滾上傳工作建立
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"檔案處理時發生錯誤：{str(e)}",
            )

    except HTTPException:
        # 重新拋出 HTTP 例外
        raise

    except Exception as e:
        # 捕獲所有其他未處理的例外
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上傳檔案時發生未預期的錯誤：{str(e)}",
        )


@router.post(
    "/upload/pdf",
    response_model=FileUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="PDF 檔案上傳（僅保存，不做解析/匯入）",
    description="""
    上傳 PDF 檔案並保存到伺服器檔案系統（Docker volume / uploads）。

    目前僅開放「上傳與保存」：
    - 不會解析 PDF
    - 不會轉成 CSV
    - 不會匯入資料庫

    之後可再串接 PDF→JSON/CSV 的轉換服務。
    """,
    responses={
        422: {
            "description": "檔案格式或內容不符合要求",
            "content": {"application/json": {"example": {"detail": "僅支援 PDF 檔案"}}},
        },
        413: {
            "description": "檔案過大",
            "content": {
                "application/json": {"example": {"detail": "檔案大小超過 10MB 限制"}}
            },
        },
    },
)
async def upload_pdf(
    file: UploadFile = File(..., description="要上傳的 PDF 檔案"),
    http_request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> FileUploadResponse:
    start_time = time.time()

    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="未選擇檔案或檔案名稱為空",
        )

    filename_lower = file.filename.lower()
    if not filename_lower.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="僅支援 PDF 檔案",
        )

    file_content = await file.read()
    file_size = len(file_content)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="檔案內容為空",
        )

    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="檔案大小超過 10MB 限制",
        )

    if not _is_pdf_bytes(file_content):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="檔案內容不是有效的 PDF（缺少 %PDF- header）",
        )

    settings = get_settings()
    process_id = uuid.uuid4()

    pdf_dir = Path(settings.upload_temp_dir) / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    # Use process_id as the file name to avoid path traversal issues.
    target_path = pdf_dir / f"{process_id}.pdf"
    target_path.write_bytes(file_content)

    # Persist tenant-scoped upload record for later conversion/status.
    tenant_id = (
        getattr(getattr(http_request, "state", None), "tenant_id", None)
        if http_request
        else None
    )
    if not tenant_id:
        # Should not happen because the router is tenant-scoped via dependencies.
        # Still keep it defensive.
        try:
            target_path.unlink(missing_ok=True)
        except TypeError:
            if target_path.exists():
                target_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant context missing",
        )

    actor_api_key_id = (
        getattr(getattr(http_request, "state", None), "auth_api_key_id", None)
        if http_request
        else None
    )
    actor_api_key_label = (
        getattr(getattr(http_request, "state", None), "auth_api_key_label", None)
        if http_request
        else None
    )

    try:
        db.add(
            PdfUpload(
                process_id=process_id,
                tenant_id=tenant_id,
                filename=file.filename,
                file_size=file_size,
                storage_path=str(target_path),
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_api_key_label,
            )
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        try:
            target_path.unlink(missing_ok=True)
        except TypeError:
            if target_path.exists():
                target_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF 保存紀錄寫入失敗：{str(e)}",
        )

    logger.info(
        "PDF 上傳完成（僅保存）",
        process_id=str(process_id),
        filename=file.filename,
        file_size=file_size,
        processing_time=time.time() - start_time,
    )

    return FileUploadResponse(
        process_id=process_id,
        total_rows=0,
        valid_rows=0,
        invalid_rows=0,
        sample_errors=[],
    )


@router.post(
    "/upload/pdf/{process_id}/convert",
    response_model=PdfConvertTriggerResponse,
    status_code=status.HTTP_200_OK,
    summary="觸發 PDF → CSV 轉檔（非同步）",
    description="""
    觸發指定 process_id 的 PDF 進行轉檔。

    - 會建立一筆 PdfConversionJob 並回傳 job_id
    - 若系統未設定外部 PDF server，背景任務會標記為 FAILED（可從 status 取得錯誤原因）
    """,
)
async def trigger_pdf_convert(
    process_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    http_request: Request,
    body: PdfConvertTriggerRequest = None,
    db: AsyncSession = Depends(get_db),
) -> PdfConvertTriggerResponse:
    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=500, detail="Tenant context missing")

    # Pre-check: PDF server must be configured before creating conversion job
    settings = get_settings()
    pdf_url = (getattr(settings, "pdf_server_url", None) or "").strip()
    if not pdf_url:
        raise HTTPException(
            status_code=503,
            detail="PDF 轉檔服務未設定 (PDF_SERVER_URL is not configured)。請聯繫管理員配置外部 PDF 轉檔服務。",
        )

    upload = (
        await db.execute(
            select(PdfUpload).where(
                PdfUpload.process_id == process_id,
                PdfUpload.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="找不到指定的 PDF 上傳紀錄")

    # Idempotency: return latest active/completed job if exists.
    latest_job = (
        (
            await db.execute(
                select(PdfConversionJob)
                .where(
                    PdfConversionJob.process_id == process_id,
                    PdfConversionJob.tenant_id == tenant_id,
                )
                .order_by(PdfConversionJob.created_at.desc())
            )
        )
        .scalars()
        .first()
    )

    if latest_job and latest_job.status in {
        PdfConversionStatus.QUEUED,
        PdfConversionStatus.UPLOADING,
        PdfConversionStatus.PROCESSING,
        PdfConversionStatus.COMPLETED,
    }:
        return PdfConvertTriggerResponse(
            job_id=latest_job.id,
            status=PdfSchemaConversionStatus(latest_job.status.value),
        )

    actor_api_key_id = getattr(
        getattr(http_request, "state", None), "auth_api_key_id", None
    )
    actor_api_key_label = getattr(
        getattr(http_request, "state", None), "auth_api_key_label", None
    )

    winder_number = (body.winder_number if body else None)

    job = PdfConversionJob(
        process_id=process_id,
        tenant_id=tenant_id,
        status=PdfConversionStatus.QUEUED,
        progress=0,
        actor_api_key_id=actor_api_key_id,
        actor_label_snapshot=actor_api_key_label,
        winder_number=winder_number,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Background processing only when global session factory is available.
    if database.async_session_factory:
        background_tasks.add_task(process_pdf_conversion_job_background, job.id)
    else:
        if get_settings().environment.lower() != "testing":
            logger.warning(
                "Skip pdf conversion background task: async_session_factory not initialized"
            )

    return PdfConvertTriggerResponse(
        job_id=job.id, status=PdfSchemaConversionStatus.QUEUED
    )


@router.get(
    "/upload/pdf/{process_id}/convert/status",
    response_model=PdfConvertStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="查詢 PDF → CSV 轉檔狀態",
)
async def get_pdf_convert_status(
    process_id: uuid.UUID,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
) -> PdfConvertStatusResponse:
    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=500, detail="Tenant context missing")

    upload = (
        await db.execute(
            select(PdfUpload).where(
                PdfUpload.process_id == process_id,
                PdfUpload.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="找不到指定的 PDF 上傳紀錄")

    latest_job = (
        (
            await db.execute(
                select(PdfConversionJob)
                .where(
                    PdfConversionJob.process_id == process_id,
                    PdfConversionJob.tenant_id == tenant_id,
                )
                .order_by(PdfConversionJob.created_at.desc())
            )
        )
        .scalars()
        .first()
    )

    if not latest_job:
        return PdfConvertStatusResponse(
            status=PdfSchemaConversionStatus.NOT_STARTED, progress=0
        )

    return PdfConvertStatusResponse(
        status=PdfSchemaConversionStatus(latest_job.status.value),
        job_id=latest_job.id,
        progress=int(latest_job.progress or 0),
        external_job_id=latest_job.external_job_id,
        output_path=latest_job.output_path,
        output_paths=getattr(latest_job, "output_paths", None),
        error_summary=latest_job.error_summary,
    )


@router.post(
    "/upload/pdf/{process_id}/convert/ingest",
    response_model=PdfConvertIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="PDF 轉檔結果匯入為 UploadJob 並執行驗證",
    description="""
    將 PDF→CSV 轉檔完成後的 CSV 檔案（可能多份）建立成 UploadJob，並直接跑既有 CSV 驗證流程。

    - 支援 output_path (單一 CSV) 與 output_paths (多 CSV / zip 解壓)
    - 具備冪等性：若同一個 conversion job 已匯入過，會直接回傳既有 UploadJob
    - 可選擇 include_csv_text=true，讓前端立即顯示表格（會增加回應大小）
    """,
)
async def ingest_pdf_converted_csvs(
    process_id: uuid.UUID,
    http_request: Request,
    background_tasks: BackgroundTasks,
    include_csv_text: bool = False,
    skip_validate: bool = False,
    allow_duplicate: bool = True,
    db: AsyncSession = Depends(get_db),
) -> PdfConvertIngestResponse:
    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=500, detail="Tenant context missing")

    upload = (
        await db.execute(
            select(PdfUpload).where(
                PdfUpload.process_id == process_id,
                PdfUpload.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="找不到指定的 PDF 上傳紀錄")

    latest_job = (
        (
            await db.execute(
                select(PdfConversionJob)
                .where(
                    PdfConversionJob.process_id == process_id,
                    PdfConversionJob.tenant_id == tenant_id,
                )
                .order_by(PdfConversionJob.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if not latest_job:
        raise HTTPException(status_code=404, detail="找不到 PDF 轉檔工作")

    if latest_job.status != PdfConversionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="PDF 轉檔尚未完成")

    output_paths = getattr(latest_job, "output_paths", None)
    if not output_paths and latest_job.output_path:
        output_paths = [latest_job.output_path]

    if not output_paths:
        raise HTTPException(status_code=500, detail="PDF 轉檔完成但找不到輸出檔案")

    # Idempotency: if already ingested, return existing UploadJobs.
    existing = getattr(latest_job, "ingested_upload_jobs", None) or []
    if existing:
        uploads: list[PdfConvertIngestedUpload] = []
        for item in existing:
            try:
                job_process_id = uuid.UUID(str(item.get("process_id")))
            except Exception:
                continue
            ujob = (
                await db.execute(
                    select(UploadJob).where(
                        UploadJob.process_id == job_process_id,
                        UploadJob.tenant_id == tenant_id,
                    )
                )
            ).scalar_one_or_none()
            if not ujob:
                continue

            import_job_id = None
            try:
                if item.get("import_job_id"):
                    import_job_id = uuid.UUID(str(item.get("import_job_id")))
            except Exception:
                import_job_id = None

            errors = (
                (
                    await db.execute(
                        select(UploadError)
                        .where(UploadError.job_id == ujob.id)
                        .order_by(UploadError.row_index.asc(), UploadError.field.asc())
                        .limit(10)
                    )
                )
                .scalars()
                .all()
            )

            sample_errors = [
                UploadErrorResponse(
                    row_index=int(e.row_index),
                    field=str(e.field),
                    error_code=str(e.error_code),
                    message=str(e.message),
                )
                for e in errors
            ]

            csv_text = (
                _decode_csv_text(ujob.file_content or b"") if include_csv_text else None
            )
            uploads.append(
                PdfConvertIngestedUpload(
                    filename=ujob.filename or (item.get("filename") or "output.csv"),
                    process_id=ujob.process_id,
                    import_job_id=import_job_id,
                    total_rows=int(ujob.total_rows or 0),
                    valid_rows=int(ujob.valid_rows or 0),
                    invalid_rows=int(ujob.invalid_rows or 0),
                    sample_errors=sample_errors,
                    csv_text=csv_text,
                )
            )
        return PdfConvertIngestResponse(uploads=uploads)

    settings = get_settings()
    base_dir = Path(settings.upload_temp_dir).resolve()

    created: list[dict[str, str]] = []
    uploads: list[PdfConvertIngestedUpload] = []

    for p in output_paths:
        csv_path = Path(str(p)).resolve()
        if base_dir not in csv_path.parents and csv_path != base_dir:
            raise HTTPException(status_code=500, detail="輸出檔案路徑不合法")
        if not csv_path.exists() or not csv_path.is_file():
            raise HTTPException(status_code=500, detail=f"找不到輸出 CSV：{csv_path}")

        filename = csv_path.name

        # Some converters emit auxiliary files like error_list.csv which may be empty.
        if filename.strip().lower() == "error_list.csv":
            continue

        file_content = csv_path.read_bytes()
        if not file_content:
            # Skip empty outputs rather than failing the entire ingest.
            continue
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413, detail=f"CSV 檔案大小超過 10MB：{csv_path.name}"
            )
        try:
            upload_job, response, csv_text = await _create_upload_job_from_csv_bytes(
                db=db,
                http_request=http_request,
                filename=filename,
                file_content=file_content,
                skip_validate=skip_validate,
            )
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=ve.message)

        # Directly create v2 ImportJob from the ingested UploadJob.
        import_job_id = await _create_v2_import_job_from_upload_job(
            db=db,
            http_request=http_request,
            background_tasks=background_tasks,
            tenant_id=tenant_id,
            upload_job=upload_job,
            allow_duplicate=allow_duplicate,
        )

        created.append(
            {
                "filename": filename,
                "process_id": str(upload_job.process_id),
                "import_job_id": str(import_job_id),
            }
        )
        uploads.append(
            PdfConvertIngestedUpload(
                filename=filename,
                process_id=response.process_id,
                import_job_id=import_job_id,
                total_rows=response.total_rows,
                valid_rows=response.valid_rows,
                invalid_rows=response.invalid_rows,
                sample_errors=response.sample_errors,
                csv_text=csv_text if include_csv_text else None,
            )
        )

    if not uploads:
        raise HTTPException(
            status_code=422,
            detail="沒有可匯入的 CSV（輸出可能只有空檔或 error_list.csv）",
        )

    latest_job.ingested_upload_jobs = created
    await db.commit()

    return PdfConvertIngestResponse(uploads=uploads)


@router.get(
    "/upload/pdf/{process_id}/convert/outputs",
    response_model=PdfConvertOutputsResponse,
    status_code=status.HTTP_200_OK,
    summary="取得 PDF → CSV 轉檔輸出",
    description="""
    取得 PDF→CSV 轉檔完成後的輸出 CSV 檔案清單。

    - 支援 output_path (單一 CSV) 與 output_paths (多 CSV / zip 解壓)
    - 不會建立 UploadJob / ImportJob（前端可先預覽/編修，再自行走 v2 import jobs 驗證/匯入）
    - include_csv_text=true 時回傳 csv 內容（可能增加回應大小）
    """,
)
async def get_pdf_convert_outputs(
    process_id: uuid.UUID,
    http_request: Request,
    include_csv_text: bool = False,
    db: AsyncSession = Depends(get_db),
) -> PdfConvertOutputsResponse:
    tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=500, detail="Tenant context missing")

    upload = (
        await db.execute(
            select(PdfUpload).where(
                PdfUpload.process_id == process_id,
                PdfUpload.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if not upload:
        raise HTTPException(status_code=404, detail="找不到指定的 PDF 上傳紀錄")

    latest_job = (
        (
            await db.execute(
                select(PdfConversionJob)
                .where(
                    PdfConversionJob.process_id == process_id,
                    PdfConversionJob.tenant_id == tenant_id,
                )
                .order_by(PdfConversionJob.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if not latest_job:
        raise HTTPException(status_code=404, detail="找不到 PDF 轉檔工作")

    if latest_job.status != PdfConversionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="PDF 轉檔尚未完成")

    output_paths = getattr(latest_job, "output_paths", None)
    if not output_paths and latest_job.output_path:
        output_paths = [latest_job.output_path]

    if not output_paths:
        raise HTTPException(status_code=500, detail="PDF 轉檔完成但找不到輸出檔案")

    settings = get_settings()
    base_dir = Path(settings.upload_temp_dir).resolve()

    outputs: list[PdfConvertOutputFile] = []

    for p in output_paths:
        csv_path = Path(str(p)).resolve()
        if base_dir not in csv_path.parents and csv_path != base_dir:
            raise HTTPException(status_code=500, detail="輸出檔案路徑不合法")
        if not csv_path.exists() or not csv_path.is_file():
            raise HTTPException(status_code=500, detail=f"找不到輸出 CSV：{csv_path}")

        filename = csv_path.name

        # Some converters emit auxiliary files like error_list.csv which may be empty.
        if filename.strip().lower() == "error_list.csv":
            continue

        file_content = csv_path.read_bytes()
        if not file_content:
            continue
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=413, detail=f"CSV 檔案大小超過 10MB：{csv_path.name}"
            )

        csv_text = _decode_csv_text(file_content) if include_csv_text else None
        outputs.append(PdfConvertOutputFile(filename=filename, csv_text=csv_text))

    if not outputs:
        raise HTTPException(
            status_code=422,
            detail="沒有可用的 CSV（輸出可能只有空檔或 error_list.csv）",
        )

    return PdfConvertOutputsResponse(outputs=outputs)


@router.get(
    "/upload/{process_id}/status",
    summary="查詢上傳工作狀態",
    description="根據 process_id 查詢上傳工作的處理狀態和結果",
    responses={
        200: {
            "description": "成功取得工作狀態",
            "content": {
                "application/json": {
                    "example": {
                        "process_id": "123e4567-e89b-12d3-a456-426614174000",
                        "status": "VALIDATED",
                        "filename": "data.csv",
                        "total_rows": 100,
                        "valid_rows": 95,
                        "invalid_rows": 5,
                        "created_at": "2024-01-08T10:30:00Z",
                    }
                }
            },
        },
        404: {
            "description": "找不到指定的上傳工作",
            "content": {
                "application/json": {"example": {"detail": "找不到指定的上傳工作"}}
            },
        },
    },
)
async def get_upload_status(
    process_id: uuid.UUID, http_request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    查詢上傳工作狀態

    Args:
        process_id: 處理流程識別碼
        db: 資料庫會話

    Returns:
        dict: 工作狀態資訊

    Raises:
        HTTPException: 找不到工作或其他錯誤
    """
    try:
        # 根據 process_id 查詢上傳工作
        from sqlalchemy import select

        result = await db.execute(
            select(UploadJob).where(UploadJob.process_id == process_id)
        )
        upload_job = result.scalar_one_or_none()

        if not upload_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的上傳工作"
            )

        tenant_id = getattr(getattr(http_request, "state", None), "tenant_id", None)
        if (
            upload_job.tenant_id is not None
            and tenant_id
            and upload_job.tenant_id != tenant_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="找不到指定的上傳工作",
            )

        return {
            "process_id": upload_job.process_id,
            "status": upload_job.status.value,
            "filename": upload_job.filename,
            "total_rows": upload_job.total_rows,
            "valid_rows": upload_job.valid_rows,
            "invalid_rows": upload_job.invalid_rows,
            "created_at": upload_job.created_at.isoformat()
            if upload_job.created_at
            else None,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢工作狀態時發生錯誤：{str(e)}",
        )
