"""
audit-edit-kit: audit event query API.

Routes:
  GET /api/audit/events   paginated audit event list

Access control (system-admin only, per user decision 2026-08-21):
  - Platform admin (ADMIN_API_KEYS / X-Admin-API-Key -> request.state.is_admin) may
    list audit events across all tenants, optionally filtered to one tenant via
    ?tenant_id=.
  - Any other caller (including a plain tenant "manager") gets 403. Audit events can
    contain cross-request metadata about every tenant's activity, so unlike
    logs-ops-kit's per-tenant log viewer this is intentionally not tenant-self-serve.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.core.audit_event import AuditEvent

router = APIRouter(tags=["Audit Events"])


def _require_system_admin(request: Request) -> None:
    is_admin = bool(getattr(getattr(request, "state", None), "is_admin", False))
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="system-admin only")


def _event_dict(row: AuditEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "actor_api_key_id": str(row.actor_api_key_id) if row.actor_api_key_id else None,
        "actor_label_snapshot": row.actor_label_snapshot,
        "request_id": row.request_id,
        "method": row.method,
        "path": row.path,
        "status_code": row.status_code,
        "action": row.action,
        "metadata": row.metadata_json,
        "client_host": row.client_host,
        "user_agent": row.user_agent,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/audit/events")
async def list_audit_events(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    tenant_id: uuid.UUID | None = Query(None, description="Filter to one tenant"),
    action: str | None = Query(None, description="partial match on action name"),
    since: datetime | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
    until: datetime | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    _require_system_admin(request)

    stmt = select(AuditEvent)
    if tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == tenant_id)
    if action:
        stmt = stmt.where(AuditEvent.action.like(f"%{action}%"))
    if since:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.created_at <= until)

    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(stmt.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset))
    ).scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_event_dict(r) for r in rows],
    }
