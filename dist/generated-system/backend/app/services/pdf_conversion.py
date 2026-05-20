from __future__ import annotations

import asyncio
import base64
import csv
import io
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from app.core import database
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.pdf_conversion_job import PdfConversionJob, PdfConversionStatus
from app.models.pdf_upload import PdfUpload
from app.models.upload_job import JobStatus, UploadJob
from app.services.validation import ValidationError

logger = get_logger(__name__)


MAX_CSV_BYTES = 10 * 1024 * 1024

# Concurrency limiter: prevent overwhelming the external PDF server
# when multiple conversion jobs run in parallel (BackgroundTasks are concurrent).
_pdf_convert_semaphore: asyncio.Semaphore | None = None


def _get_pdf_convert_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (must be created inside a running event loop)."""
    global _pdf_convert_semaphore
    if _pdf_convert_semaphore is None:
        max_concurrent = int(getattr(get_settings(), "pdf_server_max_concurrent", 3))
        _pdf_convert_semaphore = asyncio.Semaphore(max_concurrent)
    return _pdf_convert_semaphore


class PdfServerNotConfigured(RuntimeError):
    pass


def _infer_table_from_filename(filename: str) -> str | None:
    name = (Path(filename).name or "").strip().upper()
    if not name:
        return None

    # Common naming patterns like: P1_XXXX.pdf / P2-XXXX.pdf / P3 XXXX.pdf
    m = re.match(r"^(P[123])([_\-\s].*)?$", name)
    if m:
        return m.group(1)
    m = re.match(r"^(P[123])", name)
    if m:
        return m.group(1)
    return None


def _to_error_summary(error: Exception | str, *, stage: str) -> dict[str, Any]:
    if isinstance(error, Exception):
        msg = str(error).strip()
        if not msg:
            msg = type(error).__name__
        else:
            msg = f"{type(error).__name__}: {msg}"
        return {
            "stage": stage,
            "error": msg,
        }

    msg = str(error).strip()
    return {
        "stage": stage,
        "error": msg,
    }


async def _call_pdf_server_convert(
    *,
    pdf_bytes: bytes,
    filename: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    url = (getattr(settings, "pdf_server_url", None) or "").strip()
    if not url:
        raise PdfServerNotConfigured("PDF_SERVER_URL is not configured")
    # Append /process if the URL doesn't already end with a path segment
    if url.rstrip("/").count("/") <= 2:
        # e.g., "http://host:port" -> "http://host:port/process"
        url = url.rstrip("/") + "/process"

    timeout_seconds = int(getattr(settings, "pdf_server_timeout_seconds", 1800))
    # Use granular timeout: short connect (30s), long read/write for large PDFs
    timeout = httpx.Timeout(
        connect=30.0,
        read=float(timeout_seconds),
        write=60.0,
        pool=30.0,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        if url.rstrip("/").lower().endswith("/process"):
            # Legacy/LLM Table Processor style: /process expects multipart fields:
            # - table: required (P1/P2/P3)
            # - files: array of PDF files
            table = None
            if options and isinstance(options.get("table"), str):
                table = options["table"].strip()
            if not table:
                table = _infer_table_from_filename(filename)
            if not table:
                table = (getattr(settings, "pdf_server_table", None) or "").strip()
            if not table:
                raise PdfServerNotConfigured(
                    "PDF server /process requires a table (P1/P2/P3). "
                    "Set PDF_SERVER_TABLE or upload a PDF filename starting with P1/P2/P3."
                )

            data: dict[str, Any] = {"table": table}
            if options:
                if (
                    isinstance(options.get("llm_url"), str)
                    and options["llm_url"].strip()
                ):
                    data["llm_url"] = options["llm_url"].strip()
                if options.get("llm_timeout") is not None:
                    data["llm_timeout"] = str(options["llm_timeout"])

            files = [("files", (filename, pdf_bytes, "application/pdf"))]
            resp = await client.post(url, files=files, data=data)
        else:
            # Default style: /convert expects multipart field "file".
            files = {"file": (filename, pdf_bytes, "application/pdf")}
            data = {}
            if options:
                # Send options as JSON string field to be flexible.
                import json

                data["options"] = json.dumps(options, ensure_ascii=False)
            resp = await client.post(url, files=files, data=data)
        resp.raise_for_status()

        content_type = (resp.headers.get("content-type") or "").lower()
        if "application/json" in content_type or content_type.endswith("+json"):
            return resp.json()

        # Some PDF servers may return a ZIP file directly.
        return {
            "_raw_bytes": resp.content,
            "_content_type": content_type,
        }


def _extract_csv_text(result: dict[str, Any]) -> str:
    if isinstance(result.get("csv_text"), str) and result["csv_text"].strip():
        return result["csv_text"]
    if isinstance(result.get("csv"), str) and result["csv"].strip():
        return result["csv"]

    b64 = result.get("csv_base64")
    if isinstance(b64, str) and b64.strip():
        return base64.b64decode(b64).decode("utf-8", errors="replace")

    raise ValueError("PDF server response does not contain csv_text/csv/csv_base64")


def _extract_csv_texts_from_zip_bytes(zip_bytes: bytes) -> dict[str, str]:
    if not zip_bytes:
        raise ValueError("ZIP content is empty")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as e:
        raise ValueError(f"Invalid ZIP content: {e}")

    csvs: dict[str, str] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue

        # Prevent path traversal; keep only the base name.
        name = (Path(info.filename).name or "").strip()
        if not name:
            continue
        if not name.lower().endswith(".csv"):
            continue

        data = zf.read(info)
        # Prefer utf-8-sig to gracefully handle BOM.
        text = data.decode("utf-8-sig", errors="replace")
        csvs[name] = text

    if not csvs:
        raise ValueError("ZIP does not contain any CSV files")

    return csvs


def _select_csv_name_for_pdf(csvs: dict[str, str], pdf_filename: str) -> str:
    if not csvs:
        raise ValueError("No CSV candidates")
    if len(csvs) == 1:
        return next(iter(csvs.keys()))

    stem = (Path(pdf_filename).stem or "").strip()
    if stem:
        # Prefer exact match: <stem>.csv (case-insensitive)
        exact = f"{stem}.csv".lower()
        for name in csvs.keys():
            if name.lower() == exact:
                return name

        # Fallback: contains stem
        stem_lower = stem.lower()
        contains = [name for name in csvs.keys() if stem_lower in name.lower()]
        if len(contains) == 1:
            return contains[0]

    raise ValueError(
        f"ZIP contains multiple CSV files; cannot decide which one matches PDF '{pdf_filename}'. "
        f"Candidates: {sorted(csvs.keys())}"
    )


def _extract_csv_texts(
    result: dict[str, Any], *, pdf_filename: str
) -> tuple[dict[str, str], str]:
    """Return (all_csvs, selected_name).

    Supports:
    - JSON with csv_text/csv/csv_base64 (single)
    - JSON with zip_base64
    - Raw bytes response stored in result['_raw_bytes'] (zip)
    """
    # Raw bytes path (non-JSON response)
    raw = result.get("_raw_bytes")
    if isinstance(raw, (bytes, bytearray)) and raw:
        csvs = _extract_csv_texts_from_zip_bytes(bytes(raw))
        try:
            selected = _select_csv_name_for_pdf(csvs, pdf_filename)
        except ValueError:
            selected = sorted(csvs.keys())[0]
        return csvs, selected

    # JSON zip base64 path
    zip_b64 = result.get("zip_base64")
    if isinstance(zip_b64, str) and zip_b64.strip():
        zip_bytes = base64.b64decode(zip_b64)
        csvs = _extract_csv_texts_from_zip_bytes(zip_bytes)
        try:
            selected = _select_csv_name_for_pdf(csvs, pdf_filename)
        except ValueError:
            selected = sorted(csvs.keys())[0]
        return csvs, selected

    # JSON single-csv path
    csv_text = _extract_csv_text(result)
    name = f"{Path(pdf_filename).stem or 'output'}.csv"
    return {name: csv_text}, name


def _inject_winder_into_csv(content: bytes) -> bytes:
    """P2 CSV 固定 20 筆，依列順序注入 Winder number 1–20。

    第 1 列 → Winder number = 1，第 2 列 → 2，…，第 20 列 → 20。
    若 CSV 已有 Winder number（或同義欄位）則跳過，避免覆蓋 PDF 轉出的原始值。
    """
    WINDER_KEY = "Winder number"
    WINDER_SYNONYMS = {"Winder", "Winder number", "winder", "winder_number", "收卷機", "收卷機編號"}

    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return content

    # Skip injection if any winder-like column already exists
    if any(f in WINDER_SYNONYMS for f in reader.fieldnames):
        return content

    # Insert before the "規格/format" column if present; otherwise prepend.
    SPEC_SYNONYMS = {"format", "Format", "規格", "specification", "Specification"}
    existing = list(reader.fieldnames)
    insert_idx = next(
        (i for i, f in enumerate(existing) if f in SPEC_SYNONYMS), 0
    )
    fieldnames = existing[:insert_idx] + [WINDER_KEY] + existing[insert_idx:]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row_idx, row in enumerate(reader):
        row[WINDER_KEY] = str(row_idx + 1)  # 第 1 列 → 1, 第 2 列 → 2, …
        writer.writerow(row)
    return out.getvalue().encode("utf-8")


async def _auto_ingest_converted_csvs(
    *,
    db,
    conversion_job: PdfConversionJob,
    output_paths: list[str],
    base_dir: Path,
) -> None:
    """Create UploadJob(s) from converted CSV files (WITHOUT validation).

    Background conversion output often contains errors that users need to fix first.
    Therefore we only create UploadJobs and leave them in PENDING status.

    This runs server-side (background), so it must NOT depend on any HTTP request context.
    """

    existing = getattr(conversion_job, "ingested_upload_jobs", None) or []
    if existing:
        return

    tenant_id = conversion_job.tenant_id
    actor_api_key_id = conversion_job.actor_api_key_id
    actor_api_key_label = conversion_job.actor_label_snapshot

    created: list[dict[str, str]] = []

    for p in output_paths:
        csv_path = Path(str(p)).resolve()
        if base_dir not in csv_path.parents and csv_path != base_dir:
            raise ValueError("Illegal CSV output path")
        if not csv_path.exists() or not csv_path.is_file():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        filename = csv_path.name

        # Some converters emit auxiliary files like error_list.csv which may be empty.
        if filename.strip().lower() == "error_list.csv":
            continue

        file_content = csv_path.read_bytes()
        if not file_content:
            # Skip empty outputs rather than failing the whole background auto-ingest.
            continue

        # Inject sequential Winder number (1–20) only for P2 CSVs.
        table_type = _infer_table_from_filename(filename)
        if table_type == "P2":
            injected = _inject_winder_into_csv(file_content)
            if injected is not file_content:
                # Write back to disk so the outputs endpoint also returns injected content.
                csv_path.write_bytes(injected)
                file_content = injected

        if len(file_content) > MAX_CSV_BYTES:
            raise ValidationError(message=f"CSV 檔案大小超過 10MB：{csv_path.name}")

        upload_job = UploadJob(
            filename=filename,
            status=JobStatus.PENDING,
            file_content=file_content,
            tenant_id=tenant_id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_api_key_label,
            last_status_changed_at=datetime.now(UTC),
            last_status_actor_kind="system",
            last_status_actor_api_key_id=actor_api_key_id,
            last_status_actor_label_snapshot=actor_api_key_label,
        )
        db.add(upload_job)
        await db.commit()
        await db.refresh(upload_job)

        created.append({"filename": filename, "process_id": str(upload_job.process_id)})

    conversion_job.ingested_upload_jobs = created
    await db.commit()


async def process_pdf_conversion_job_background(job_id: uuid.UUID) -> None:
    if not database.async_session_factory:
        logger.error(
            "Async session factory not initialized; cannot process pdf conversion job",
            job_id=str(job_id),
        )
        return

    settings = get_settings()

    # ------------------------------------------------------------------
    # Phase 1: load job + upload metadata, update status → PROCESSING,
    #          then RELEASE the DB session so the pool stays available
    #          for other requests while the external call runs.
    # ------------------------------------------------------------------
    process_id: uuid.UUID | None = None
    pdf_path_str: str | None = None
    upload_filename: str | None = None

    async with database.async_session_factory() as db:
        stmt = select(PdfConversionJob).where(PdfConversionJob.id == job_id)
        job = (await db.execute(stmt)).scalar_one_or_none()
        if not job:
            return

        process_id = job.process_id

        upload = (
            await db.execute(
                select(PdfUpload).where(PdfUpload.process_id == job.process_id)
            )
        ).scalar_one_or_none()
        if not upload:
            job.status = PdfConversionStatus.FAILED
            job.progress = 100
            job.error_summary = _to_error_summary(
                "PDF upload record not found", stage="load_upload"
            )
            job.finished_at = datetime.now(UTC)
            await db.commit()
            return

        pdf_path_str = upload.storage_path
        upload_filename = upload.filename

        job.status = PdfConversionStatus.UPLOADING
        job.progress = 15
        job.started_at = datetime.now(UTC)
        await db.commit()
    # --- DB session released here ---

    # ------------------------------------------------------------------
    # Phase 2: read PDF bytes and call external server (may take minutes).
    #          No DB session is held during this phase.
    # ------------------------------------------------------------------
    result: dict[str, Any] | None = None
    convert_error: Exception | None = None
    convert_error_stage: str = "convert"

    try:
        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        pdf_bytes = pdf_path.read_bytes()

        # Update status → PROCESSING (short DB touch)
        async with database.async_session_factory() as db:
            job = (await db.execute(
                select(PdfConversionJob).where(PdfConversionJob.id == job_id)
            )).scalar_one()
            job.status = PdfConversionStatus.PROCESSING
            job.progress = 45
            await db.commit()

        # Call external server (with concurrency limiter)
        sem = _get_pdf_convert_semaphore()
        async with sem:
            logger.info(
                "Calling PDF server for conversion",
                job_id=str(job_id),
                filename=upload_filename,
            )
            result = await _call_pdf_server_convert(
                pdf_bytes=pdf_bytes,
                filename=upload_filename or "upload.pdf",
                options={
                    "output_format": "csv",
                },
            )

    except PdfServerNotConfigured as e:
        convert_error = e
        convert_error_stage = "config"
    except Exception as e:
        logger.exception(
            "PDF conversion job failed",
            job_id=str(job_id),
            process_id=str(process_id),
        )
        convert_error = e
        convert_error_stage = "convert"

    # ------------------------------------------------------------------
    # Phase 3: write results back to DB (fresh session).
    # ------------------------------------------------------------------
    async with database.async_session_factory() as db:
        job = (await db.execute(
            select(PdfConversionJob).where(PdfConversionJob.id == job_id)
        )).scalar_one()

        if convert_error is not None:
            job.status = PdfConversionStatus.FAILED
            job.progress = 100
            job.error_summary = _to_error_summary(convert_error, stage=convert_error_stage)
            job.finished_at = datetime.now(UTC)
            await db.commit()
            return

        try:
            job.progress = 70
            await db.commit()

            csvs, selected_name = _extract_csv_texts(
                result, pdf_filename=upload_filename or "upload.pdf"
            )

            out_dir = Path(settings.upload_temp_dir) / "pdf" / str(process_id)
            out_dir.mkdir(parents=True, exist_ok=True)

            output_paths: list[str] = []
            selected_path: str | None = None
            for name, text in csvs.items():
                safe_name = (Path(name).name or "output.csv").strip() or "output.csv"
                out_path = out_dir / safe_name
                out_path.write_text(text, encoding="utf-8")
                output_paths.append(str(out_path))
                if name == selected_name:
                    selected_path = str(out_path)

            if not selected_path:
                selected_path = output_paths[0]

            job.status = PdfConversionStatus.COMPLETED
            job.progress = 100
            job.output_path = selected_path
            job.output_paths = output_paths
            job.finished_at = datetime.now(UTC)
            job.error_summary = None
            await db.commit()

            # Auto-ingest converted CSVs into existing validation flow.
            try:
                resolved_base = Path(settings.upload_temp_dir).resolve()
                await _auto_ingest_converted_csvs(
                    db=db,
                    conversion_job=job,
                    output_paths=output_paths,
                    base_dir=resolved_base,
                )
            except Exception as e:
                logger.exception(
                    "Auto-ingest converted CSVs failed",
                    job_id=str(job.id),
                    process_id=str(job.process_id),
                    error=str(e),
                )

        except Exception as e:
            logger.exception(
                "PDF conversion post-processing failed",
                job_id=str(job_id),
                process_id=str(process_id),
            )
            job.status = PdfConversionStatus.FAILED
            job.progress = 100
            job.error_summary = _to_error_summary(e, stage="convert")
            job.finished_at = datetime.now(UTC)
            await db.commit()
