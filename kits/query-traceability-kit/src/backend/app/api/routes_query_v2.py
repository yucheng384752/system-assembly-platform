"""Query V2 — cross-station lot search and traceability traversal."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.core.database import get_db
from app.models.core.tenant import Tenant
from app.models.generic_record import GenericRecord
from app.models.station import Station, StationLink
from app.utils.normalization import NormalizationError, normalize_lot_no

router = APIRouter(tags=["Query V2"])

MAX_TRACE_DEPTH = 5


# ── helpers ───────────────────────────────────────────────────────────────────

async def _station_map(tenant_id: uuid.UUID, db: AsyncSession) -> dict[uuid.UUID, Station]:
    rows = (
        await db.execute(select(Station).where(Station.tenant_id == tenant_id))
    ).scalars().all()
    return {s.id: s for s in rows}


def _record_dict(r: GenericRecord) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "lot_no_raw": r.lot_no_raw,
        "data": r.data,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _records_by_station_for_lot(
    lot_no: str,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> dict[uuid.UUID, list[GenericRecord]]:
    """Fetch a complete lot dataflow in one query, tolerant of lot formatting."""
    conditions = [GenericRecord.lot_no_raw == lot_no]
    try:
        conditions.append(GenericRecord.lot_no_norm == normalize_lot_no(lot_no))
    except NormalizationError:
        pass

    records = (
        await db.execute(
            select(GenericRecord)
            .where(
                GenericRecord.tenant_id == tenant_id,
                or_(*conditions),
            )
            .order_by(GenericRecord.created_at)
        )
    ).scalars().all()
    grouped: dict[uuid.UUID, list[GenericRecord]] = {}
    for record in records:
        grouped.setdefault(record.station_id, []).append(record)
    return grouped


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/lot/{lot_no}")
async def search_lot(
    lot_no: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Search all stations for a given lot_no_raw value."""
    station_map = await _station_map(tenant.id, db)
    records_by_station = await _records_by_station_for_lot(lot_no.strip(), tenant.id, db)
    results: list[dict] = []
    for st in station_map.values():
        if records := records_by_station.get(st.id):
            results.append({
                "station_code": st.code,
                "station_name": st.name,
                "records": [_record_dict(r) for r in records],
            })

    return results


@router.get("/trace/{lot_no}")
async def trace_lot(
    lot_no: str,
    flow_code: str = "default",
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Traverse StationLinks (link_type=sequential) starting from stations that
    have a record for lot_no, up to MAX_TRACE_DEPTH levels deep.
    """
    station_map = await _station_map(tenant.id, db)
    records_by_station = await _records_by_station_for_lot(lot_no.strip(), tenant.id, db)
    if not records_by_station:
        return []

    links = (
        await db.execute(
            select(StationLink).where(StationLink.tenant_id == tenant.id)
        )
    ).scalars().all()
    link_map: dict[uuid.UUID, list[uuid.UUID]] = {}
    for lnk in links:
        configured_flows = (lnk.link_config or {}).get("flowCodes")
        if isinstance(configured_flows, list) and flow_code not in configured_flows:
            continue
        if not isinstance(configured_flows, list) and flow_code != "default":
            continue
        link_map.setdefault(lnk.from_station_id, []).append(lnk.to_station_id)

    def _build_node(
        station_id: uuid.UUID,
        depth: int,
        path: frozenset[uuid.UUID],
    ) -> list[dict]:
        if depth > MAX_TRACE_DEPTH or station_id not in station_map or station_id in path:
            return []
        st = station_map[station_id]
        records = records_by_station.get(station_id, [])
        next_path = path | {station_id}
        nodes: list[dict] = []
        for rec in records:
            children: list[dict] = []
            for next_id in link_map.get(station_id, []):
                children.extend(_build_node(next_id, depth + 1, next_path))
            nodes.append({
                "station_code": st.code,
                "station_name": st.name,
                "record": _record_dict(rec),
                "linked_to": children,
            })
        return nodes

    record_station_ids = set(records_by_station)
    downstream_ids = {
        next_id
        for station_id in record_station_ids
        for next_id in link_map.get(station_id, [])
        if next_id in record_station_ids
    }
    root_ids = record_station_ids - downstream_ids
    if not root_ids:  # malformed cyclic dataflow: still return data without recursing forever
        root_ids = record_station_ids

    return [
        node
        for station_id in station_map
        if station_id in root_ids
        for node in _build_node(station_id, 0, frozenset())
    ]
