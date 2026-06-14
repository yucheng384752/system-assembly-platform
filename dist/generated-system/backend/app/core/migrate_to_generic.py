"""Migrate legacy P1/P2/P3 records into generic_records / generic_record_items.

Run once (idempotent — skips already-migrated records):

    python -m app.core.migrate_to_generic           # live run
    python -m app.core.migrate_to_generic --dry-run  # preview only, no writes

Or call programmatically:
    from app.core.migrate_to_generic import migrate_all
    summary = await migrate_all(async_session_factory, dry_run=False)
"""
from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

BATCH = 200  # records per DB round-trip


# ── helpers ───────────────────────────────────────────────────────────────────

def _lot_key(*parts: Any) -> str:
    """Build composite lot_no_raw from key field values (max 50 chars)."""
    joined = "_".join(str(p) for p in parts if p is not None)
    return joined[:50]


def _lot_norm(raw: str) -> int:
    cleaned = "".join(c for c in raw if c.isdigit())
    try:
        v = int(cleaned[:18]) if cleaned else 0
        return min(v, 9_223_372_036_854_775_807)
    except (ValueError, OverflowError):
        return 0


async def _station_id(code: str, tenant_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    from app.models.station import Station
    row = (
        await db.execute(
            select(Station.id).where(
                Station.tenant_id == tenant_id, Station.code == code
            )
        )
    ).scalar_one_or_none()
    return row


async def _schema_id(station_id: uuid.UUID, db: AsyncSession) -> uuid.UUID | None:
    from app.models.station import StationSchema
    row = (
        await db.execute(
            select(StationSchema.id)
            .where(StationSchema.station_id == station_id, StationSchema.is_active == True)
            .order_by(StationSchema.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


async def _existing_lot_nos(
    station_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> set[str]:
    from app.models.generic_record import GenericRecord
    rows = (
        await db.execute(
            select(GenericRecord.lot_no_raw).where(
                GenericRecord.station_id == station_id,
                GenericRecord.tenant_id == tenant_id,
            )
        )
    ).scalars().all()
    return set(rows)


# ── per-table migration functions ─────────────────────────────────────────────

async def _migrate_p1(
    tenant_id: uuid.UUID, station_id: uuid.UUID, schema_id: uuid.UUID | None,
    db: AsyncSession, dry_run: bool
) -> tuple[int, int]:
    """Returns (migrated, skipped)."""
    from app.models.generic_record import GenericRecord
    from app.models.p1_record import P1Record

    existing = await _existing_lot_nos(station_id, tenant_id, db)
    total = (
        await db.execute(
            select(P1Record).where(P1Record.tenant_id == tenant_id)
        )
    ).scalars()

    migrated = skipped = 0
    offset = 0

    while True:
        batch = (
            await db.execute(
                select(P1Record)
                .where(P1Record.tenant_id == tenant_id)
                .order_by(P1Record.created_at)
                .offset(offset)
                .limit(BATCH)
            )
        ).scalars().all()
        if not batch:
            break
        offset += len(batch)

        for rec in batch:
            lot_key = _lot_key(rec.lot_no_raw)
            if lot_key in existing:
                skipped += 1
                continue
            data: dict[str, Any] = {"lot_no": rec.lot_no_raw}
            if rec.extras:
                data.update(rec.extras)
            if not dry_run:
                db.add(GenericRecord(
                    tenant_id=tenant_id,
                    station_id=station_id,
                    schema_version_id=schema_id,
                    lot_no_raw=lot_key,
                    lot_no_norm=rec.lot_no_norm,
                    data=data,
                ))
            existing.add(lot_key)
            migrated += 1

        if not dry_run:
            await db.commit()

    return migrated, skipped


async def _migrate_p2(
    tenant_id: uuid.UUID, station_id: uuid.UUID, schema_id: uuid.UUID | None,
    db: AsyncSession, dry_run: bool
) -> tuple[int, int]:
    from app.models.generic_record import GenericRecord, GenericRecordItem
    from app.models.p2_record import P2Record
    from app.models.p2_item_v2 import P2ItemV2

    existing = await _existing_lot_nos(station_id, tenant_id, db)
    migrated = skipped = 0
    offset = 0

    while True:
        batch = (
            await db.execute(
                select(P2Record)
                .where(P2Record.tenant_id == tenant_id)
                .order_by(P2Record.created_at)
                .offset(offset)
                .limit(BATCH)
            )
        ).scalars().all()
        if not batch:
            break
        offset += len(batch)

        for rec in batch:
            lot_key = _lot_key(rec.lot_no_raw, rec.winder_number)
            if lot_key in existing:
                skipped += 1
                continue

            data: dict[str, Any] = {
                "lot_no": rec.lot_no_raw,
                "winder_number": rec.winder_number,
            }
            if rec.extras:
                data.update(rec.extras)

            if not dry_run:
                gr = GenericRecord(
                    tenant_id=tenant_id,
                    station_id=station_id,
                    schema_version_id=schema_id,
                    lot_no_raw=lot_key,
                    lot_no_norm=rec.lot_no_norm,
                    data=data,
                )
                db.add(gr)
                await db.flush()  # get gr.id

                # Migrate P2ItemV2 → GenericRecordItem
                items = (
                    await db.execute(
                        select(P2ItemV2).where(P2ItemV2.p2_record_id == rec.id)
                    )
                ).scalars().all()
                for row_no, item in enumerate(items, start=1):
                    item_data: dict[str, Any] = {
                        "winder_number": item.winder_number,
                        "production_date_yyyymmdd": item.production_date_yyyymmdd,
                        "trace_lot_no": item.trace_lot_no,
                        "sheet_width": item.sheet_width,
                        "thickness1": item.thickness1,
                        "thickness2": item.thickness2,
                        "thickness3": item.thickness3,
                        "thickness4": item.thickness4,
                        "thickness5": item.thickness5,
                        "thickness6": item.thickness6,
                        "thickness7": item.thickness7,
                        "appearance": item.appearance,
                        "rough_edge": item.rough_edge,
                        "slitting_result": item.slitting_result,
                    }
                    row_data = item.row_data or {}
                    db.add(GenericRecordItem(
                        record_id=gr.id,
                        tenant_id=tenant_id,
                        row_no=row_no,
                        data={k: v for k, v in item_data.items() if v is not None},
                        row_data=row_data,
                    ))

            existing.add(lot_key)
            migrated += 1

        if not dry_run:
            await db.commit()

    return migrated, skipped


async def _migrate_p3(
    tenant_id: uuid.UUID, station_id: uuid.UUID, schema_id: uuid.UUID | None,
    db: AsyncSession, dry_run: bool
) -> tuple[int, int]:
    from app.models.generic_record import GenericRecord, GenericRecordItem
    from app.models.p3_record import P3Record
    from app.models.p3_item_v2 import P3ItemV2

    existing = await _existing_lot_nos(station_id, tenant_id, db)
    migrated = skipped = 0
    offset = 0

    while True:
        batch = (
            await db.execute(
                select(P3Record)
                .where(P3Record.tenant_id == tenant_id)
                .order_by(P3Record.created_at)
                .offset(offset)
                .limit(BATCH)
            )
        ).scalars().all()
        if not batch:
            break
        offset += len(batch)

        for rec in batch:
            lot_key = _lot_key(
                rec.lot_no_raw,
                rec.production_date_yyyymmdd,
                rec.machine_no,
                rec.mold_no,
            )
            if lot_key in existing:
                skipped += 1
                continue

            data: dict[str, Any] = {
                "lot_no": rec.lot_no_raw,
                "production_date_yyyymmdd": rec.production_date_yyyymmdd,
                "machine_no": rec.machine_no,
                "mold_no": rec.mold_no,
                "product_id": rec.product_id,
            }
            if rec.extras:
                data.update(rec.extras)

            if not dry_run:
                gr = GenericRecord(
                    tenant_id=tenant_id,
                    station_id=station_id,
                    schema_version_id=schema_id,
                    lot_no_raw=lot_key,
                    lot_no_norm=rec.lot_no_norm,
                    data=data,
                )
                db.add(gr)
                await db.flush()

                items = (
                    await db.execute(
                        select(P3ItemV2).where(P3ItemV2.p3_record_id == rec.id)
                    )
                ).scalars().all()
                for item in items:
                    item_data: dict[str, Any] = {
                        "product_id": item.product_id,
                        "lot_no": item.lot_no,
                        "production_date": str(item.production_date) if item.production_date else None,
                        "machine_no": item.machine_no,
                        "mold_no": item.mold_no,
                        "production_lot": item.production_lot,
                        "source_winder": item.source_winder,
                        "specification": item.specification,
                        "bottom_tape_lot": item.bottom_tape_lot,
                    }
                    row_data = item.row_data or {}
                    db.add(GenericRecordItem(
                        record_id=gr.id,
                        tenant_id=tenant_id,
                        row_no=item.row_no,
                        data={k: v for k, v in item_data.items() if v is not None},
                        row_data=row_data,
                    ))

            existing.add(lot_key)
            migrated += 1

        if not dry_run:
            await db.commit()

    return migrated, skipped


# ── public API ────────────────────────────────────────────────────────────────

@dataclass
class MigrationSummary:
    dry_run: bool = False
    tenants: int = 0
    details: list[dict] = field(default_factory=list)

    @property
    def total_migrated(self) -> int:
        return sum(d["migrated"] for d in self.details)

    @property
    def total_skipped(self) -> int:
        return sum(d["skipped"] for d in self.details)

    def print(self) -> None:
        mode = "[DRY RUN] " if self.dry_run else ""
        print(f"\n{mode}Migration summary — {self.tenants} tenant(s)")
        print(f"  Total migrated : {self.total_migrated}")
        print(f"  Total skipped  : {self.total_skipped} (already existed)")
        print()
        for d in self.details:
            print(f"  tenant={d['tenant_code']}  station={d['station']}"
                  f"  migrated={d['migrated']}  skipped={d['skipped']}")


async def migrate_all(async_session_factory, *, dry_run: bool = False) -> MigrationSummary:
    """Migrate all P1/P2/P3 records for all active tenants."""
    from app.models.core.tenant import Tenant

    summary = MigrationSummary(dry_run=dry_run)

    async with async_session_factory() as db:
        tenants = (
            await db.execute(select(Tenant).where(Tenant.is_active == True))
        ).scalars().all()
        summary.tenants = len(tenants)

    for tenant in tenants:
        async with async_session_factory() as db:
            for station_code, migrate_fn in [
                ("P1", _migrate_p1),
                ("P2", _migrate_p2),
                ("P3", _migrate_p3),
            ]:
                st_id = await _station_id(station_code, tenant.id, db)
                if st_id is None:
                    # Station not seeded yet — seed_stations must run first
                    print(f"  WARN: Station {station_code} not found for tenant "
                          f"'{tenant.code}'. Run seed_stations first.")
                    continue

                sc_id = await _schema_id(st_id, db)
                migrated, skipped = await migrate_fn(
                    tenant.id, st_id, sc_id, db, dry_run
                )
                summary.details.append({
                    "tenant_code": tenant.code,
                    "station": station_code,
                    "migrated": migrated,
                    "skipped": skipped,
                })
                print(f"  {tenant.code}/{station_code}: "
                      f"migrated={migrated}, skipped={skipped}"
                      + (" [DRY RUN]" if dry_run else ""))

    return summary


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import os

    dry_run = "--dry-run" in sys.argv

    async def _main() -> None:
        # Bootstrap DB connection using the same path as main.py
        from app.core.config import get_settings
        from app.core.database import init_db

        settings = get_settings()
        await init_db()

        from app.core.database import async_session_factory

        if async_session_factory is None:
            print("ERROR: database not initialised")
            sys.exit(1)

        summary = await migrate_all(async_session_factory, dry_run=dry_run)
        summary.print()

    asyncio.run(_main())
