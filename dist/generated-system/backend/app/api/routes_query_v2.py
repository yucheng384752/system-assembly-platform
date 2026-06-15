"""Query V2 — cross-station lot search and traceability traversal."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.core.tenant import Tenant
from app.models.generic_record import GenericRecord
from app.models.station import Station, StationLink, StationSchema

router = APIRouter(tags=["Query V2"])

MAX_TRACE_DEPTH = 5


# ── helpers ───────────────────────────────────────────────────────────────────

async def _station_map(tenant_id: uuid.UUID, db: AsyncSession) -> dict[uuid.UUID, Station]:
    rows = (
        await db.execute(select(Station).where(Station.tenant_id == tenant_id))
    ).scalars().all()
    return {s.id: s for s in rows}


async def _active_fields(station_id: uuid.UUID, db: AsyncSession) -> list[str]:
    schema = (
        await db.execute(
            select(StationSchema)
            .where(StationSchema.station_id == station_id, StationSchema.is_active == True)
            .order_by(StationSchema.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not schema or not schema.record_fields:
        return []
    return [f.get("name", "") for f in schema.record_fields if f.get("name")]


def _record_dict(r: GenericRecord) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "lot_no_raw": r.lot_no_raw,
        "data": r.data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _records_for_lot(
    lot_no: str,
    station_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> list[GenericRecord]:
    return (
        await db.execute(
            select(GenericRecord).where(
                GenericRecord.tenant_id == tenant_id,
                GenericRecord.station_id == station_id,
                GenericRecord.lot_no_raw == lot_no,
            )
        )
    ).scalars().all()


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/lot/{lot_no}")
async def search_lot(
    lot_no: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Search all stations for a given lot_no_raw value."""
    station_map = await _station_map(tenant.id, db)
    results: list[dict] = []

    for st in station_map.values():
        records = await _records_for_lot(lot_no, st.id, tenant.id, db)
        if records:
            results.append({
                "station_code": st.code,
                "station_name": st.name,
                "records": [_record_dict(r) for r in records],
            })

    return results


@router.get("/trace/{lot_no}")
async def trace_lot(
    lot_no: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Traverse StationLinks (link_type=sequential) starting from stations that
    have a record for lot_no, up to MAX_TRACE_DEPTH levels deep.
    """
    station_map = await _station_map(tenant.id, db)

    # Pre-load all station links for this tenant
    links = (
        await db.execute(
            select(StationLink).where(StationLink.tenant_id == tenant.id)
        )
    ).scalars().all()
    # from_station_id → list of to_station_id
    link_map: dict[uuid.UUID, list[uuid.UUID]] = {}
    for lnk in links:
        link_map.setdefault(lnk.from_station_id, []).append(lnk.to_station_id)

    async def _build_node(station_id: uuid.UUID, current_lot: str, depth: int) -> list[dict]:
        if depth > MAX_TRACE_DEPTH or station_id not in station_map:
            return []
        st = station_map[station_id]
        records = await _records_for_lot(current_lot, station_id, tenant.id, db)
        nodes: list[dict] = []
        for rec in records:
            children: list[dict] = []
            for next_id in link_map.get(station_id, []):
                children.extend(await _build_node(next_id, current_lot, depth + 1))
            nodes.append({
                "station_code": st.code,
                "station_name": st.name,
                "record": _record_dict(rec),
                "linked_to": children,
            })
        return nodes

    # Start from every station that has this lot_no
    result: list[dict] = []
    visited_starts: set[uuid.UUID] = set()
    for st in station_map.values():
        records = await _records_for_lot(lot_no, st.id, tenant.id, db)
        if records and st.id not in visited_starts:
            visited_starts.add(st.id)
            for rec in records:
                children: list[dict] = []
                for next_id in link_map.get(st.id, []):
                    children.extend(await _build_node(next_id, lot_no, 1))
                result.append({
                    "station_code": st.code,
                    "station_name": st.name,
                    "record": _record_dict(rec),
                    "linked_to": children,
                })

    return result
