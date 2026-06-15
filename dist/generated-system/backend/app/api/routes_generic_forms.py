"""Generic Forms API — schema-driven form types, record storage, and CSV upload."""
from __future__ import annotations

import io
import uuid
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.core.tenant import Tenant
from app.models.generic_record import GenericRecord
from app.models.station import Station, StationSchema

router = APIRouter(tags=["Generic Forms"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class FieldDef(BaseModel):
    name: str
    type: str = "string"   # string | integer | decimal | date | boolean
    label: str | None = None
    required: bool = False
    is_key: bool = False   # True → value used as lot_no_raw (record identifier)


class StationCreate(BaseModel):
    code: str
    name: str
    sort_order: int = 0


class SchemaIn(BaseModel):
    fields: list[FieldDef]


class StationRead(BaseModel):
    id: str
    code: str
    name: str
    sort_order: int
    schema_version: int | None = None
    fields: list[dict] | None = None


class UploadResult(BaseModel):
    total: int
    imported: int
    skipped: int
    errors: list[dict]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_station_read(station: Station, schema: StationSchema | None) -> StationRead:
    return StationRead(
        id=str(station.id),
        code=station.code,
        name=station.name,
        sort_order=station.sort_order,
        schema_version=schema.version if schema else None,
        fields=schema.record_fields if schema else None,
    )


def _coerce(value: Any, ftype: str) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    if ftype == "integer":
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return s
    if ftype == "decimal":
        try:
            return float(s)
        except (ValueError, TypeError):
            return s
    return s


def _lot_no_norm(raw: str) -> int:
    """Convert key string to sortable integer (0 if non-numeric)."""
    cleaned = "".join(c for c in raw if c.isdigit())
    try:
        v = int(cleaned[:18]) if cleaned else 0
        return min(v, 9_223_372_036_854_775_807)   # BigInteger max
    except (ValueError, OverflowError):
        return 0


async def _get_station(code: str, tenant_id: uuid.UUID, db: AsyncSession) -> Station:
    station = (
        await db.execute(
            select(Station).where(
                Station.tenant_id == tenant_id,
                Station.code == code.strip().upper(),
            )
        )
    ).scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail=f"Form '{code}' not found")
    return station


async def _active_schema(station_id: uuid.UUID, db: AsyncSession) -> StationSchema | None:
    return (
        await db.execute(
            select(StationSchema)
            .where(StationSchema.station_id == station_id, StationSchema.is_active == True)
            .order_by(StationSchema.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/forms", response_model=list[StationRead])
async def list_forms(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all form types for the current tenant."""
    stations = (
        await db.execute(
            select(Station)
            .where(Station.tenant_id == tenant.id)
            .order_by(Station.sort_order, Station.code)
        )
    ).scalars().all()

    result = []
    for st in stations:
        schema = await _active_schema(st.id, db)
        result.append(_to_station_read(st, schema))
    return result


@router.post("/forms", response_model=StationRead, status_code=status.HTTP_201_CREATED)
async def create_form(
    body: StationCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new form type (station)."""
    code = body.code.strip().upper()
    if not code:
        raise HTTPException(status_code=422, detail="code is required")

    existing = (
        await db.execute(
            select(Station).where(Station.tenant_id == tenant.id, Station.code == code)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Form code '{code}' already exists")

    station = Station(
        tenant_id=tenant.id,
        code=code,
        name=body.name.strip() or code,
        sort_order=body.sort_order,
        has_items=False,
    )
    db.add(station)
    await db.commit()
    await db.refresh(station)
    return _to_station_read(station, None)


@router.delete("/forms/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form(
    code: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a form type and all its records."""
    station = await _get_station(code, tenant.id, db)

    await db.execute(
        sql_delete(GenericRecord).where(
            GenericRecord.station_id == station.id,
            GenericRecord.tenant_id == tenant.id,
        )
    )
    await db.execute(
        sql_delete(StationSchema).where(StationSchema.station_id == station.id)
    )
    await db.execute(sql_delete(Station).where(Station.id == station.id))
    await db.commit()


@router.put("/forms/{code}/schema", response_model=StationRead)
async def set_schema(
    code: str,
    body: SchemaIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Set (or replace) the active schema for a form type."""
    station = await _get_station(code, tenant.id, db)

    old = (
        await db.execute(
            select(StationSchema).where(
                StationSchema.station_id == station.id, StationSchema.is_active == True
            )
        )
    ).scalars().all()
    for s in old:
        s.is_active = False

    max_ver = (
        await db.execute(
            select(func.max(StationSchema.version)).where(
                StationSchema.station_id == station.id
            )
        )
    ).scalar() or 0

    key_fields = [f.name for f in body.fields if f.is_key]
    field_dicts = [f.model_dump() for f in body.fields]

    schema = StationSchema(
        station_id=station.id,
        version=max_ver + 1,
        is_active=True,
        record_fields=field_dicts,
        item_fields=None,
        unique_key_fields=key_fields,
        csv_signature_columns=[f.name for f in body.fields],
        csv_filename_pattern=None,
        csv_field_mapping={f.name: f.name for f in body.fields},
    )
    db.add(schema)
    await db.commit()
    await db.refresh(schema)
    return _to_station_read(station, schema)


@router.get("/forms/{code}/records")
async def list_records(
    code: str,
    page: int = 1,
    page_size: int = 50,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List records for a form type (paginated)."""
    station = await _get_station(code, tenant.id, db)

    offset = max(0, (page - 1) * page_size)
    total = (
        await db.execute(
            select(func.count(GenericRecord.id)).where(
                GenericRecord.tenant_id == tenant.id,
                GenericRecord.station_id == station.id,
            )
        )
    ).scalar() or 0

    rows = (
        await db.execute(
            select(GenericRecord)
            .where(
                GenericRecord.tenant_id == tenant.id,
                GenericRecord.station_id == station.id,
            )
            .order_by(GenericRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "id": str(r.id),
                "lot_no_raw": r.lot_no_raw,
                "data": r.data,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/forms/{code}/upload", response_model=UploadResult)
async def upload_csv(
    code: str,
    file: UploadFile = File(...),
    allow_duplicate: bool = Form(False),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV and import rows using the form's active schema."""
    station = await _get_station(code, tenant.id, db)
    schema = await _active_schema(station.id, db)
    if not schema:
        raise HTTPException(
            status_code=422,
            detail="No schema defined. Use PUT /api/forms/{code}/schema first.",
        )

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", dtype=str)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot read CSV: {exc}")

    df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all")
    if df.empty:
        return UploadResult(total=0, imported=0, skipped=0, errors=[])

    fields: list[dict] = schema.record_fields or []
    key_fields = [f["name"] for f in fields if f.get("is_key")]

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for row_idx, row in enumerate(df.itertuples(index=False)):
        row_dict = row._asdict()
        row_data: dict[str, Any] = {}
        row_errors: list[str] = []

        for field in fields:
            fname = field["name"]
            ftype = field.get("type", "string")
            raw_val = row_dict.get(fname)
            coerced = _coerce(raw_val, ftype)

            if field.get("required") and coerced is None:
                row_errors.append(f"'{fname}' 為必填欄位")
            else:
                row_data[fname] = coerced

        if row_errors:
            errors.append({"row": row_idx + 1, "errors": row_errors})
            continue

        key_val = (
            "_".join(str(row_data.get(k) or "") for k in key_fields)
            if key_fields
            else str(uuid.uuid4())
        )
        if not key_val.strip("_"):
            key_val = str(uuid.uuid4())

        if not allow_duplicate:
            exists = (
                await db.execute(
                    select(GenericRecord.id).where(
                        GenericRecord.tenant_id == tenant.id,
                        GenericRecord.station_id == station.id,
                        GenericRecord.lot_no_raw == key_val[:50],
                    )
                )
            ).scalar_one_or_none()
            if exists:
                skipped += 1
                continue

        db.add(
            GenericRecord(
                tenant_id=tenant.id,
                station_id=station.id,
                schema_version_id=schema.id,
                lot_no_raw=key_val[:50],
                lot_no_norm=_lot_no_norm(key_val),
                data=row_data,
            )
        )
        imported += 1

    await db.commit()
    return UploadResult(total=len(df), imported=imported, skipped=skipped, errors=errors[:10])


@router.delete("/forms/{code}/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    code: str,
    record_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single record."""
    station = await _get_station(code, tenant.id, db)
    deleted = await db.execute(
        sql_delete(GenericRecord).where(
            GenericRecord.id == record_id,
            GenericRecord.tenant_id == tenant.id,
            GenericRecord.station_id == station.id,
        )
    )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="Record not found")
    await db.commit()
