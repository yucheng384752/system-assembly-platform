"""Generic Forms API — schema-driven form types, record storage, and CSV upload."""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db, get_db_context
from app.models.core.tenant import Tenant
from app.models.generic_record import GenericRecord
from app.models.station import Station, StationLink, StationSchema

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


class DataflowLinkIn(BaseModel):
    flow_code: str = "default"
    from_station_code: str
    to_station_code: str
    parent_column: str | None = None
    child_column: str | None = None
    sort_order: int = 0


class DataflowLinkRead(DataflowLinkIn):
    id: str


class UploadResult(BaseModel):
    total: int
    imported: int
    skipped: int
    errors: list[dict]


class PreviewResult(BaseModel):
    total: int
    preview_rows: list[dict]
    errors: list[dict]
    duplicate_count: int
    valid_count: int


class CommitResult(BaseModel):
    total: int
    imported: int
    skipped: int
    error_count: int
    job_id: str | None = None


class JobStatus(BaseModel):
    job_id: str
    status: str
    total: int
    imported: int
    skipped: int
    error_count: int
    created_at: str
    finished_at: str | None = None
    message: str | None = None


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
    ftype_lower = ftype.lower()
    if ftype_lower == "integer":
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return s
    if ftype_lower in ("decimal", "float", "number"):
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


# ── Import helpers ────────────────────────────────────────────────────────────

def _threshold_bytes() -> int:
    try:
        return int(float(os.environ.get("GENERIC_FORMS_ASYNC_THRESHOLD_MB", "1")) * 1024 * 1024)
    except (ValueError, TypeError):
        return 1048576


def _parse_csv_content(content: bytes) -> tuple["pd.DataFrame | None", "HTTPException | None"]:
    try:
        df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig", dtype=str)
    except Exception as exc:
        return None, HTTPException(status_code=422, detail=f"Cannot read CSV: {exc}")
    df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all")
    return df, None


def _map_row(row_dict: dict, fields: list[dict]) -> tuple[dict, list[str]]:
    row_data: dict[str, Any] = {}
    row_errors: list[str] = []
    for field in fields:
        field_key = field.get("fieldKey") or field.get("name")
        source_name = field.get("sourceName") or field_key
        ftype = field.get("type", "string")
        coerced = _coerce(row_dict.get(source_name), ftype)
        if field.get("required") and coerced is None:
            row_errors.append(f"'{source_name}' 為必填欄位")
        else:
            row_data[field_key] = coerced
    return row_data, row_errors


def _key_val_for(row_data: dict, key_fields: list[str]) -> str:
    if key_fields:
        val = "_".join(str(row_data.get(k) or "") for k in key_fields)
        return val if val.strip("_") else str(uuid.uuid4())
    return str(uuid.uuid4())


# ponytail: in-memory, single-process only — upgrade to DB model if multi-worker/restart-safe needed
_import_jobs: dict[str, dict] = {}


async def _do_commit(
    job_id: str,
    content: bytes,
    station_id: uuid.UUID,
    schema_id: uuid.UUID,
    tenant_id: uuid.UUID,
    fields: list[dict],
    key_fields: list[str],
) -> None:
    _import_jobs[job_id]["status"] = "running"
    total = imported = skipped = error_count = 0
    try:
        df, exc = _parse_csv_content(content)
        if exc:
            _import_jobs[job_id].update(
                status="failed", message=exc.detail,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            return
        if df is None or df.empty:
            _import_jobs[job_id].update(status="done", finished_at=datetime.now(timezone.utc).isoformat())
            return
        total = len(df)
        seen_keys: set[str] = set()
        async with get_db_context() as db:
            for row in df.itertuples(index=False):
                row_data, row_errors = _map_row(row._asdict(), fields)
                if row_errors:
                    error_count += 1
                    continue
                key_val = _key_val_for(row_data, key_fields)[:50]
                if key_val in seen_keys:
                    skipped += 1
                    continue
                exists = (
                    await db.execute(
                        select(GenericRecord.id).where(
                            GenericRecord.tenant_id == tenant_id,
                            GenericRecord.station_id == station_id,
                            GenericRecord.lot_no_raw == key_val,
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    skipped += 1
                    continue
                seen_keys.add(key_val)
                db.add(GenericRecord(
                    tenant_id=tenant_id,
                    station_id=station_id,
                    schema_version_id=schema_id,
                    lot_no_raw=key_val[:50],
                    lot_no_norm=_lot_no_norm(key_val),
                    data=row_data,
                ))
                imported += 1
        _import_jobs[job_id].update(
            status="done",
            total=total, imported=imported, skipped=skipped, error_count=error_count,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        _import_jobs[job_id].update(status="failed", finished_at=datetime.now(timezone.utc).isoformat())
        raise


async def _get_station(code: str, tenant_id: uuid.UUID, db: AsyncSession) -> Station:
    station = (
        await db.execute(
            select(Station).where(
                Station.tenant_id == tenant_id,
                Station.code == code.strip(),
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


def _flow_codes(link: StationLink) -> list[str]:
    codes = (link.link_config or {}).get("flowCodes")
    return [str(code) for code in codes] if isinstance(codes, list) else ["default"]


def _would_create_cycle(links: list[StationLink], flow_code: str, from_id: uuid.UUID, to_id: uuid.UUID) -> bool:
    graph: dict[uuid.UUID, list[uuid.UUID]] = {}
    for link in links:
        if flow_code in _flow_codes(link):
            graph.setdefault(link.from_station_id, []).append(link.to_station_id)
    graph.setdefault(from_id, []).append(to_id)
    stack = [to_id]
    seen: set[uuid.UUID] = set()
    while stack:
        current = stack.pop()
        if current == from_id:
            return True
        if current not in seen:
            seen.add(current)
            stack.extend(graph.get(current, []))
    return False


def _to_dataflow_link(link: StationLink, stations: dict[uuid.UUID, Station], flow_code: str) -> DataflowLinkRead:
    mappings = (link.link_config or {}).get("keyMappings", {})
    mapping = mappings.get(flow_code, {}) if isinstance(mappings, dict) else {}
    return DataflowLinkRead(
        id=str(link.id), flow_code=flow_code,
        from_station_code=stations[link.from_station_id].code,
        to_station_code=stations[link.to_station_id].code,
        parent_column=mapping.get("parentColumn"), child_column=mapping.get("childColumn"),
        sort_order=link.sort_order,
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/dataflows/links", response_model=list[DataflowLinkRead])
async def list_dataflow_links(
    flow_code: str = "default",
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    stations = (await db.execute(select(Station).where(Station.tenant_id == tenant.id))).scalars().all()
    station_map = {station.id: station for station in stations}
    links = (await db.execute(select(StationLink).where(StationLink.tenant_id == tenant.id))).scalars().all()
    return [_to_dataflow_link(link, station_map, flow_code) for link in links if flow_code in _flow_codes(link)]


@router.post("/dataflows/links", response_model=DataflowLinkRead)
@router.put("/dataflows/links", response_model=DataflowLinkRead)
async def upsert_dataflow_link(
    body: DataflowLinkIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    flow_code = body.flow_code.strip()
    if not flow_code:
        raise HTTPException(status_code=422, detail="flow_code is required")
    from_station = await _get_station(body.from_station_code, tenant.id, db)
    to_station = await _get_station(body.to_station_code, tenant.id, db)
    if from_station.id == to_station.id:
        raise HTTPException(status_code=422, detail="A dataflow link cannot point to itself")
    links = (await db.execute(select(StationLink).where(StationLink.tenant_id == tenant.id))).scalars().all()
    existing = next((link for link in links if link.from_station_id == from_station.id and link.to_station_id == to_station.id), None)
    already_in_flow = existing is not None and flow_code in _flow_codes(existing)
    if not already_in_flow and _would_create_cycle(links, flow_code, from_station.id, to_station.id):
        raise HTTPException(status_code=409, detail=f"Link would create a cycle in dataflow '{flow_code}'")
    link = existing or StationLink(
        tenant_id=tenant.id, from_station_id=from_station.id, to_station_id=to_station.id,
        link_type="sequential", link_config={}, sort_order=body.sort_order,
    )
    config = dict(link.link_config or {})
    config["flowCodes"] = sorted(set(_flow_codes(link) if existing else []) | {flow_code})
    mappings = dict(config.get("keyMappings") or {})
    mappings[flow_code] = {"parentColumn": body.parent_column, "childColumn": body.child_column}
    config["keyMappings"] = mappings
    link.link_config = config
    link.sort_order = body.sort_order
    if not existing:
        db.add(link)
    await db.commit()
    await db.refresh(link)
    return _to_dataflow_link(link, {from_station.id: from_station, to_station.id: to_station}, flow_code)


@router.delete("/dataflows/links/{from_code}/{to_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataflow_link(
    from_code: str,
    to_code: str,
    flow_code: str = "default",
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from_station = await _get_station(from_code, tenant.id, db)
    to_station = await _get_station(to_code, tenant.id, db)
    link = (await db.execute(select(StationLink).where(
        StationLink.tenant_id == tenant.id,
        StationLink.from_station_id == from_station.id,
        StationLink.to_station_id == to_station.id,
    ))).scalar_one_or_none()
    if not link or flow_code not in _flow_codes(link):
        raise HTTPException(status_code=404, detail="Dataflow link not found")
    remaining = [code for code in _flow_codes(link) if code != flow_code]
    if not remaining:
        await db.delete(link)
    else:
        config = dict(link.link_config or {})
        config["flowCodes"] = remaining
        mappings = dict(config.get("keyMappings") or {})
        mappings.pop(flow_code, None)
        config["keyMappings"] = mappings
        link.link_config = config
    await db.commit()

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
    code = body.code.strip()
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

    # Delete records (no ORM cascade to GenericRecord)
    await db.execute(
        sql_delete(GenericRecord).where(
            GenericRecord.station_id == station.id,
            GenericRecord.tenant_id == tenant.id,
        )
    )
    # Delete schemas
    await db.execute(
        sql_delete(StationSchema).where(StationSchema.station_id == station.id)
    )
    await db.execute(
        sql_delete(StationLink).where(
            StationLink.tenant_id == tenant.id,
            or_(StationLink.from_station_id == station.id, StationLink.to_station_id == station.id),
        )
    )
    # Delete station
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

    # Deactivate old schemas
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


async def _list_domain_records(
    code: str,
    schema: "StationSchema | None",
    tenant: Tenant,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> dict:
    """Read records directly from a domain physical table (e.g. daihui_entry)."""
    from sqlalchemy import text as _text
    fields: list[dict] = schema.record_fields if schema else []
    field_keys = [
        f.get("fieldKey") or f.get("name")
        for f in fields
        if f.get("fieldKey") or f.get("name")
    ]
    lot_field_key = next(
        (f.get("fieldKey") or f.get("name") for f in fields if f.get("role") == "lot"),
        None,
    )
    offset = max(0, (page - 1) * page_size)
    tid = str(tenant.id)

    try:
        total = (
            await db.execute(
                _text(f'SELECT COUNT(*) FROM "{code}" WHERE "_tenant_id" = :tid'),
                {"tid": tid},
            )
        ).scalar() or 0
    except Exception:
        total = 0

    safe_keys = [k for k in field_keys if k.replace("_", "").isalnum()]
    if not safe_keys:
        return {"total": total, "page": page, "page_size": page_size, "records": []}

    try:
        col_sql = ", ".join(f'"{k}"' for k in safe_keys)
        field_keys = safe_keys
        raw_rows = (
            await db.execute(
                _text(
                    f'SELECT {col_sql}, "_import_job_id", "_row_index", "_imported_at" '
                    f'FROM "{code}" WHERE "_tenant_id" = :tid '
                    f'ORDER BY "_imported_at" DESC NULLS LAST OFFSET :offset LIMIT :lim'
                ),
                {"tid": tid, "offset": offset, "lim": page_size},
            )
        ).mappings().all()
    except Exception:
        raw_rows = []

    records = []
    for r in raw_rows:
        data = {k: r.get(k) for k in field_keys}
        lot_raw = str(r[lot_field_key]) if lot_field_key and r.get(lot_field_key) is not None else str(r.get("_row_index", ""))
        imported_at = r.get("_imported_at")
        records.append({
            "id": f'{r.get("_import_job_id", "")}_{r.get("_row_index", "")}',
            "lot_no_raw": lot_raw,
            "data": data,
            "created_at": imported_at.isoformat() if imported_at and hasattr(imported_at, "isoformat") else (str(imported_at) if imported_at else None),
        })

    return {"total": total, "page": page, "page_size": page_size, "records": records}


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
    schema = await _active_schema(station.id, db)

    # Domain-backed tables (registered in table_registry) store rows in the physical table,
    # not GenericRecord. Check table_registry so this works for any client/project name.
    from app.models.core.schema_registry import TableRegistry
    is_domain = (
        await db.execute(select(TableRegistry.id).where(TableRegistry.table_code == code).limit(1))
    ).scalar_one_or_none() is not None
    if is_domain:
        return await _list_domain_records(code, schema, tenant, page, page_size, db)

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

    # Reject upload when no CSV column matches any schema field
    if fields:
        csv_columns = set(df.columns)
        schema_source_names = {f.get("sourceName") or f.get("name") for f in fields if f.get("sourceName") or f.get("name")}
        if not csv_columns & schema_source_names:
            raise HTTPException(
                status_code=422,
                detail=f"No CSV columns match the form schema. Expected headers: {sorted(schema_source_names)}, got: {sorted(csv_columns)}",
            )

    # Support both API-created format (name/is_key) and bootstrap format (fieldKey/sourceName/role)
    key_fields = [
        f.get("fieldKey") or f.get("name")
        for f in fields
        if f.get("is_key") or f.get("role") == "lot"
    ]

    imported = 0
    skipped = 0
    errors: list[dict] = []

    for row_idx, row in enumerate(df.itertuples(index=False)):
        row_dict = row._asdict()
        row_data: dict[str, Any] = {}
        row_errors: list[str] = []

        for field in fields:
            field_key = field.get("fieldKey") or field.get("name")  # DB storage key
            source_name = field.get("sourceName") or field_key  # CSV column header
            ftype = field.get("type", "string")
            raw_val = row_dict.get(source_name)
            coerced = _coerce(raw_val, ftype)

            if field.get("required") and coerced is None:
                row_errors.append(f"'{source_name}' 為必填欄位")
            else:
                row_data[field_key] = coerced

        if row_errors:
            errors.append({"row": row_idx + 1, "errors": row_errors})
            continue

        key_val = (
            "_".join(str(row_data.get(k) or "") for k in key_fields if k)
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


@router.post("/forms/{code}/import/preview", response_model=PreviewResult)
async def import_preview(
    code: str,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run CSV import: validate rows and report duplicates without writing to DB."""
    station = await _get_station(code, tenant.id, db)
    schema = await _active_schema(station.id, db)
    if not schema:
        raise HTTPException(422, "No schema defined. Use PUT /api/forms/{code}/schema first.")

    content = await file.read()
    df, exc = _parse_csv_content(content)
    if exc:
        raise exc
    if df.empty:
        return PreviewResult(total=0, preview_rows=[], errors=[], duplicate_count=0, valid_count=0)

    fields: list[dict] = schema.record_fields or []
    key_fields = [
        f.get("fieldKey") or f.get("name")
        for f in fields
        if f.get("is_key") or f.get("role") == "lot"
    ]

    valid_rows: list[tuple[dict, str]] = []
    errors: list[dict] = []
    for row_idx, row in enumerate(df.itertuples(index=False)):
        row_data, row_errors = _map_row(row._asdict(), fields)
        if row_errors:
            errors.append({"row": row_idx + 1, "errors": row_errors})
        else:
            valid_rows.append((row_data, _key_val_for(row_data, key_fields)))

    duplicate_count = 0
    for _, key_val in valid_rows:
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
            duplicate_count += 1

    return PreviewResult(
        total=len(df),
        preview_rows=[r for r, _ in valid_rows[:10]],
        errors=errors,
        duplicate_count=duplicate_count,
        valid_count=len(valid_rows) - duplicate_count,
    )


@router.post("/forms/{code}/import/commit", response_model=CommitResult)
async def import_commit(
    code: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Commit CSV import. Sync for files < GENERIC_FORMS_ASYNC_THRESHOLD_MB (default 1 MB), async otherwise."""
    station = await _get_station(code, tenant.id, db)
    schema = await _active_schema(station.id, db)
    if not schema:
        raise HTTPException(422, "No schema defined. Use PUT /api/forms/{code}/schema first.")

    content = await file.read()
    fields: list[dict] = schema.record_fields or []
    key_fields = [
        f.get("fieldKey") or f.get("name")
        for f in fields
        if f.get("is_key") or f.get("role") == "lot"
    ]

    if len(content) >= _threshold_bytes():
        job_id = str(uuid.uuid4())
        _import_jobs[job_id] = {
            "tenant_id": tenant.id,
            "status": "pending",
            "total": 0, "imported": 0, "skipped": 0, "error_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        }
        background_tasks.add_task(
            _do_commit, job_id, content, station.id, schema.id, tenant.id, fields, key_fields
        )
        return CommitResult(total=0, imported=0, skipped=0, error_count=0, job_id=job_id)

    df, exc = _parse_csv_content(content)
    if exc:
        raise exc
    if df.empty:
        return CommitResult(total=0, imported=0, skipped=0, error_count=0)

    imported = skipped = error_count = 0
    seen_keys: set[str] = set()
    for row in df.itertuples(index=False):
        row_data, row_errors = _map_row(row._asdict(), fields)
        if row_errors:
            error_count += 1
            continue
        key_val = _key_val_for(row_data, key_fields)[:50]
        if key_val in seen_keys:
            skipped += 1
            continue
        exists = (
            await db.execute(
                select(GenericRecord.id).where(
                    GenericRecord.tenant_id == tenant.id,
                    GenericRecord.station_id == station.id,
                    GenericRecord.lot_no_raw == key_val,
                )
            )
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        seen_keys.add(key_val)
        db.add(GenericRecord(
            tenant_id=tenant.id,
            station_id=station.id,
            schema_version_id=schema.id,
            lot_no_raw=key_val,
            lot_no_norm=_lot_no_norm(key_val),
            data=row_data,
        ))
        imported += 1
    await db.commit()
    return CommitResult(total=len(df), imported=imported, skipped=skipped, error_count=error_count)


@router.get("/forms/{code}/import-jobs/{job_id}", response_model=JobStatus)
async def get_import_job(
    code: str,
    job_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get status of an async import job."""
    # Verify the station exists and belongs to this tenant
    await _get_station(code, tenant.id, db)
    job = _import_jobs.get(job_id)
    # 404 (not 403) for a job owned by another tenant, so we don't confirm the job_id exists at all.
    if not job or job.get("tenant_id") != tenant.id:
        raise HTTPException(404, f"Import job '{job_id}' not found")
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        total=job.get("total", 0),
        imported=job.get("imported", 0),
        skipped=job.get("skipped", 0),
        error_count=job.get("error_count", 0),
        created_at=job["created_at"],
        finished_at=job.get("finished_at"),
        message=job.get("message"),
    )
