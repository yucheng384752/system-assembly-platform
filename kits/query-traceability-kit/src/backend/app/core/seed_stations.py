"""Seed customer station definitions on first startup.

Reads from customer-form-schema.json in the same directory.
Idempotent: skips stations whose code already exists for the tenant.
Stations are seeded into the 'default' tenant only.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core.tenant import Tenant
from app.models.station import Station, StationLink, StationSchema

_SCHEMA_FILE = Path(__file__).parent / "customer-form-schema.json"
_DATAFLOW_FILE = Path(__file__).parent / "customer-dataflows.json"


async def seed_stations(async_session_factory) -> None:
    if not _SCHEMA_FILE.exists():
        return

    definitions: list[dict] = json.loads(_SCHEMA_FILE.read_text("utf-8-sig"))
    dataflows: list[dict] = (
        json.loads(_DATAFLOW_FILE.read_text("utf-8-sig")) if _DATAFLOW_FILE.exists() else []
    )

    async with async_session_factory() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.is_default == True, Tenant.is_active == True))
        ).scalar_one_or_none()
        if tenant is None:
            tenant = (
                await db.execute(select(Tenant).where(Tenant.is_active == True).limit(1))
            ).scalar_one_or_none()
        if tenant is None:
            return

        for defn in definitions:
            existing = (
                await db.execute(
                    select(Station).where(
                        Station.tenant_id == tenant.id,
                        Station.code == defn["code"],
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            station = Station(
                tenant_id=tenant.id,
                code=defn["code"],
                name=defn["name"],
            )
            db.add(station)
            await db.flush()

            fields = [
                {
                    "name": f["name"],
                    "fieldKey": f.get("fieldKey", f["name"]),
                    "type": f.get("type", "string"),
                    "label": f.get("label", f["name"]),
                    "required": f.get("required", False),
                    "is_key": f.get("is_key", False),
                }
                for f in defn["fields"]
            ]
            schema = StationSchema(
                station_id=station.id,
                version=1,
                is_active=True,
                record_fields=fields,
                unique_key_fields=[f["fieldKey"] for f in defn["fields"] if f.get("is_key")],
            )
            db.add(schema)

        await db.flush()
        stations = (
            await db.execute(select(Station).where(Station.tenant_id == tenant.id))
        ).scalars().all()
        station_by_code = {station.code: station for station in stations}
        existing_links = (
            await db.execute(select(StationLink).where(StationLink.tenant_id == tenant.id))
        ).scalars().all()
        links_by_pair = {(link.from_station_id, link.to_station_id): link for link in existing_links}
        for flow in dataflows:
            flow_code = str(flow.get("code") or "default")
            for index, edge in enumerate(flow.get("edges") or []):
                from_station = station_by_code.get(edge.get("fromTableCode"))
                to_station = station_by_code.get(edge.get("toTableCode"))
                if not from_station or not to_station or from_station.id == to_station.id:
                    continue
                pair = (from_station.id, to_station.id)
                link = links_by_pair.get(pair)
                if link is None:
                    link = StationLink(
                        tenant_id=tenant.id,
                        from_station_id=from_station.id,
                        to_station_id=to_station.id,
                        link_type="sequential",
                        link_config={},
                        sort_order=index,
                    )
                    db.add(link)
                    links_by_pair[pair] = link
                config = dict(link.link_config or {})
                config["flowCodes"] = sorted(set(config.get("flowCodes") or []) | {flow_code})
                mappings = dict(config.get("keyMappings") or {})
                mappings[flow_code] = {
                    "parentColumn": edge.get("parentColumn"),
                    "childColumn": edge.get("childColumn"),
                }
                config["keyMappings"] = mappings
                link.link_config = config

        await db.commit()
