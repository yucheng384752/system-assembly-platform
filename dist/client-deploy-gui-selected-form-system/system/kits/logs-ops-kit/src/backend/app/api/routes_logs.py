"""
logs-ops-kit: system log query API.

Routes (all tenant-scoped):
  GET /api/logs/          paginated log list with filters
  GET /api/logs/summary   counts by log_type + level (last 24 h)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()


def _row_to_dict(row: Any) -> dict[str, Any]:
    try:
        metadata = json.loads(row.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return {
        "id": row.id,
        "timestamp": row.timestamp,
        "log_type": row.log_type,
        "level": row.level,
        "action": row.action,
        "state": row.state,
        "describe": row.describe,
        "metadata": metadata,
    }


@router.get("/")
async def list_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    log_type: str | None = Query(
        None,
        description="user_action | system_error | system_warning | system",
    ),
    level: str | None = Query(None, description="INFO | WARNING | ERROR | CRITICAL"),
    action: str | None = Query(None, description="partial match on action name"),
    since: str | None = Query(None, description="ISO 8601 lower bound (inclusive)"),
    until: str | None = Query(None, description="ISO 8601 upper bound (inclusive)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    filters: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if log_type:
        filters.append("log_type = :log_type")
        params["log_type"] = log_type
    if level:
        filters.append("level = :level")
        params["level"] = level.upper()
    if action:
        filters.append("action LIKE :action")
        params["action"] = f"%{action}%"
    if since:
        filters.append("timestamp >= :since")
        params["since"] = since
    if until:
        filters.append("timestamp <= :until")
        params["until"] = until

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}

    rows = (
        await db.execute(
            text(
                f"SELECT id, timestamp, log_type, level, action, state, describe, metadata_json"
                f" FROM system_logs {where}"
                f" ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    ).fetchall()

    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM system_logs {where}"),
            count_params,
        )
    ).scalar() or 0

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_row_to_dict(r) for r in rows],
    }


@router.get("/summary")
async def log_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = (
        await db.execute(
            text(
                "SELECT log_type, level, COUNT(*) AS cnt"
                " FROM system_logs"
                " WHERE timestamp >= :since"
                " GROUP BY log_type, level"
                " ORDER BY cnt DESC"
            ),
            {"since": since},
        )
    ).fetchall()
    return {
        "since": since,
        "items": [
            {"log_type": r.log_type, "level": r.level, "count": r.cnt}
            for r in rows
        ],
    }
