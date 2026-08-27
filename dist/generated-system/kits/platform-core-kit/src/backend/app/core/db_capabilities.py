from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_forms(db: AsyncSession, tenant_id: Any | None = None, **_: Any) -> list[dict[str, Any]]:
    try:
        from app.models.station import Station, StationSchema
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="forms DB capability is not installed") from exc

    stmt = select(Station).order_by(Station.sort_order, Station.code)
    if tenant_id is not None and hasattr(Station, "tenant_id"):
        stmt = stmt.where(Station.tenant_id == tenant_id)
    stations = (await db.execute(stmt)).scalars().all()
    result: list[dict[str, Any]] = []
    for station in stations:
        schema = (
            await db.execute(
                select(StationSchema)
                .where(StationSchema.station_id == station.id, StationSchema.is_active == True)
                .order_by(StationSchema.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        result.append(
            {
                "id": str(station.id),
                "code": station.code,
                "name": station.name,
                "sort_order": station.sort_order,
                "schema_version": schema.version if schema else None,
                "fields": schema.record_fields if schema else None,
            }
        )
    return result


async def resolve_table(db: AsyncSession, table_code: str | None = None, **_: Any) -> dict[str, Any] | None:
    if not table_code:
        raise HTTPException(status_code=422, detail="table_code is required")
    try:
        from app.models.core.schema_registry import SchemaVersion, TableRegistry
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="table registry DB capability is not installed") from exc

    table = (
        await db.execute(select(TableRegistry).where(TableRegistry.table_code == table_code))
    ).scalar_one_or_none()
    if not table:
        return None
    schema = (
        await db.execute(
            select(SchemaVersion)
            .where(SchemaVersion.table_id == table.id)
            .order_by(SchemaVersion.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "id": str(table.id),
        "table_code": table.table_code,
        "display_name": table.display_name,
        "schema": schema.schema_json if schema else None,
    }


async def search_records(
    db: AsyncSession,
    tenant_id: Any | None = None,
    station_id: str | None = None,
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    try:
        from app.models.generic_record import GenericRecord
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="generic record DB capability is not installed") from exc

    limit = int(limit)
    if not 1 <= limit <= 5000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 5000")
    stmt = select(GenericRecord).order_by(GenericRecord.created_at.desc())
    if tenant_id is not None:
        stmt = stmt.where(GenericRecord.tenant_id == tenant_id)
    if station_id:
        stmt = stmt.where(GenericRecord.station_id == station_id)
    if date_from:
        stmt = stmt.where(GenericRecord.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc))
    if date_to:
        stmt = stmt.where(
            GenericRecord.created_at
            < datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
        )
    records = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    if len(records) > limit:
        raise HTTPException(status_code=422, detail="Too many records; narrow the date range")
    return [
        {
            "id": str(record.id),
            "tenant_id": str(record.tenant_id),
            "station_id": str(record.station_id),
            "lot_no_raw": record.lot_no_raw,
            "data": record.data,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        for record in records
    ]


async def validate_edit_reason(
    db: AsyncSession,
    tenant_id: Any | None = None,
    reason_id: Any | None = None,
    **_: Any,
) -> dict[str, Any]:
    if tenant_id is None or reason_id is None:
        raise HTTPException(status_code=422, detail="tenant_id and reason_id are required")
    try:
        from app.models.core.edit_reason import EditReason
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="edit reason DB capability is not installed") from exc

    reason = (
        await db.execute(
            select(EditReason).where(
                EditReason.id == reason_id,
                EditReason.tenant_id == tenant_id,
                EditReason.is_active == True,
            )
        )
    ).scalar_one_or_none()
    if not reason:
        raise HTTPException(status_code=422, detail="reason_id must reference an active edit reason")
    return {"id": str(reason.id), "code": reason.code, "label": reason.label}


async def records_trend(
    db: AsyncSession,
    *,
    tenant_id: Any,
    station_code: str,
    date_from: str,
    date_to: str,
    **_: Any,
) -> list[dict[str, Any]]:
    try:
        from app.models.generic_record import GenericRecord
        from app.models.station import Station
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="record trend DB capability is not installed") from exc

    bucket_date = func.date(GenericRecord.created_at).label("bucket_date")
    rows = (
        await db.execute(
            select(bucket_date, func.count(GenericRecord.id))
            .join(Station, Station.id == GenericRecord.station_id)
            .where(
                GenericRecord.tenant_id == tenant_id,
                Station.code == station_code,
                GenericRecord.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc),
                GenericRecord.created_at
                < datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1),
            )
            .group_by(bucket_date)
            .order_by(bucket_date)
        )
    ).all()
    return [
        {"bucket_date": value.isoformat() if hasattr(value, "isoformat") else str(value), "count": count}
        for value, count in rows
    ]


def _upload_job_dict(job: Any) -> dict[str, Any]:
    return {
        "process_id": str(job.process_id),
        "filename": job.filename,
        "status": job.status,
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "actor": job.actor_label_snapshot,
    }


async def list_upload_jobs(
    db: AsyncSession,
    *,
    tenant_id: Any,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
    **_: Any,
) -> dict[str, Any]:
    # Consumes the existing baseline UploadJob/JobStatus model (upload-validation-kit's
    # own /api/upload flow) — this capability is read-only, no create/write counterpart.
    try:
        from app.models.upload_job import UploadJob
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="upload jobs DB capability is not installed") from exc

    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 5000)
    filters = [UploadJob.tenant_id == tenant_id]
    if status:
        filters.append(UploadJob.status == status)
    if date_from:
        filters.append(UploadJob.created_at >= datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc))
    if date_to:
        filters.append(
            UploadJob.created_at
            < datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
        )
    total = (await db.execute(select(func.count(UploadJob.id)).where(*filters))).scalar() or 0
    items = (
        await db.execute(
            select(UploadJob)
            .where(*filters)
            .order_by(UploadJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_upload_job_dict(job) for job in items]}


DB_CAPABILITIES = {
    "db.forms.list": list_forms,
    "db.tables.resolve": resolve_table,
    "db.records.search": search_records,
    "db.records.trend": records_trend,
    "db.edit-reasons.validate": validate_edit_reason,
    "db.upload.jobs.list": list_upload_jobs,
}
