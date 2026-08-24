"""Tenant-scoped inline record edits and edit-reason catalog."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.audit import RowEdit
from app.models.core.edit_reason import EditReason
from app.models.core.tenant import Tenant
from app.models.generic_record import GenericRecord
from app.models.station import Station, StationSchema

router = APIRouter(tags=["Inline Edit"])


class RecordEditIn(BaseModel):
    reason_id: uuid.UUID
    changes: dict[str, str | int | float | bool | None]


class ReasonCreateIn(BaseModel):
    code: str
    label: str


class ReasonUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = None
    is_active: bool | None = None


def _require_tenant_manager(request: Request) -> None:
    state = getattr(request, "state", None)
    if not bool(getattr(state, "is_admin", False)) and getattr(state, "actor_role", None) != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager privileges required")


def _actor(request: Request) -> str | None:
    state = getattr(request, "state", None)
    for name in ("auth_api_key_label", "actor_user_id", "auth_api_key_id"):
        value = getattr(state, name, None)
        if value:
            return str(value)[:100]
    return None


def _reason_dict(reason: EditReason) -> dict[str, Any]:
    return {
        "id": str(reason.id),
        "code": reason.code,
        "label": reason.label,
        "is_active": reason.is_active,
        "created_at": reason.created_at.isoformat() if reason.created_at else None,
    }


async def _active_reason(
    db: AsyncSession, tenant_id: uuid.UUID, reason_id: uuid.UUID
) -> EditReason:
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
    return reason


def _coerce_changes(
    changes: dict[str, Any],
    fields: list[dict[str, Any]],
    coerce: Callable[[Any, str], Any],
) -> dict[str, Any]:
    if not changes:
        raise HTTPException(status_code=422, detail="changes must not be empty")
    if any(isinstance(value, (dict, list)) for value in changes.values()):
        raise HTTPException(status_code=422, detail="change values must be scalar")

    field_map = {
        str(field.get("fieldKey") or field.get("name")): field
        for field in fields
        if field.get("fieldKey") or field.get("name")
    }
    invalid = sorted(set(changes) - set(field_map))
    if invalid:
        raise HTTPException(status_code=422, detail={"invalid_fields": invalid})

    result: dict[str, Any] = {}
    for key, value in changes.items():
        field = field_map[key]
        field_type = str(field.get("type", "string"))
        coerced = coerce(value, field_type)
        if field.get("required") and coerced is None:
            raise HTTPException(status_code=422, detail=f"'{key}' is required")
        field_type_lower = field_type.lower()
        conversion_failed = (
            field_type_lower in {"integer", "decimal", "float", "number", "boolean"}
            and isinstance(coerced, str)
        )
        if value is not None and field_type_lower == "date":
            try:
                datetime.fromisoformat(str(value).strip())
            except ValueError:
                conversion_failed = True
        if value is not None and conversion_failed:
            raise HTTPException(status_code=422, detail=f"'{key}' is not a valid {field_type}")
        result[key] = coerced
    return result


@router.patch("/records/{table_code}/{record_id}")
async def edit_record(
    table_code: str,
    record_id: uuid.UUID,
    body: RecordEditIn,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    station = (
        await db.execute(
            select(Station).where(Station.tenant_id == tenant.id, Station.code == table_code.strip())
        )
    ).scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail=f"Form '{table_code}' not found")

    schema = (
        await db.execute(
            select(StationSchema)
            .where(StationSchema.station_id == station.id, StationSchema.is_active == True)
            .order_by(StationSchema.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=422, detail=f"Form '{table_code}' has no active schema")

    try:
        from app.api.routes_generic_forms import _coerce
    except Exception as exc:  # pragma: no cover - optional kit source
        raise HTTPException(status_code=501, detail="generic forms edit support is not installed") from exc

    changes = _coerce_changes(body.changes, schema.record_fields or [], _coerce)
    await _active_reason(db, tenant.id, body.reason_id)

    record = (
        await db.execute(
            select(GenericRecord).where(
                GenericRecord.id == record_id,
                GenericRecord.tenant_id == tenant.id,
                GenericRecord.station_id == station.id,
            )
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    data = dict(record.data or {})
    before = {key: data.get(key) for key, value in changes.items() if data.get(key) != value}
    after = {key: value for key, value in changes.items() if data.get(key) != value}
    data.update(after)
    record.data = data
    db.add(
        RowEdit(
            tenant_id=tenant.id,
            table_code=station.code,
            record_id=record.id,
            reason_id=body.reason_id,
            before_json=before,
            after_json=after,
            created_by=_actor(request),
        )
    )
    await db.commit()
    return {"id": str(record.id), "table_code": station.code, "changes": after, "data": data}


@router.get("/reasons")
async def list_reasons(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    # Any authenticated tenant actor may browse reasons — edit_record() and set_schema()
    # already accept reason_id from any actor (no manager check), so gating the read-only
    # catalog list behind manager only blocked the picker UI without adding real protection.
    # Mutating the catalog (create/update below) stays manager-only.
    reasons = (
        await db.execute(
            select(EditReason).where(EditReason.tenant_id == tenant.id).order_by(EditReason.code)
        )
    ).scalars().all()
    return [_reason_dict(reason) for reason in reasons]


@router.post("/reasons", status_code=status.HTTP_201_CREATED)
async def create_reason(
    body: ReasonCreateIn,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_tenant_manager(request)
    code, label = body.code.strip(), body.label.strip()
    if not code or not label:
        raise HTTPException(status_code=422, detail="code and label are required")
    if len(code) > 100 or len(label) > 255:
        raise HTTPException(status_code=422, detail="code or label is too long")
    reason = EditReason(tenant_id=tenant.id, code=code, label=label, is_active=True)
    db.add(reason)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Edit reason code '{code}' already exists") from exc
    await db.refresh(reason)
    return _reason_dict(reason)


@router.patch("/reasons/{reason_id}")
async def update_reason(
    reason_id: uuid.UUID,
    body: ReasonUpdateIn,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_tenant_manager(request)
    reason = (
        await db.execute(
            select(EditReason).where(EditReason.id == reason_id, EditReason.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if not reason:
        raise HTTPException(status_code=404, detail="Edit reason not found")
    if not body.model_fields_set:
        raise HTTPException(status_code=422, detail="At least one field is required")
    if "label" in body.model_fields_set:
        label = (body.label or "").strip()
        if not label:
            raise HTTPException(status_code=422, detail="label must not be empty")
        if len(label) > 255:
            raise HTTPException(status_code=422, detail="label is too long")
        reason.label = label
    if "is_active" in body.model_fields_set:
        if body.is_active is None:
            raise HTTPException(status_code=422, detail="is_active must be a boolean")
        reason.is_active = body.is_active
    await db.commit()
    await db.refresh(reason)
    return _reason_dict(reason)
