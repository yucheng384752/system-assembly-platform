"""Validation rule administration API."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.core.tenant import Tenant
from app.models.station import Station
from app.models.validation_rule import ValidationRule

router = APIRouter(tags=["Validation Rules"])


class ValidationRuleCreate(BaseModel):
    station_id: uuid.UUID | None = None
    field_name: str
    rule_type: str
    rule_config: dict[str, Any]
    is_active: bool = True


class ValidationRuleRead(BaseModel):
    id: str
    station_id: str | None
    field_name: str
    rule_type: str
    rule_config: dict[str, Any]
    is_active: bool


def _to_rule_read(rule: ValidationRule) -> ValidationRuleRead:
    return ValidationRuleRead(
        id=str(rule.id),
        station_id=str(rule.station_id) if rule.station_id else None,
        field_name=rule.field_name,
        rule_type=rule.rule_type,
        rule_config=rule.rule_config,
        is_active=rule.is_active,
    )


async def _ensure_station(tenant_id: uuid.UUID, station_id: uuid.UUID, db: AsyncSession) -> None:
    exists = (
        await db.execute(
            select(Station.id).where(
                Station.tenant_id == tenant_id,
                Station.id == station_id,
            )
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Station not found")


async def _get_rule(rule_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> ValidationRule:
    rule = (
        await db.execute(
            select(ValidationRule).where(
                ValidationRule.tenant_id == tenant_id,
                ValidationRule.id == rule_id,
            )
        )
    ).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Validation rule not found")
    return rule


@router.get("/rules", response_model=list[ValidationRuleRead])
async def list_rules(
    station_id: uuid.UUID | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ValidationRule).where(ValidationRule.tenant_id == tenant.id)
    if station_id is not None:
        stmt = stmt.where(ValidationRule.station_id == station_id)
    rows = (await db.execute(stmt.order_by(ValidationRule.field_name, ValidationRule.rule_type))).scalars().all()
    return [_to_rule_read(rule) for rule in rows]


@router.post("/rules", response_model=ValidationRuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: ValidationRuleCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if body.station_id is not None:
        await _ensure_station(tenant.id, body.station_id, db)

    existing = (
        await db.execute(
            select(ValidationRule.id).where(
                ValidationRule.tenant_id == tenant.id,
                ValidationRule.station_id == body.station_id,
                ValidationRule.field_name == body.field_name,
                ValidationRule.rule_type == body.rule_type,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Validation rule already exists")

    rule = ValidationRule(
        tenant_id=tenant.id,
        station_id=body.station_id,
        field_name=body.field_name.strip(),
        rule_type=body.rule_type.strip(),
        rule_config=body.rule_config,
        is_active=body.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_rule_read(rule)


@router.put("/rules/{rule_id}/toggle", response_model=ValidationRuleRead)
async def toggle_rule(
    rule_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    rule = await _get_rule(rule_id, tenant.id, db)
    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)
    return _to_rule_read(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    deleted = await db.execute(
        sql_delete(ValidationRule).where(
            ValidationRule.tenant_id == tenant.id,
            ValidationRule.id == rule_id,
        )
    )
    if deleted.rowcount == 0:
        raise HTTPException(status_code=404, detail="Validation rule not found")
    await db.commit()
