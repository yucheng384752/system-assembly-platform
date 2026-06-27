import csv
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core.schema_registry import SchemaVersion, TableRegistry
from app.models.import_job import ImportJob, ImportJobStatus, StagingRow
from app.services.audit_events import write_audit_event_best_effort
from app.services.csv_field_mapper import CSVFieldMapper, csv_field_mapper
from app.utils.normalization import normalize_lot_no

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_schema_version_for_table(self, table_id: uuid.UUID) -> SchemaVersion | None:
        result = await self.db.execute(
            select(SchemaVersion)
            .where(SchemaVersion.table_id == table_id)
            .order_by(SchemaVersion.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    def _schema_fields(self, schema: SchemaVersion) -> list[dict[str, Any]]:
        schema_json = schema.schema_json or {}
        fields = schema_json.get("fields") or schema_json.get("columns") or []
        return [field for field in fields if isinstance(field, dict)]

    def _schema_column_names(self, schema: SchemaVersion) -> list[str]:
        columns: list[str] = []
        for field in self._schema_fields(schema):
            column = field.get("fieldKey") or field.get("name")
            if column:
                column = str(column)
                if not column.replace("_", "").isalnum():
                    raise ValueError(f"Unsafe schema column name: {column}")
                columns.append(column)
        return columns

    def _schema_row_data(
        self, schema: SchemaVersion, row: dict[str, Any]
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field in self._schema_fields(schema):
            column = field.get("fieldKey") or field.get("name")
            if not column:
                continue
            column = str(column)
            source = field.get("sourceName") or field.get("name") or column
            data[column] = row.get(str(source), row.get(column))
        return data

    async def _commit_schema_target_rows(
        self,
        *,
        table_code: str,
        table_id: uuid.UUID,
        rows: list[dict[str, Any]],
    ) -> int:
        if not table_code.replace("_", "").isalnum():
            raise ValueError(f"Unsafe table_code={table_code}")
        schema = await self._get_schema_version_for_table(table_id)
        if schema is None:
            raise ValueError(f"No schema found for table_code={table_code}")

        columns = self._schema_column_names(schema)
        if not columns:
            raise ValueError(f"No schema columns found for table_code={table_code}")

        quoted_columns = ", ".join(f'"{column}"' for column in columns)
        placeholders = ", ".join(f":{column}" for column in columns)
        stmt = text(
            f'INSERT INTO "{table_code}" ({quoted_columns}) VALUES ({placeholders})'
        )

        inserted_count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            await self.db.execute(stmt, self._schema_row_data(schema, row))
            inserted_count += 1

        await self.db.flush()
        return inserted_count

    def _extract_lot_no_from_row_dict(self, row: dict[str, Any]) -> str | None:
        if not row or not isinstance(row, dict):
            return None
        for field in CSVFieldMapper.LOT_NO_FIELD_NAMES:
            v = row.get(field)
            if v is None or v == "":
                continue
            s = str(v).strip()
            if s:
                return s
        return None

    def _canonicalize_lot_no_raw(self, val: str) -> str | None:
        """Return canonical 7+2 lot in underscore form, or None if invalid."""
        s = str(val or "").strip()
        if not s:
            return None
        m = re.match(r"^(\d{7})[-_](\d{1,2})(?:[-_].+)?$", s)
        if not m:
            return None
        return f"{m.group(1)}_{m.group(2).zfill(2)}"

    def _touch_status(
        self,
        job: ImportJob,
        status: str,
        *,
        actor_api_key_id: uuid.UUID | None = None,
        actor_label_snapshot: str | None = None,
        actor_kind: str = "system",
    ) -> None:
        job.status = status
        job.last_status_changed_at = datetime.now(timezone.utc)
        job.last_status_actor_kind = actor_kind
        job.last_status_actor_api_key_id = actor_api_key_id
        job.last_status_actor_label_snapshot = actor_label_snapshot

    def _row_signature_for_dedupe(self, row: dict[str, Any]) -> str:
        """Compute a stable signature for a parsed CSV row.

        This is an *exact-match* dedupe helper (after light normalization), used to
        avoid double-counting when multiple files contain mostly the same rows.
        """
        if not isinstance(row, dict):
            return ""

        normalized: dict[str, Any] = {}
        for k, v in row.items():
            key = str(k).strip()
            if key == "":
                continue
            if v is None:
                normalized[key] = None
                continue
            s = str(v).strip()
            normalized[key] = s

        # JSON canonicalization: stable order, stable separators.
        return json.dumps(
            normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    def _dedupe_rows_exact(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            sig = self._row_signature_for_dedupe(r)
            if not sig:
                continue
            if sig in seen:
                continue
            seen.add(sig)
            out.append(r)
        return out

    def _is_empty_value(self, v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str) and v.strip() == "":
            return True
        return False

    def _normalize_value_for_compare(self, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _is_blank_row_dict(self, row: dict[str, Any] | None) -> bool:
        if not row or not isinstance(row, dict):
            return True
        return all(self._is_empty_value(v) for v in row.values())

    def _row_completeness_score(self, row: dict[str, Any]) -> int:
        if not isinstance(row, dict):
            return 0
        return sum(1 for v in row.values() if not self._is_empty_value(v))

    def _merge_rows_prefer_complete(
        self, rows: list[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, int]:
        """Merge multiple parsed rows into one.

        Used for exact-match dedupe before merging rows with the same business key
        but rows differ by a few fields.

        Strategy (conservative):
        - Pick the most complete row as base.
        - Fill missing/empty fields from other rows.
        - If both sides have non-empty but different values, keep base and count a conflict.
        """
        material_rows = [r for r in (rows or []) if isinstance(r, dict)]
        if not material_rows:
            return None, 0

        material_rows.sort(key=self._row_completeness_score, reverse=True)
        merged: dict[str, Any] = dict(material_rows[0])
        conflicts = 0

        for r in material_rows[1:]:
            for k, v in r.items():
                if k not in merged or self._is_empty_value(merged.get(k)):
                    if not self._is_empty_value(v):
                        merged[k] = v
                    continue

                if self._is_empty_value(v):
                    continue

                a = self._normalize_value_for_compare(merged.get(k))
                b = self._normalize_value_for_compare(v)
                if a != b:
                    conflicts += 1

        return merged, conflicts

    async def parse_job(
        self,
        job_id: uuid.UUID,
        *,
        actor_api_key_id: uuid.UUID | None = None,
        actor_label_snapshot: str | None = None,
        actor_kind: str = "system",
    ) -> ImportJob:
        """
        Parse all files in the import job and populate staging_rows.
        """
        # 1. Fetch Job with Files
        stmt = (
            select(ImportJob)
            .options(selectinload(ImportJob.files))
            .where(ImportJob.id == job_id)
        )
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Import job {job_id} not found")

        # 2. Update Status to PARSING
        prev_status = job.status
        self._touch_status(
            job,
            ImportJobStatus.PARSING,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_label_snapshot,
            actor_kind=actor_kind,
        )
        await self.db.commit()

        await write_audit_event_best_effort(
            tenant_id=job.tenant_id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_label_snapshot,
            request_id=None,
            method="INTERNAL",
            path=f"/internal/v2/import/jobs/{job.id}/status",
            status_code=0,
            action="import.job.status",
            metadata={
                "job_id": str(job.id),
                "from_status": getattr(prev_status, "name", str(prev_status)),
                "to_status": getattr(job.status, "name", str(job.status)),
                "actor_kind": actor_kind,
            },
        )

        total_rows_job = 0

        try:
            for file_record in job.files:
                file_path = Path(file_record.storage_path)
                if not file_path.exists():
                    logger.error(f"File not found: {file_path}")
                    continue

                # Parse CSV
                rows_to_insert = []
                row_count_file = 0

                # TODO: Handle encoding detection if needed. Defaulting to utf-8-sig for now.
                try:
                    with open(file_path, encoding="utf-8-sig", newline="") as csvfile:
                        reader = csv.DictReader(csvfile)

                        # Normalize headers?
                        # For now, we assume headers match the keys we want or we store raw dict.

                        for i, row in enumerate(reader, start=1):
                            # Basic cleanup: strip whitespace from keys and values
                            clean_row = {
                                k.strip(): v.strip() for k, v in row.items() if k
                            }
                            if self._is_blank_row_dict(clean_row):
                                continue

                            staging_row = StagingRow(
                                id=uuid.uuid4(),
                                job_id=job.id,
                                file_id=file_record.id,
                                row_index=i,
                                parsed_json=clean_row,
                                is_valid=True,  # Assume valid until validation step
                                errors_json=[],
                            )
                            rows_to_insert.append(staging_row)
                            row_count_file += 1

                            # Batch insert every 1000 rows to avoid memory issues
                            if len(rows_to_insert) >= 1000:
                                self.db.add_all(rows_to_insert)
                                await (
                                    self.db.flush()
                                )  # Flush to send to DB but not commit yet
                                rows_to_insert = []

                    # Insert remaining rows
                    if rows_to_insert:
                        self.db.add_all(rows_to_insert)
                        await self.db.flush()

                    # Update file row count
                    file_record.row_count = row_count_file
                    total_rows_job += row_count_file

                except UnicodeDecodeError:
                    # Fallback to cp950 (Big5) commonly used in Taiwan/Windows
                    with open(file_path, encoding="cp950", newline="") as csvfile:
                        reader = csv.DictReader(csvfile)
                        for i, row in enumerate(reader, start=1):
                            clean_row = {
                                k.strip(): v.strip() for k, v in row.items() if k
                            }
                            if self._is_blank_row_dict(clean_row):
                                continue
                            staging_row = StagingRow(
                                id=uuid.uuid4(),
                                job_id=job.id,
                                file_id=file_record.id,
                                row_index=i,
                                parsed_json=clean_row,
                                is_valid=True,
                                errors_json=[],
                            )
                            rows_to_insert.append(staging_row)
                            row_count_file += 1
                            if len(rows_to_insert) >= 1000:
                                self.db.add_all(rows_to_insert)
                                await self.db.flush()
                                rows_to_insert = []
                        if rows_to_insert:
                            self.db.add_all(rows_to_insert)
                            await self.db.flush()

                    file_record.row_count = row_count_file
                    total_rows_job += row_count_file

            # 3. Update Job Status to VALIDATING (or READY if we skip validation for now)
            # The plan implies validation is next.
            job.total_rows = total_rows_job
            prev_status = job.status
            self._touch_status(
                job,
                ImportJobStatus.VALIDATING,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )

            await self.db.commit()

            await write_audit_event_best_effort(
                tenant_id=job.tenant_id,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                request_id=None,
                method="INTERNAL",
                path=f"/internal/v2/import/jobs/{job.id}/status",
                status_code=0,
                action="import.job.status",
                metadata={
                    "job_id": str(job.id),
                    "from_status": getattr(prev_status, "name", str(prev_status)),
                    "to_status": getattr(job.status, "name", str(job.status)),
                    "actor_kind": actor_kind,
                    "total_rows": int(total_rows_job),
                },
            )
            return job

        except Exception as e:
            logger.exception(f"Error parsing job {job_id}: {e}")
            prev_status = job.status
            self._touch_status(
                job,
                ImportJobStatus.FAILED,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )
            job.error_summary = {"error": str(e)}
            await self.db.commit()

            if job:
                await write_audit_event_best_effort(
                    tenant_id=job.tenant_id,
                    actor_api_key_id=actor_api_key_id,
                    actor_label_snapshot=actor_label_snapshot,
                    request_id=None,
                    method="INTERNAL",
                    path=f"/internal/v2/import/jobs/{job.id}/status",
                    status_code=0,
                    action="import.job.status",
                    metadata={
                        "job_id": str(job.id),
                        "from_status": getattr(prev_status, "name", str(prev_status)),
                        "to_status": getattr(job.status, "name", str(job.status)),
                        "actor_kind": actor_kind,
                        "error": str(e)[:200],
                    },
                )
            raise e

    async def validate_job(
        self,
        job_id: uuid.UUID,
        *,
        actor_api_key_id: uuid.UUID | None = None,
        actor_label_snapshot: str | None = None,
        actor_kind: str = "system",
    ) -> ImportJob:
        """
        Validate staging rows against schema.
        """
        # 1. Fetch Job with Table info and Files
        stmt = (
            select(ImportJob)
            .options(selectinload(ImportJob.files))
            .where(ImportJob.id == job_id)
        )
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            raise ValueError(f"Import job {job_id} not found")

        # Fetch table code to determine validation rules
        table_stmt = select(TableRegistry).where(TableRegistry.id == job.table_id)
        table_result = await self.db.execute(table_stmt)
        table = table_result.scalar_one_or_none()

        if not table:
            raise ValueError(f"Table for job {job_id} not found")

        # Map file_id to filename
        file_map = {f.id: f.filename for f in job.files}

        # 2. Define Validation Rules
        # Import V2 目前採用「一個檔案 → 1 筆 records + N 筆 items」的混合架構。
        # 因此 staging_rows 不應以「同一檔案內 key 重複」判錯（會把多列 items 全打成 invalid）。
        # 這裡僅做非常保守的欄位檢查；真正的欄位映射/解析放在 commit_job。
        required_fields: list[str] = []
        numeric_fields: list[str] = []

        # lot_no 驗證：一律從內容欄位抓取
        # 3. Iterate and Validate Staging Rows
        offset = 0
        limit = 1000
        error_count_job = 0

        while True:
            rows_stmt = (
                select(StagingRow)
                .where(StagingRow.job_id == job_id)
                .offset(offset)
                .limit(limit)
            )
            rows_result = await self.db.execute(rows_stmt)
            rows = rows_result.scalars().all()

            if not rows:
                break

            for row in rows:
                errors = []
                data = row.parsed_json
                _filename = file_map.get(row.file_id, "")
                if self._is_blank_row_dict(data if isinstance(data, dict) else None):
                    row.is_valid = True
                    row.errors_json = []
                    continue

                # Check required fields
                for field in required_fields:
                    if field not in data or not data[field]:
                        errors.append(
                            {"field": field, "message": "Missing required field"}
                        )

                # Check numeric fields
                for field in numeric_fields:
                    if field in data and data[field]:
                        try:
                            float(data[field])
                        except ValueError:
                            errors.append(
                                {"field": field, "message": "Value must be numeric"}
                            )

                if errors:
                    row.is_valid = False
                    row.errors_json = errors
                    error_count_job += 1
                else:
                    row.is_valid = True
                    row.errors_json = []

            # Flush changes for this chunk
            await self.db.flush()
            offset += limit

        # 4. Update Job Status
        job.error_count = error_count_job
        # If validation is done, we mark it as READY (for review/commit)
        prev_status = job.status
        self._touch_status(
            job,
            ImportJobStatus.READY,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_label_snapshot,
            actor_kind=actor_kind,
        )
        await self.db.commit()

        await write_audit_event_best_effort(
            tenant_id=job.tenant_id,
            actor_api_key_id=actor_api_key_id,
            actor_label_snapshot=actor_label_snapshot,
            request_id=None,
            method="INTERNAL",
            path=f"/internal/v2/import/jobs/{job.id}/status",
            status_code=0,
            action="import.job.status",
            metadata={
                "job_id": str(job.id),
                "from_status": getattr(prev_status, "name", str(prev_status)),
                "to_status": getattr(job.status, "name", str(job.status)),
                "actor_kind": actor_kind,
                "error_count": int(error_count_job),
            },
        )
        return job

    async def commit_job(
        self,
        job_id: uuid.UUID,
        *,
        actor_api_key_id: uuid.UUID | None = None,
        actor_label_snapshot: str | None = None,
        actor_kind: str = "system",
    ) -> ImportJob:
        """Commit valid staging rows to the configured target table."""
        logger.info(f"Starting commit_job for {job_id}")
        stmt = (
            select(ImportJob)
            .options(selectinload(ImportJob.files))
            .where(ImportJob.id == job_id)
        )
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            raise ValueError(f"Import job {job_id} not found")

        if job.status not in (ImportJobStatus.READY, ImportJobStatus.COMMITTING):
            raise ValueError(
                f"Job {job_id} is not ready to commit (status: {job.status})"
            )

        if job.status == ImportJobStatus.READY:
            prev_status = job.status
            self._touch_status(
                job,
                ImportJobStatus.COMMITTING,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )
            await self.db.commit()
            await write_audit_event_best_effort(
                tenant_id=job.tenant_id,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                request_id=None,
                method="INTERNAL",
                path=f"/internal/v2/import/jobs/{job.id}/status",
                status_code=0,
                action="import.job.status",
                metadata={
                    "job_id": str(job.id),
                    "from_status": getattr(prev_status, "name", str(prev_status)),
                    "to_status": getattr(job.status, "name", str(job.status)),
                    "actor_kind": actor_kind,
                },
            )

        table_result = await self.db.execute(
            select(TableRegistry).where(TableRegistry.id == job.table_id)
        )
        table = table_result.scalar_one_or_none()
        if not table:
            raise ValueError(f"Table for job {job_id} not found")

        try:
            rows_result = await self.db.execute(
                select(StagingRow)
                .where(StagingRow.job_id == job_id, StagingRow.is_valid == True)  # noqa: E712
                .order_by(StagingRow.file_id, StagingRow.row_index)
            )
            valid_rows = [
                row.parsed_json
                for row in rows_result.scalars().all()
                if isinstance(row.parsed_json, dict)
            ]

            inserted_count = 0
            if valid_rows:
                from app.models.generic_record import GenericRecord

                station = await self._get_generic_station(table.table_code, job.tenant_id)
                if station is None:
                    raise ValueError(
                        f"Station not found for table_code={table.table_code!r}, "
                        f"tenant_id={job.tenant_id}"
                    )

                schema = await self._get_active_station_schema_for_station(station.id)
                unique_key_fields: list[str] = []
                if schema and schema.unique_key_fields:
                    unique_key_fields = list(schema.unique_key_fields)

                for idx, row_data_dict in enumerate(valid_rows):
                    if unique_key_fields:
                        lot_no_raw = "_".join(
                            str(row_data_dict.get(f, "")) for f in unique_key_fields
                        ).strip("_") or str(idx)
                    else:
                        lot_no_raw = str(idx)
                    lot_no_norm = self._generic_lot_no_norm(lot_no_raw)

                    existing_stmt = select(GenericRecord).where(
                        GenericRecord.tenant_id == job.tenant_id,
                        GenericRecord.station_id == station.id,
                        GenericRecord.lot_no_raw == lot_no_raw,
                    )
                    existing_result = await self.db.execute(existing_stmt)
                    existing_rec = existing_result.scalar_one_or_none()
                    if existing_rec:
                        existing_rec.data = row_data_dict
                        existing_rec.updated_at = datetime.now(timezone.utc)
                    else:
                        self.db.add(
                            GenericRecord(
                                id=uuid.uuid4(),
                                tenant_id=job.tenant_id,
                                station_id=station.id,
                                schema_version_id=schema.id if schema else None,
                                lot_no_raw=lot_no_raw,
                                lot_no_norm=lot_no_norm,
                                data=row_data_dict,
                            )
                        )
                    inserted_count += 1
                await self.db.flush()
                logger.info(
                    f"Generic commit: wrote {inserted_count} rows to generic_records "
                    f"(table_code={table.table_code}, tenant={job.tenant_id})"
                )

            if inserted_count == 0:
                raise ValueError(
                    f"Commit wrote zero target rows for table_code={table.table_code}"
                )

            self._touch_status(
                job,
                ImportJobStatus.COMPLETED,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                actor_kind=actor_kind,
            )
            await self.db.commit()

            await write_audit_event_best_effort(
                tenant_id=job.tenant_id,
                actor_api_key_id=actor_api_key_id,
                actor_label_snapshot=actor_label_snapshot,
                request_id=None,
                method="INTERNAL",
                path=f"/internal/v2/import/jobs/{job.id}/status",
                status_code=0,
                action="import.job.status",
                metadata={
                    "job_id": str(job.id),
                    "from_status": str(ImportJobStatus.COMMITTING),
                    "to_status": getattr(job.status, "name", str(job.status)),
                    "actor_kind": actor_kind,
                    "inserted_count": inserted_count,
                },
            )
            return job

        except Exception as e:
            logger.exception(f"Error committing job {job_id}: {e}")
            await self.db.rollback()
            result = await self.db.execute(select(ImportJob).where(ImportJob.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                prev_status = job.status
                self._touch_status(
                    job,
                    ImportJobStatus.FAILED,
                    actor_api_key_id=actor_api_key_id,
                    actor_label_snapshot=actor_label_snapshot,
                    actor_kind=actor_kind,
                )
                job.error_summary = {"error": str(e)}
                await self.db.commit()
            else:
                prev_status = None

            if job:
                await write_audit_event_best_effort(
                    tenant_id=job.tenant_id,
                    actor_api_key_id=actor_api_key_id,
                    actor_label_snapshot=actor_label_snapshot,
                    request_id=None,
                    method="INTERNAL",
                    path=f"/internal/v2/import/jobs/{job.id}/status",
                    status_code=0,
                    action="import.job.status",
                    metadata={
                        "job_id": str(job.id),
                        "from_status": getattr(prev_status, "name", str(prev_status)),
                        "to_status": getattr(job.status, "name", str(job.status)),
                        "actor_kind": actor_kind,
                        "error": str(e)[:200],
                    },
                )
            raise e

    async def _get_generic_station(
        self, table_code: str, tenant_id: uuid.UUID
    ) -> Any | None:
        """Look up a Station by code for a given tenant."""
        from app.models.station import Station

        stmt = select(Station).where(
            Station.tenant_id == tenant_id,
            Station.code == table_code,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_active_station_schema_for_station(
        self, station_id: uuid.UUID
    ) -> Any | None:
        """Return the active StationSchema for a station (highest version, is_active=True)."""
        from app.models.station import StationSchema

        stmt = (
            select(StationSchema)
            .where(
                StationSchema.station_id == station_id,
                StationSchema.is_active == True,  # noqa: E712
            )
            .order_by(StationSchema.version.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _generic_lot_no_norm(raw: str) -> int:
        """Stable numeric value for a generic lot_no_raw (digits only, or 0)."""
        digits = "".join(c for c in str(raw) if c.isdigit())
        return int(digits) if digits else 0

