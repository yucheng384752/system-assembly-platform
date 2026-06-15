"""Seed default Station + StationSchema records for all active tenants.

Called at startup when USE_GENERIC_SCHEMA=true.
Idempotent — skips stations that already exist for a tenant.

Field type values: string | integer | decimal | date | boolean
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── Station definitions ───────────────────────────────────────────────────────
# Each entry maps directly to the legacy hard-coded model columns so that
# data migrated from p1_records / p2_records / p3_records round-trips cleanly.

_P1_FIELDS = [
    {"name": "lot_no", "type": "string", "label": "Lot No",
     "required": True, "is_key": True},
]

_P2_FIELDS = [
    {"name": "lot_no",        "type": "string",  "label": "Lot No",
     "required": True,  "is_key": True},
    {"name": "winder_number", "type": "integer", "label": "Winder Number",
     "required": True,  "is_key": True},
]

_P3_FIELDS = [
    {"name": "lot_no",                   "type": "string",  "label": "Lot No",
     "required": True,  "is_key": True},
    {"name": "production_date_yyyymmdd", "type": "integer", "label": "Production Date (YYYYMMDD)",
     "required": True,  "is_key": True},
    {"name": "machine_no",               "type": "string",  "label": "Machine No",
     "required": True,  "is_key": True},
    {"name": "mold_no",                  "type": "string",  "label": "Mold No",
     "required": True,  "is_key": True},
    {"name": "product_id",               "type": "string",  "label": "Product ID",
     "required": False, "is_key": False},
]

# Add or extend stations here — no code changes elsewhere needed.
_STATION_DEFS: list[dict] = [
    {"code": "P1", "name": "P1 入料製程", "sort_order": 10, "fields": _P1_FIELDS},
    {"code": "P2", "name": "P2 生產製程", "sort_order": 20, "fields": _P2_FIELDS},
    {"code": "P3", "name": "P3 品質製程", "sort_order": 30, "fields": _P3_FIELDS},
]


# ── Seed function ─────────────────────────────────────────────────────────────

async def seed_stations(async_session_factory) -> None:
    """Create Station + StationSchema v1 for every active tenant that doesn't have them yet."""
    from app.models.core.tenant import Tenant
    from app.models.station import Station, StationSchema

    async with async_session_factory() as db:
        tenants = (
            await db.execute(select(Tenant).where(Tenant.is_active == True))
        ).scalars().all()

        for tenant in tenants:
            for defn in _STATION_DEFS:
                exists = (
                    await db.execute(
                        select(Station.id).where(
                            Station.tenant_id == tenant.id,
                            Station.code == defn["code"],
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue

                station = Station(
                    tenant_id=tenant.id,
                    code=defn["code"],
                    name=defn["name"],
                    sort_order=defn["sort_order"],
                    has_items=False,
                )
                db.add(station)
                await db.flush()  # populate station.id before referencing it

                fields = defn["fields"]
                key_fields = [f["name"] for f in fields if f.get("is_key")]

                db.add(
                    StationSchema(
                        station_id=station.id,
                        version=1,
                        is_active=True,
                        record_fields=fields,
                        item_fields=None,
                        unique_key_fields=key_fields,
                        csv_signature_columns=[f["name"] for f in fields],
                        csv_filename_pattern=None,
                        csv_field_mapping={f["name"]: f["name"] for f in fields},
                    )
                )

        await db.commit()
