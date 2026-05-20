import hashlib
import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db
from app.core import database
from app.core.config import get_settings
from app.models.core.schema_registry import TableRegistry
from app.models.core.tenant import Tenant
from app.models.import_job import ImportFile, ImportJob, ImportJobStatus, StagingRow
from app.models.upload_job import UploadJob
from app.schemas.import_job import ImportJobErrorRow, ImportJobRead
from app.services.audit_events import write_audit_event_best_effort
from app.services.import_v2 import ImportService

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


class ImportJobFromUploadJobRequest(BaseModel):
    upload_process_id: uuid.UUID
    table_code: str | None = None
    allow_duplicate: bool = False


def _infer_table_code_from_filename(filename: str) -> str | None:
    # Heuristic: prefer leading token before '_' (e.g., P1_2503033_01.csv)
    name = (filename or "").strip()
    if not name:
        return None
    token = Path(name).name.split("_", 1)[0].upper()
    if token in {"P1", "P2", "P3"}:
        return token
    return None


async def _mark_job_failed(job_id: uuid.UUID, error: Exception | str) -> None:
    if not database.async_session_factory:
        logger.error(
            f"Async session factory not initialized; cannot mark job {job_id} as FAILED"
        )
        return

    error_text = str(error)
    async with database.async_session_factory() as db:
        stmt = select(ImportJob).where(ImportJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return
        prev_status = job.status
        job.status = ImportJobStatus.FAILED
        job.error_summary = {"error": error_text}
        job.last_status_changed_at = datetime.now(UTC)
        job.last_status_actor_kind = "system"
        job.last_status_actor_api_key_id = None
        job.last_status_actor_label_snapshot = None
        await db.commit()

        await write_audit_event_best_effort(
            tenant_id=job.tenant_id,
            actor_api_key_id=None,
            actor_label_snapshot=None,
            request_id=None,
            method="INTERNAL",
            path=f"/internal/v2/import/jobs/{job.id}/status",
            status_code=0,
            action="import.job.status",
            metadata={
                "job_id": str(job.id),
                "from_status": str(prev_status),
                "to_status": str(ImportJobStatus.FAILED),
                "actor_kind": "system",
                "error": error_text[:200],
            },
        )


async def process_import_job_background(
    job_id: uuid.UUID,
    *,
    actor_api_key_id: uuid.UUID | None = None,
    actor_label_snapshot: str | None = None,
    actor_kind: str = "system",
):
    """
    Background task to parse and validate import job.
    """
    if not database.async_session_factory:
        await _mark_job_failed(job_id, "Async session factory not initialized")
        return

    async with database.async_session_factory() as db:
        service = ImportService(db)
        try:
            logger.info(f"Starting background processing for job {job_id}")
            # 1. Parse
            await service.parse_job(
                job_id,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )
            # 2. Validate
            await service.validate_job(
                job_id,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )
            logger.info(f"Completed background processing for job {job_id}")
        except Exception as e:
            logger.exception(f"Background processing failed for job {job_id}: {e}")
            await _mark_job_failed(job_id, e)


@router.post("/jobs", response_model=ImportJobRead, status_code=status.HTTP_201_CREATED)
async def create_import_job(
    request: Request,
    background_tasks: BackgroundTasks,
    table_code: str = Form(..., description="Target table code (e.g., 'P1', 'P2')"),
    allow_duplicate: bool = Form(
        False, description="Allow importing the same file content multiple times"
    ),
    files: list[UploadFile] = File(..., description="Files to upload"),
    db: AsyncSession = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """
    Create a new import job with uploaded files.
    """
    # 1. Validate Table Code
    stmt = select(TableRegistry).where(TableRegistry.table_code == table_code)
    result = await db.execute(stmt)
    table_registry = result.scalar_one_or_none()

    if not table_registry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid table code: {table_code}",
        )

    # 1.5 Check Mixed Batch (Extensions)
    exts = {Path(f.filename).suffix.lower() for f in files}
    if len(exts) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mixed file formats are not allowed. Found: {', '.join(exts)}",
        )

    # 2. Create Job
    job_id = uuid.uuid4()
    # Generate batch_id
    batch_id = f"{datetime.now().strftime('%Y%m%d')}-{str(job_id)[:8]}"

    job = ImportJob(
        id=job_id,
        tenant_id=current_tenant.id,
        table_id=table_registry.id,
        batch_id=batch_id,
        status=ImportJobStatus.UPLOADED,
        total_files=len(files),
    )
    actor_api_key_id = getattr(getattr(request, "state", None), "auth_api_key_id", None)
    actor_api_key_label = getattr(
        getattr(request, "state", None), "auth_api_key_label", None
    )
    if actor_api_key_id:
        job.actor_api_key_id = actor_api_key_id
        job.actor_label_snapshot = actor_api_key_label
        job.last_status_actor_api_key_id = actor_api_key_id
        job.last_status_actor_label_snapshot = actor_api_key_label
    job.last_status_changed_at = datetime.now(UTC)
    job.last_status_actor_kind = "user"
    db.add(job)

    # 3. Process Files
    upload_dir = Path(settings.upload_temp_dir) / str(job_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        for file in files:
            # Calculate Hash & Save
            file_path = upload_dir / file.filename

            sha256_hash = hashlib.sha256()
            file_size = 0

            # Write to disk and hash
            with open(file_path, "wb") as buffer:
                while content := await file.read(1024 * 1024):  # 1MB chunks
                    sha256_hash.update(content)
                    buffer.write(content)
                    file_size += len(content)

            file_hash = sha256_hash.hexdigest()

            # Check for duplicates (L2-3)
            dup_stmt = (
                select(ImportFile, ImportJob)
                .join(ImportJob, ImportJob.id == ImportFile.job_id)
                .where(
                    ImportFile.tenant_id == current_tenant.id,
                    ImportFile.table_id == table_registry.id,
                    ImportFile.file_hash == file_hash,
                )
                .order_by(ImportFile.created_at.desc())
                .limit(1)
            )
            dup_result = await db.execute(dup_stmt)
            dup_row = dup_result.first()
            if (not allow_duplicate) and dup_row:
                dup_file, dup_job = dup_row
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "detail": "File content is duplicate (same SHA-256).",
                        "filename": file.filename,
                        "file_hash": file_hash,
                        "duplicate_of": {
                            "job_id": str(dup_job.id),
                            "batch_id": dup_job.batch_id,
                            "uploaded_filename": dup_file.filename,
                        },
                        "hint": "If you intended to re-import, create a NEW job with allow_duplicate=true (or change file content).",
                        "error_code": "DUPLICATE_FILE_CONTENT",
                    },
                )

            # Create ImportFile record
            import_file = ImportFile(
                job_id=job_id,
                tenant_id=current_tenant.id,
                table_id=table_registry.id,
                filename=file.filename,
                file_hash=file_hash,
                storage_path=str(file_path),
                file_size=file_size,
            )
            db.add(import_file)
    except Exception as e:
        # Cleanup uploaded files
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        raise e

    await db.commit()
    await db.refresh(job)

    # Semantic audit event (best-effort).
    actor_api_key_id = getattr(getattr(request, "state", None), "auth_api_key_id", None)
    actor_api_key_label = getattr(
        getattr(request, "state", None), "auth_api_key_label", None
    )
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    await write_audit_event_best_effort(
        tenant_id=current_tenant.id,
        actor_api_key_id=actor_api_key_id,
        actor_label_snapshot=actor_api_key_label,
        request_id=str(request_id) if request_id else None,
        method=request.method,
        path=request.url.path,
        status_code=status.HTTP_201_CREATED,
        action="import.job.create",
        metadata={
            "job_id": str(job.id),
            "batch_id": job.batch_id,
            "table_code": table_code,
            "total_files": len(files),
            "allow_duplicate": bool(allow_duplicate),
        },
        client_host=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    # Eager load files for response
    # In async sqlalchemy, relationships are lazy by default.
    # We might need to select with options or rely on implicit loading if session is open (but await is needed)
    # For simplicity, let's re-fetch with files

    stmt = (
        select(ImportJob)
        .where(ImportJob.id == job_id)
        .execution_options(populate_existing=True)
    )
    # We rely on lazy loading working if we access it before session close,
    # but with async it's tricky. Better to use selectinload.

    from sqlalchemy.orm import selectinload

    stmt = (
        select(ImportJob)
        .options(selectinload(ImportJob.files))
        .where(ImportJob.id == job_id)
    )
    result = await db.execute(stmt)
    job = result.scalar_one()

    # Trigger background processing (only if global session factory is available).
    # In tests we often override `get_db` without initializing the global factory.
    if database.async_session_factory:
        # Background work is attributed to system (it is executed by the service).
        background_tasks.add_task(process_import_job_background, job.id)
    else:
        # Avoid noisy errors in testing; callers can invoke service methods directly.
        if settings.environment.lower() != "testing":
            logger.warning(
                "Skip background processing: async_session_factory not initialized"
            )

    return job


@router.post(
    "/jobs/from-upload-job",
    response_model=ImportJobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_import_job_from_upload_job(
    payload: ImportJobFromUploadJobRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Create a v2 ImportJob from an existing UploadJob.

    This supports the PDF→CSV→UploadJob(edit)→v2 validate/commit workflow.
    We reuse the existing v2 import pipeline by writing the UploadJob's CSV bytes
    to the v2 temp upload directory and creating a single-file ImportJob.
    """

    # 1) Fetch UploadJob
    result = await db.execute(
        select(UploadJob).where(
            UploadJob.process_id == payload.upload_process_id,
            UploadJob.tenant_id == current_tenant.id,
        )
    )
    upload_job = result.scalar_one_or_none()
    if not upload_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload job not found"
        )
    if not upload_job.file_content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload job file_content is empty",
        )

    # 2) Determine table_code
    table_code = (
        payload.table_code or ""
    ).strip().upper() or _infer_table_code_from_filename(upload_job.filename)
    if not table_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_code is required (cannot infer from filename)",
        )

    # 3) Validate TableRegistry
    result = await db.execute(
        select(TableRegistry).where(TableRegistry.table_code == table_code)
    )
    table_registry = result.scalar_one_or_none()
    if not table_registry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid table code: {table_code}",
        )

    # 4) Create ImportJob + ImportFile
    job_id = uuid.uuid4()
    batch_id = f"{datetime.now().strftime('%Y%m%d')}-{str(job_id)[:8]}"

    actor_api_key_id = getattr(getattr(request, "state", None), "auth_api_key_id", None)
    actor_api_key_label = getattr(
        getattr(request, "state", None), "auth_api_key_label", None
    )

    job = ImportJob(
        id=job_id,
        tenant_id=current_tenant.id,
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

    upload_dir = Path(settings.upload_temp_dir) / str(job_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    try:
        filename = Path(upload_job.filename).name
        file_path = upload_dir / filename
        content = bytes(upload_job.file_content)
        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)
        file_path.write_bytes(content)

        dup_stmt = select(ImportFile).where(
            ImportFile.tenant_id == current_tenant.id,
            ImportFile.table_id == table_registry.id,
            ImportFile.file_hash == file_hash,
        )
        dup_result = await db.execute(dup_stmt)
        if (not payload.allow_duplicate) and dup_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate file detected: {filename}",
            )

        import_file = ImportFile(
            job_id=job_id,
            tenant_id=current_tenant.id,
            table_id=table_registry.id,
            filename=filename,
            file_hash=file_hash,
            storage_path=str(file_path),
            file_size=file_size,
        )
        db.add(import_file)
    except Exception:
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        raise

    await db.commit()

    request_id = getattr(getattr(request, "state", None), "request_id", None)
    await write_audit_event_best_effort(
        tenant_id=current_tenant.id,
        actor_api_key_id=actor_api_key_id,
        actor_label_snapshot=actor_api_key_label,
        request_id=str(request_id) if request_id else None,
        method=request.method,
        path=request.url.path,
        status_code=status.HTTP_201_CREATED,
        action="import.job.create.from_upload_job",
        metadata={
            "job_id": str(job.id),
            "batch_id": job.batch_id,
            "table_code": table_code,
            "upload_process_id": str(upload_job.process_id),
            "allow_duplicate": bool(payload.allow_duplicate),
        },
        client_host=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    from sqlalchemy.orm import selectinload

    stmt = (
        select(ImportJob)
        .options(selectinload(ImportJob.files))
        .where(ImportJob.id == job_id)
    )
    job = (await db.execute(stmt)).scalar_one()

    if database.async_session_factory:
        background_tasks.add_task(process_import_job_background, job.id)
    else:
        if settings.environment.lower() != "testing":
            logger.warning(
                "Skip background processing: async_session_factory not initialized"
            )

    return job


@router.get("/jobs/{job_id}", response_model=ImportJobRead)
async def get_import_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """
    Get import job status and details.
    """
    from sqlalchemy.orm import selectinload

    stmt = (
        select(ImportJob)
        .options(selectinload(ImportJob.files))
        .where(ImportJob.id == job_id, ImportJob.tenant_id == current_tenant.id)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
        )

    return job


@router.get("/jobs/{job_id}/errors", response_model=list[ImportJobErrorRow])
async def get_import_job_errors(
    job_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """
    Get validation errors for an import job.
    """
    # Verify job ownership
    stmt = select(ImportJob).where(
        ImportJob.id == job_id, ImportJob.tenant_id == current_tenant.id
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
        )

    # Query errors
    offset = (page - 1) * page_size
    stmt = (
        select(StagingRow)
        .where(StagingRow.job_id == job_id, StagingRow.is_valid == False)
        .order_by(StagingRow.row_index)
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return rows


@router.post("/jobs/{job_id}/commit", response_model=ImportJobRead)
async def commit_import_job(
    job_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """
    Commit a READY import job to target tables.
    """
    stmt = select(ImportJob).where(
        ImportJob.id == job_id, ImportJob.tenant_id == current_tenant.id
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
        )

    if job.status not in (ImportJobStatus.READY, ImportJobStatus.COMMITTING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not ready to commit (status: {job.status})",
        )

    # Update status to COMMITTING immediately to prevent double clicks.
    # If job is already COMMITTING (e.g., background task crashed/restarted), allow re-trigger.
    if job.status != ImportJobStatus.COMMITTING:
        job.status = ImportJobStatus.COMMITTING
        actor_api_key_id = getattr(
            getattr(request, "state", None), "auth_api_key_id", None
        )
        actor_api_key_label = getattr(
            getattr(request, "state", None), "auth_api_key_label", None
        )
        if actor_api_key_id:
            job.actor_api_key_id = actor_api_key_id
            job.actor_label_snapshot = actor_api_key_label
            job.last_status_actor_api_key_id = actor_api_key_id
            job.last_status_actor_label_snapshot = actor_api_key_label
        job.last_status_changed_at = datetime.now(UTC)
        job.last_status_actor_kind = "user"
        await db.commit()
        await db.refresh(job)

        request_id = getattr(getattr(request, "state", None), "request_id", None)
        await write_audit_event_best_effort(
            tenant_id=current_tenant.id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_api_key_label,
            request_id=str(request_id) if request_id else None,
            method=request.method,
            path=request.url.path,
            status_code=status.HTTP_200_OK,
            action="import.job.commit.requested",
            metadata={
                "job_id": str(job.id),
            },
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    # In tests we need deterministic behavior; commit synchronously.
    if settings.environment.lower() == "testing":
        service = ImportService(db)
        actor_api_key_id = getattr(
            getattr(request, "state", None), "auth_api_key_id", None
        )
        actor_api_key_label = getattr(
            getattr(request, "state", None), "auth_api_key_label", None
        )
        await service.commit_job(
            job.id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_api_key_label,
            actor_kind="user",
        )
    else:
        # Trigger background commit
        background_tasks.add_task(process_commit_job_background, job.id)

    # Re-fetch with files for response schema
    from sqlalchemy.orm import selectinload

    stmt = (
        select(ImportJob)
        .options(selectinload(ImportJob.files))
        .where(ImportJob.id == job_id)
    )
    result = await db.execute(stmt)
    job = result.scalar_one()

    return job


@router.post("/jobs/{job_id}/cancel", response_model=ImportJobRead)
async def cancel_import_job(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """Cancel an import job (idempotent)."""
    stmt = select(ImportJob).where(
        ImportJob.id == job_id,
        ImportJob.tenant_id == current_tenant.id,
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found",
        )

    if job.status != ImportJobStatus.CANCELLED:
        job.status = ImportJobStatus.CANCELLED
        actor_api_key_id = getattr(
            getattr(request, "state", None), "auth_api_key_id", None
        )
        actor_api_key_label = getattr(
            getattr(request, "state", None), "auth_api_key_label", None
        )
        if actor_api_key_id:
            job.actor_api_key_id = actor_api_key_id
            job.actor_label_snapshot = actor_api_key_label
            job.last_status_actor_api_key_id = actor_api_key_id
            job.last_status_actor_label_snapshot = actor_api_key_label
        job.last_status_changed_at = datetime.now(UTC)
        job.last_status_actor_kind = "user"
        await db.commit()

        request_id = getattr(getattr(request, "state", None), "request_id", None)
        await write_audit_event_best_effort(
            tenant_id=current_tenant.id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_api_key_label,
            request_id=str(request_id) if request_id else None,
            method=request.method,
            path=request.url.path,
            status_code=status.HTTP_200_OK,
            action="import.job.cancelled",
            metadata={
                "job_id": str(job.id),
            },
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    from sqlalchemy.orm import selectinload

    stmt = (
        select(ImportJob)
        .options(selectinload(ImportJob.files))
        .where(ImportJob.id == job_id)
    )
    result = await db.execute(stmt)
    job = result.scalar_one()
    return job


async def process_commit_job_background(
    job_id: uuid.UUID,
    *,
    actor_api_key_id: uuid.UUID | None = None,
    actor_label_snapshot: str | None = None,
    actor_kind: str = "system",
):
    """
    Background task to commit import job.
    """
    if not database.async_session_factory:
        logger.error("Async session factory not initialized")
        await _mark_job_failed(job_id, "Async session factory not initialized")
        return

    async with database.async_session_factory() as db:
        service = ImportService(db)
        try:
            logger.info(f"Starting background commit for job {job_id}")
            await service.commit_job(
                job_id,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )
            logger.info(f"Completed background commit for job {job_id}")
        except Exception as e:
            logger.exception(f"Background commit failed for job {job_id}: {e}")
            await _mark_job_failed(job_id, e)
