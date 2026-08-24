from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.core.db_capabilities import DB_CAPABILITIES
from app.models.core.tenant import Tenant

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

MAX_RANGE_DAYS = 366
EXPORT_LIMIT = 5000
NUMERIC_TYPES = {"integer", "decimal", "float", "number"}


def _date_range(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    try:
        end = date.fromisoformat(date_to) if date_to else date.today()
        start = date.fromisoformat(date_from) if date_from else end - timedelta(days=29)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dates must use YYYY-MM-DD") from exc
    if start > end:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail="Date range must not exceed 366 days")
    return start.isoformat(), end.isoformat()


def _optional_dates(date_from: str | None, date_to: str | None) -> tuple[str | None, str | None]:
    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dates must use YYYY-MM-DD") from exc
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    return start.isoformat() if start else None, end.isoformat() if end else None


def _bucket_start(value: str, granularity: str) -> str:
    current = date.fromisoformat(value)
    if granularity == "week":
        current -= timedelta(days=current.isoweekday() - 1)
    elif granularity == "month":
        current = current.replace(day=1)
    return current.isoformat()


def _rebucket(daily: list[dict[str, Any]], granularity: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in daily:
        key = _bucket_start(item["bucket_start"], granularity)
        bucket = grouped.setdefault(
            key,
            {"bucket_start": key, "count": 0, "sum": None, "avg": None, "value_count": 0},
        )
        bucket["count"] += item["count"]
        if item.get("sum") is not None:
            bucket["sum"] = (bucket["sum"] or 0.0) + item["sum"]
            bucket["value_count"] += item.get("value_count", 0)
    result = []
    for bucket in grouped.values():
        value_count = bucket.pop("value_count")
        bucket["avg"] = bucket["sum"] / value_count if value_count else None
        result.append(bucket)
    return result


def _number_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


@router.get("/trend")
async def trend(
    code: str,
    field: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    granularity: Literal["day", "week", "month"] = "day",
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    date_from, date_to = _date_range(date_from, date_to)
    forms = await DB_CAPABILITIES["db.forms.list"](db=db, tenant_id=tenant.id)
    form = next((item for item in forms if item.get("code") == code), None)
    if not form:
        raise HTTPException(status_code=404, detail=f"Form '{code}' not found")
    if field:
        field_def = next(
            (item for item in (form.get("fields") or []) if (item.get("fieldKey") or item.get("name")) == field),
            None,
        )
        if not field_def or str(field_def.get("type", "")).lower() not in NUMERIC_TYPES:
            raise HTTPException(status_code=422, detail="field must reference a numeric field")

    counts = await DB_CAPABILITIES["db.records.trend"](
        db=db,
        tenant_id=tenant.id,
        station_code=code,
        date_from=date_from,
        date_to=date_to,
    )
    daily = [
        {
            "bucket_start": item["bucket_date"],
            "count": item["count"],
            "sum": None,
            "avg": None,
            "value_count": 0,
        }
        for item in counts
    ]
    if field:
        by_date = {item["bucket_start"]: item for item in daily}
        records = await DB_CAPABILITIES["db.records.search"](
            db=db,
            tenant_id=tenant.id,
            station_id=form["id"],
            date_from=date_from,
            date_to=date_to,
            limit=5000,
        )
        for record in records:
            value = _number_value((record.get("data") or {}).get(field))
            created_at = record.get("created_at")
            if value is None or not created_at:
                continue
            key = datetime.fromisoformat(created_at).date().isoformat()
            bucket = by_date.get(key)
            if not bucket:
                continue
            bucket["sum"] = (bucket["sum"] or 0.0) + value
            bucket["value_count"] += 1
        for bucket in daily:
            bucket["avg"] = bucket["sum"] / bucket["value_count"] if bucket["value_count"] else None

    buckets = daily if granularity == "day" else _rebucket(daily, granularity)
    for bucket in buckets:
        bucket.pop("value_count", None)
    return {"granularity": granularity, "field": field, "buckets": buckets}


UploadJobStatus = Literal["PENDING", "VALIDATED", "IMPORTED"]


@router.get("/upload-history")
async def upload_history(
    date_from: str | None = None,
    date_to: str | None = None,
    status: UploadJobStatus | None = None,
    page: int = 1,
    page_size: int = 50,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    date_from, date_to = _optional_dates(date_from, date_to)
    return await DB_CAPABILITIES["db.upload.jobs.list"](
        db=db,
        tenant_id=tenant.id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/upload-history/export")
async def export_upload_history(
    date_from: str | None = None,
    date_to: str | None = None,
    status: UploadJobStatus | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    date_from, date_to = _optional_dates(date_from, date_to)
    result = await DB_CAPABILITIES["db.upload.jobs.list"](
        db=db,
        tenant_id=tenant.id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        page=1,
        page_size=EXPORT_LIMIT,
    )
    if result["total"] > EXPORT_LIMIT:
        raise HTTPException(status_code=422, detail="Too many rows to export; narrow the filters")

    output = io.StringIO(newline="")
    columns = [
        "created_at",
        "process_id",
        "filename",
        "status",
        "total_rows",
        "valid_rows",
        "invalid_rows",
        "actor",
    ]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(result["items"])
    content = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="upload-history.csv"'},
    )
