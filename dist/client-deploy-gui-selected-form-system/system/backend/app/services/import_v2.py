import csv
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.core.schema_registry import TableRegistry
from app.models.import_job import ImportJob, ImportJobStatus, StagingRow
from app.services.audit_events import write_audit_event_best_effort
from app.services.csv_field_mapper import CSVFieldMapper, csv_field_mapper
from app.utils.normalization import normalize_lot_no

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

    def _compose_p2_trace_lot_no(
        self, lot_no_norm: int | str | None, winder_number: int | str | None
    ) -> str | None:
        if lot_no_norm is None or winder_number is None:
            return None
        lot = str(lot_no_norm).strip()
        if not lot:
            return None
        try:
            w = int(winder_number)
        except (TypeError, ValueError):
            return None
        if w <= 0:
            return None
        return f"{lot}_{w:02d}"

    def _extract_file_lot_no_raw_or_raise(
        self, row_data: list[dict[str, Any]], *, table_code: str
    ) -> str:
        """Extract a single lot_no for a file from row content.

        For P1/P2 we expect one lot per file.
        """
        seen: set[str] = set()
        for row in row_data or []:
            lot_raw = self._extract_lot_no_from_row_dict(row)
            if not lot_raw:
                continue
            canonical = self._canonicalize_lot_no_raw(lot_raw)
            if canonical:
                seen.add(canonical)

        if not seen:
            raise ValueError(f"{table_code} file is missing lot_no in content")
        if len(seen) > 1:
            raise ValueError(
                f"{table_code} file contains multiple lot_no values: {sorted(seen)}"
            )
        return next(iter(seen))

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
        job.last_status_changed_at = datetime.now(UTC)
        job.last_status_actor_kind = actor_kind
        job.last_status_actor_api_key_id = actor_api_key_id
        job.last_status_actor_label_snapshot = actor_label_snapshot

    def _normalize_p3_lot_no_raw(self, val: str) -> str:
        """P3 專用 lot_no 正規化（僅取前兩段），例如：2507173_02_18 -> 2507173_02"""
        s = str(val or "").strip()
        if not s:
            return s
        parts = re.findall(r"\d+", s)
        if len(parts) >= 2 and len(parts[0]) >= 6 and len(parts[1]) <= 2:
            return f"{parts[0]}_{parts[1].zfill(2)}"
        return s

    def _compose_p3_item_product_id(
        self,
        production_date_yyyymmdd: int | None,
        machine_no: Any,
        mold_no: Any,
        production_lot: Any,
    ) -> str | None:
        """Compose canonical per-row P3 product_id: YYYYMMDD_machine_mold_lot."""
        try:
            ymd_i = int(production_date_yyyymmdd or 0)
        except (TypeError, ValueError):
            return None
        if ymd_i <= 0:
            return None

        machine = str(machine_no or "").strip()
        mold = str(mold_no or "").strip()
        if not machine or not mold:
            return None

        try:
            lot_i = int(float(production_lot))
        except (TypeError, ValueError):
            return None

        return f"{ymd_i:08d}_{machine}_{mold}_{lot_i}"

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

        Used for "mostly same" cases: same business key (P1: lot; P2: lot+winder)
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
        lot_no_pattern = re.compile(r"^\d{7}_\d{2}$")
        lot_no_flexible_pattern = re.compile(r"^(\d{7})[-_](\d{1,2})(?:[-_].+)?$")

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

                # LOT NO validation (all tables): extract from row content
                lot_no_val = self._extract_lot_no_from_row_dict(
                    data if isinstance(data, dict) else {}
                )
                if not lot_no_val:
                    errors.append(
                        {
                            "field": "lot_no",
                            "message": "Missing lot_no in row content",
                        }
                    )
                else:
                    m = lot_no_flexible_pattern.match(str(lot_no_val).strip())
                    canonical = f"{m.group(1)}_{m.group(2).zfill(2)}" if m else None

                    if table.table_code in ("P1", "P2"):
                        # P1/P2 enforce strict 7+2 format
                        if not canonical or not lot_no_pattern.match(canonical):
                            errors.append(
                                {
                                    "field": "lot_no",
                                    "message": f"Invalid lot_no format: {lot_no_val}",
                                }
                            )
                    elif table.table_code == "P3":
                        # P3 allows suffixes (e.g. 2507173_02_18) but must still start with 7+2
                        if not canonical:
                            errors.append(
                                {
                                    "field": "lot_no",
                                    "message": f"Invalid lot_no format: {lot_no_val}",
                                }
                            )

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
        """
        Commit valid staging rows to target tables.
        """
        logger.info(f"Starting commit_job for {job_id}")
        # 1. Fetch Job
        stmt = (
            select(ImportJob)
            .options(selectinload(ImportJob.files))
            .where(ImportJob.id == job_id)
        )
        result = await self.db.execute(stmt)
        job = result.scalar_one_or_none()

        if not job:
            logger.error(f"Import job {job_id} not found")
            raise ValueError(f"Import job {job_id} not found")

        if (
            job.status != ImportJobStatus.READY
            and job.status != ImportJobStatus.COMMITTING
        ):
            logger.error(f"Job {job_id} is not ready to commit (status: {job.status})")
            raise ValueError(
                f"Job {job_id} is not ready to commit (status: {job.status})"
            )

        # Update status (only when transitioning from READY)
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

        # Get Table Code
        table_stmt = select(TableRegistry).where(TableRegistry.id == job.table_id)
        table_result = await self.db.execute(table_stmt)
        table = table_result.scalar_one_or_none()

        if not table:
            logger.error(f"Table for job {job_id} not found")
            raise ValueError(f"Table for job {job_id} not found")

        logger.info(
            f"Commit job {job_id}: Table code {table.table_code}, Files: {len(job.files)}"
        )

        try:
            # Collect per-key rows across files in the *same job* for dedupe/merge.
            # This helps when users upload split files or mostly-identical files.
            p1_rows_by_lot_norm: dict[int, list[dict[str, Any]]] = {}
            p1_lot_raw_by_norm: dict[int, str] = {}

            p2_rows_by_key: dict[tuple[int, int], list[dict[str, Any]]] = {}
            p2_lot_raw_by_norm: dict[int, str] = {}

            # Process by file
            for file_record in job.files:
                logger.info(
                    f"Processing file {file_record.filename} (ID: {file_record.id})"
                )
                # Get staging rows
                rows_stmt = (
                    select(StagingRow)
                    .where(
                        StagingRow.file_id == file_record.id,
                        StagingRow.is_valid == True,
                    )
                    .order_by(StagingRow.row_index)
                )

                rows_result = await self.db.execute(rows_stmt)
                rows = rows_result.scalars().all()

                if not rows:
                    continue

                # Prepare Data
                row_data = [r.parsed_json for r in rows]

                if table.table_code == "P1":
                    from app.models.p1_record import P1Record

                    lot_no_raw = self._extract_file_lot_no_raw_or_raise(
                        row_data, table_code="P1"
                    )
                    lot_no_norm = normalize_lot_no(lot_no_raw)
                    p1_lot_raw_by_norm.setdefault(lot_no_norm, lot_no_raw)
                    p1_rows_by_lot_norm.setdefault(lot_no_norm, []).extend(
                        [r for r in row_data if isinstance(r, dict)]
                    )
                    continue

                elif table.table_code == "P2":
                    from app.models.p2_item_v2 import P2ItemV2
                    from app.models.p2_record import P2Record

                    lot_no_raw = self._extract_file_lot_no_raw_or_raise(
                        row_data, table_code="P2"
                    )
                    lot_no_norm = normalize_lot_no(lot_no_raw)

                    p2_lot_raw_by_norm.setdefault(lot_no_norm, lot_no_raw)

                    # P2 匯入：
                    # - 支援「單檔單一 winder」（例如檔名含 _05 或內容只有一列）
                    # - 也支援「單檔多個 winder」（內容多列且每列帶 winder_number）
                    #
                    # 目前資料模型以 (tenant_id, lot_no_norm, winder_number) 為 key 建立/更新 P2Record。
                    winder_num_for_file = self._extract_p2_info(
                        file_record.filename, row_data
                    )

                    def _extract_winder_from_row(row: dict[str, Any]) -> int | None:
                        for field in CSVFieldMapper.WINDER_NUMBER_FIELD_NAMES:
                            v = row.get(field)
                            if v is None or v == "":
                                continue
                            try:
                                return int(float(v))
                            except (ValueError, TypeError):
                                continue
                        return None

                    rows_by_winder: dict[int, list[dict[str, Any]]] = {}
                    if row_data:
                        for r0 in row_data:
                            if not isinstance(r0, dict):
                                continue
                            w = _extract_winder_from_row(r0)
                            if w is None:
                                continue
                            rows_by_winder.setdefault(w, []).append(r0)

                    # 若內容沒有任何可用的 winder_number，視為單一 winder 檔案（用檔名/第一列推導的 winder）
                    if not rows_by_winder and row_data:
                        rows_by_winder[winder_num_for_file] = [
                            r for r in row_data if isinstance(r, dict)
                        ]

                    if not rows_by_winder:
                        logger.warning(
                            f"P2 import has no rows (filename={file_record.filename})"
                        )
                        continue

                    for winder_num, winder_rows in rows_by_winder.items():
                        if not winder_rows:
                            continue
                        key = (lot_no_norm, int(winder_num))
                        p2_rows_by_key.setdefault(key, []).extend(
                            [r for r in winder_rows if isinstance(r, dict)]
                        )
                    continue

                elif table.table_code == "P3":
                    from app.models.p3_item_v2 import P3ItemV2
                    from app.models.p3_record import P3Record

                    # P3 改用混合架構: 依 lot_no 分組 → 每個 lot 1筆 p3_records + N筆 p3_items_v2
                    # 注意：你的檔名 (例如 P3_0902_P24 copy.csv) 不包含 lot_no，不能用檔名推 lot。

                    p3_info = self._extract_p3_info(file_record.filename, row_data)

                    # Group rows by lot_no_norm extracted from row content
                    groups: dict[int, dict[str, Any]] = {}
                    for row in row_data:
                        # Skip completely blank CSV rows (common in real exports)
                        if (
                            not row
                            or not isinstance(row, dict)
                            or all(
                                (v is None) or (str(v).strip() == "")
                                for v in row.values()
                            )
                        ):
                            continue

                        lot_from_row = None
                        for field in CSVFieldMapper.LOT_NO_FIELD_NAMES:
                            if field in row and row[field]:
                                lot_from_row = str(row[field]).strip()
                                break
                        if not lot_from_row:
                            # Do NOT fallback to filename-derived lot for P3 (e.g. P3_0902_P02.csv)
                            # to avoid creating a spurious group/record like lot_no=0902_P02.
                            logger.warning(
                                f"P3 row missing lot_no; skipping row (filename={file_record.filename})"
                            )
                            continue

                        # P3 lot_no 可能帶尾碼（如 _18），分組與 records 關聯只需要前兩段
                        lot_from_row = self._normalize_p3_lot_no_raw(lot_from_row)

                        lot_norm_row = normalize_lot_no(lot_from_row)
                        if lot_norm_row not in groups:
                            groups[lot_norm_row] = {
                                "lot_no_raw": lot_from_row,
                                "rows": [],
                            }
                        groups[lot_norm_row]["rows"].append(row)

                    if not groups:
                        logger.warning(
                            f"P3 import produced no groups (filename={file_record.filename})"
                        )

                    for lot_norm_row, payload in groups.items():
                        group_lot_raw = payload["lot_no_raw"]
                        group_rows = payload["rows"]

                        # Check existence of P3Record for this lot
                        existing_stmt = select(P3Record).where(
                            P3Record.tenant_id == job.tenant_id,
                            P3Record.lot_no_norm == lot_norm_row,
                            P3Record.machine_no == p3_info["machine_no"],
                            P3Record.mold_no == p3_info["mold_no"],
                            P3Record.production_date_yyyymmdd
                            == p3_info["production_date_yyyymmdd"],
                        )
                        existing_result = await self.db.execute(existing_stmt)
                        p3_record = existing_result.scalar_one_or_none()

                        # Generate product_id for P3Record
                        production_date_yyyymmdd = int(
                            p3_info.get("production_date_yyyymmdd") or 0
                        )
                        date_str = (
                            f"{production_date_yyyymmdd:08d}"
                            if production_date_yyyymmdd
                            else ""
                        )
                        lot_part_raw = None
                        if group_rows:
                            for field in CSVFieldMapper.LOT_FIELD_NAMES:
                                if field in group_rows[0] and group_rows[0][field]:
                                    lot_part_raw = group_rows[0][field]
                                    break
                        lot_part: int
                        try:
                            lot_part = (
                                int(float(lot_part_raw))
                                if lot_part_raw is not None
                                else 0
                            )
                        except (ValueError, TypeError):
                            lot_part = 0

                        # product_id 唯一格式：YYYYMMDD_machine_mold_lot
                        product_id = f"{date_str}_{p3_info.get('machine_no')}_{p3_info.get('mold_no')}_{lot_part}"

                        if not p3_record:
                            p3_record = P3Record(
                                id=uuid.uuid4(),
                                tenant_id=job.tenant_id,
                                lot_no_raw=group_lot_raw,
                                lot_no_norm=lot_norm_row,
                                schema_version_id=job.schema_version_id,
                                production_date_yyyymmdd=p3_info[
                                    "production_date_yyyymmdd"
                                ],
                                machine_no=p3_info["machine_no"],
                                mold_no=p3_info["mold_no"],
                                product_id=product_id,
                                extras={},
                            )
                            self.db.add(p3_record)
                            await self.db.flush()
                        else:
                            p3_record.product_id = product_id
                            p3_record.updated_at = func.now()

                        # Delete existing items for this record (if re-importing)
                        await self.db.execute(
                            delete(P3ItemV2).where(
                                P3ItemV2.p3_record_id == p3_record.id
                            )
                        )
                        # Ensure DELETE is flushed before INSERT to avoid unique constraint conflicts
                        await self.db.flush()

                        # Create P3ItemV2 for each row
                        for row_idx, row in enumerate(group_rows, start=1):
                            # Extract fields from row
                            item_product_id = None
                            item_lot_no = group_lot_raw
                            item_production_date = None
                            item_machine_no = p3_info["machine_no"]
                            item_mold_no = p3_info["mold_no"]
                            item_production_lot = None
                            item_source_winder = None
                            item_specification = None
                            item_bottom_tape_lot = None

                            # Map fields from row
                            for field in CSVFieldMapper.PRODUCT_ID_FIELD_NAMES:
                                if field in row and row[field]:
                                    item_product_id = str(row[field]).strip()
                                    break

                            for field in CSVFieldMapper.LOT_NO_FIELD_NAMES:
                                if field in row and row[field]:
                                    item_lot_no = str(row[field]).strip()
                                    break

                            for field in CSVFieldMapper.DATE_FIELD_NAMES:
                                if field in row and row[field]:
                                    try:
                                        ymd = csv_field_mapper._normalize_date_to_yyyymmdd(
                                            str(row[field])
                                        )
                                        if ymd:
                                            year = ymd // 10000
                                            month = (ymd % 10000) // 100
                                            day = ymd % 100
                                            from datetime import date

                                            item_production_date = date(
                                                year, month, day
                                            )
                                            break
                                    except Exception:
                                        pass

                            for field in CSVFieldMapper.MACHINE_NO_FIELD_NAMES:
                                if field in row and row[field]:
                                    item_machine_no = str(row[field]).strip()
                                    break

                            for field in CSVFieldMapper.MOLD_NO_FIELD_NAMES:
                                if field in row and row[field]:
                                    item_mold_no = str(row[field]).strip()
                                    break

                            for field in CSVFieldMapper.LOT_FIELD_NAMES:
                                if field in row and row[field]:
                                    try:
                                        item_production_lot = int(float(row[field]))
                                    except (ValueError, TypeError):
                                        pass
                                    break

                            # If source CSV doesn't provide row product_id, compose one
                            # from per-row attributes to keep row-level identity stable.
                            if not item_product_id:
                                item_ymd = None
                                if item_production_date is not None:
                                    item_ymd = (
                                        item_production_date.year * 10000
                                        + item_production_date.month * 100
                                        + item_production_date.day
                                    )
                                if not item_ymd:
                                    item_ymd = p3_info.get("production_date_yyyymmdd")

                                item_product_id = self._compose_p3_item_product_id(
                                    item_ymd,
                                    item_machine_no,
                                    item_mold_no,
                                    item_production_lot,
                                )

                            for field in CSVFieldMapper.SOURCE_WINDER_FIELD_NAMES:
                                if field in row and row[field]:
                                    try:
                                        item_source_winder = int(float(row[field]))
                                    except (ValueError, TypeError):
                                        pass
                                    break

                            for field in CSVFieldMapper.SPECIFICATION_FIELD_NAMES:
                                if field in row and row[field]:
                                    item_specification = str(row[field]).strip()
                                    break

                            for field in CSVFieldMapper.BOTTOM_TAPE_LOT_FIELD_NAMES:
                                if field in row and row[field]:
                                    item_bottom_tape_lot = str(row[field]).strip()
                                    break

                            # Create P3ItemV2
                            p3_item = P3ItemV2(
                                id=uuid.uuid4(),
                                p3_record_id=p3_record.id,
                                tenant_id=job.tenant_id,
                                row_no=row_idx,
                                product_id=item_product_id,
                                lot_no=item_lot_no,
                                production_date=item_production_date,
                                machine_no=item_machine_no,
                                mold_no=item_mold_no,
                                production_lot=item_production_lot,
                                source_winder=item_source_winder,
                                specification=item_specification,
                                bottom_tape_lot=item_bottom_tape_lot,
                                row_data=row,
                            )
                            self.db.add(p3_item)

            # Apply merged + deduped rows to DB (P1/P2).
            if table.table_code == "P1":
                from app.models.p1_record import P1Record

                for lot_no_norm, rows_for_lot in p1_rows_by_lot_norm.items():
                    lot_no_raw = p1_lot_raw_by_norm.get(lot_no_norm) or str(lot_no_norm)
                    # Business-key merge: one lot -> one merged row (but keep list wrapper for compatibility)
                    deduped_rows = self._dedupe_rows_exact(rows_for_lot)
                    merged_row, conflict_count = self._merge_rows_prefer_complete(
                        deduped_rows
                    )
                    if conflict_count:
                        logger.info(
                            f"P1 dedupe merge conflicts (tenant={job.tenant_id}, lot_no_norm={lot_no_norm}): {conflict_count}"
                        )
                    merged_rows = [merged_row] if merged_row else []

                    existing_stmt = select(P1Record).where(
                        P1Record.tenant_id == job.tenant_id,
                        P1Record.lot_no_norm == lot_no_norm,
                    )
                    existing_result = await self.db.execute(existing_stmt)
                    existing_record = existing_result.scalar_one_or_none()

                    if existing_record:
                        existing_record.lot_no_raw = lot_no_raw
                        existing_record.extras = {"rows": merged_rows}
                        existing_record.updated_at = func.now()
                    else:
                        self.db.add(
                            P1Record(
                                id=uuid.uuid4(),
                                tenant_id=job.tenant_id,
                                lot_no_raw=lot_no_raw,
                                lot_no_norm=lot_no_norm,
                                schema_version_id=job.schema_version_id,
                                extras={"rows": merged_rows},
                            )
                        )

            if table.table_code == "P2":
                from app.models.p2_item_v2 import P2ItemV2
                from app.models.p2_record import P2Record

                for (lot_no_norm, winder_num), rows_for_key in p2_rows_by_key.items():
                    lot_no_raw = p2_lot_raw_by_norm.get(lot_no_norm) or str(lot_no_norm)
                    # Business-key merge: one (lot,winder) -> one merged row (but keep list wrapper)
                    deduped_rows = self._dedupe_rows_exact(rows_for_key)
                    merged_row, conflict_count = self._merge_rows_prefer_complete(
                        deduped_rows
                    )
                    if conflict_count:
                        logger.info(
                            f"P2 dedupe merge conflicts (tenant={job.tenant_id}, lot_no_norm={lot_no_norm}, winder={winder_num}): {conflict_count}"
                        )
                    merged_rows = [merged_row] if merged_row else []
                    if not merged_rows:
                        continue

                    existing_stmt = select(P2Record).where(
                        P2Record.tenant_id == job.tenant_id,
                        P2Record.lot_no_norm == lot_no_norm,
                        P2Record.winder_number == int(winder_num),
                    )
                    existing_result = await self.db.execute(existing_stmt)
                    p2_record = existing_result.scalar_one_or_none()

                    if not p2_record:
                        p2_record = P2Record(
                            id=uuid.uuid4(),
                            tenant_id=job.tenant_id,
                            lot_no_raw=lot_no_raw,
                            lot_no_norm=lot_no_norm,
                            schema_version_id=job.schema_version_id,
                            winder_number=int(winder_num),
                            extras={"rows": merged_rows},
                        )
                        self.db.add(p2_record)
                        await self.db.flush()
                    else:
                        p2_record.lot_no_raw = lot_no_raw
                        p2_record.extras = {"rows": merged_rows}
                        p2_record.updated_at = func.now()

                    await self.db.execute(
                        delete(P2ItemV2).where(P2ItemV2.p2_record_id == p2_record.id)
                    )
                    await self.db.flush()

                    row = merged_rows[0]
                    p2_item_ymd = self._extract_p2_item_production_date_yyyymmdd(row)
                    trace_lot_no = self._compose_p2_trace_lot_no(
                        p2_record.lot_no_raw, int(winder_num)
                    )
                    p2_item = P2ItemV2(
                        id=uuid.uuid4(),
                        p2_record_id=p2_record.id,
                        tenant_id=job.tenant_id,
                        winder_number=int(winder_num),
                        production_date_yyyymmdd=p2_item_ymd,
                        trace_lot_no=trace_lot_no,
                        row_data=row,
                    )

                    slitting_result = self._extract_p2_item_slitting_result(row)
                    if slitting_result is not None:
                        p2_item.slitting_result = slitting_result

                    for field in [
                        "sheet_width",
                        "thickness1",
                        "thickness2",
                        "thickness3",
                        "thickness4",
                        "thickness5",
                        "thickness6",
                        "thickness7",
                        "appearance",
                        "rough_edge",
                    ]:
                        if field in row and row[field]:
                            try:
                                setattr(p2_item, field, float(row[field]))
                            except (ValueError, TypeError):
                                pass

                    self.db.add(p2_item)

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
                    "from_status": getattr(
                        ImportJobStatus.COMMITTING,
                        "name",
                        str(ImportJobStatus.COMMITTING),
                    ),
                    "to_status": getattr(job.status, "name", str(job.status)),
                    "actor_kind": actor_kind,
                },
            )
            return job

        except Exception as e:
            logger.exception(f"Error committing job {job_id}: {e}")
            # Ensure no partial writes are committed.
            await self.db.rollback()

            # Re-fetch the job in a clean transaction, then mark FAILED.
            stmt = select(ImportJob).where(ImportJob.id == job_id)
            result = await self.db.execute(stmt)
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

    def _extract_lot_no(self, filename: str) -> str:
        stem = Path(filename).stem

        # Test scripts may copy files with a leading prefix like "_import_test_".
        # Strip it first so the regular P1_/P2_/P3_ parsing still works.
        for test_prefix in ["_import_test_", "import_test_"]:
            if stem.lower().startswith(test_prefix):
                stem = stem[len(test_prefix) :]
                break
        for prefix in ["P1_", "P2_", "P3_", "QC_"]:
            if stem.upper().startswith(prefix):
                stem = stem[len(prefix) :]
                break

        # Normalize P1/P2 style lot numbers: keep only the first 7+2 segment
        # e.g. 2507173_02_10 -> 2507173_02
        m = re.match(r"^(\d{7})_(\d{1,2})(?:_.+)?$", stem)
        if m:
            return f"{m.group(1)}_{m.group(2).zfill(2)}"

        return stem

    def _extract_p2_info(self, filename: str, row_data: list[dict[str, Any]]) -> int:
        # Try to get winder from filename
        # Format: P2_LotNo_Winder.csv or P2_LotNo.csv (if winder in content)
        parts = Path(filename).stem.split("_")
        winder = None

        # Try last part of filename if it's a number and length is small (e.g. 1, 01, 17)
        if len(parts) >= 3:
            last_part = parts[-1]
            if last_part.isdigit() and len(last_part) <= 2:
                winder = int(last_part)

        if winder is not None:
            return winder

        # Try to get from content (first row)
        if row_data:
            first_row = row_data[0]
            for field in CSVFieldMapper.WINDER_NUMBER_FIELD_NAMES:
                if field in first_row and first_row[field]:
                    try:
                        return int(first_row[field])
                    except (ValueError, TypeError):
                        pass

        # Default or Error
        # For now, default to 1 if not found, but log warning
        logger.warning(
            f"Could not extract winder number for {filename}, defaulting to 1"
        )
        return 1

    def _extract_p2_item_production_date_yyyymmdd(
        self, row: dict[str, Any] | None
    ) -> int | None:
        if not isinstance(row, dict):
            return None

        candidates: list[Any] = []
        for key in [
            "Slitting date",
            "Slitting Date",
            "slitting date",
            "slitting_date",
            "Slitting Time",
            "slitting_time",
            "分條時間",
            "production_date",
            "Production Date",
            "生產日期",
            "date",
            "Date",
        ]:
            if key in row and row[key] is not None and str(row[key]).strip():
                candidates.append(row[key])

        nested_rows = row.get("rows")
        if isinstance(nested_rows, list):
            for nested in nested_rows:
                if not isinstance(nested, dict):
                    continue
                for key in [
                    "Slitting date",
                    "Slitting Date",
                    "slitting date",
                    "slitting_date",
                    "Slitting Time",
                    "slitting_time",
                    "分條時間",
                    "production_date",
                    "Production Date",
                    "生產日期",
                    "date",
                    "Date",
                ]:
                    if (
                        key in nested
                        and nested[key] is not None
                        and str(nested[key]).strip()
                    ):
                        candidates.append(nested[key])

        for v in candidates:
            ymd = csv_field_mapper._normalize_date_to_yyyymmdd(str(v))
            if ymd:
                return int(ymd)
        return None

    def _extract_p2_item_slitting_result(
        self, row: dict[str, Any] | None
    ) -> float | None:
        if not isinstance(row, dict):
            return None

        candidates: list[Any] = []
        for key in [
            "Striped Results",
            "Striped results",
            "striped results",
            "striped result",
            "Slitting Result",
            "slitting result",
            "Slitting result",
            "slitting_result",
            "分條結果",
            "分條結果(成品)",
        ]:
            if key in row and row[key] is not None and str(row[key]).strip():
                candidates.append(row[key])

        nested_rows = row.get("rows")
        if isinstance(nested_rows, list):
            for nested in nested_rows:
                if not isinstance(nested, dict):
                    continue
                for key in [
                    "Striped Results",
                    "Striped results",
                    "striped results",
                    "striped result",
                    "Slitting Result",
                    "slitting result",
                    "slitting_result",
                    "分條結果",
                    "分條結果(成品)",
                ]:
                    if (
                        key in nested
                        and nested[key] is not None
                        and str(nested[key]).strip()
                    ):
                        candidates.append(nested[key])

        for v in candidates:
            try:
                value = float(v)
                if value.is_integer():
                    return int(value)
                return value
            except (ValueError, TypeError):
                continue
        return None

    def _extract_p3_info(
        self, filename: str, row_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        info = {
            "production_date_yyyymmdd": 0,
            "machine_no": "UNKNOWN",
            "mold_no": "UNKNOWN",
        }

        # Try filename first
        # P3_YYYYMDD_MM_WW.csv
        parts = Path(filename).stem.split("_")

        if len(parts) >= 4:
            # P3_2507173_02_17 -> Date: 2507173, Machine: 02
            # Wait, 2507173 is 7 digits. YYYYMDD? 2025-07-17?
            # If so, YYYYMMDD = 20250717
            date_str = parts[1]
            machine_str = parts[2]

            if len(date_str) == 7:
                # 2507173 -> 20250717
                # First 2 digits are year (25 -> 2025)
                # Next 2 are month (07)
                # Next 2 are day (17)
                # Last digit? 3?
                # Wait, PRD says "YYYYMDD".
                # 2024 11 01 2 -> 2411012.
                # 24 (Year) 11 (Month) 01 (Day) 2 (Shift/Seq?)
                # So date is 20241101.

                try:
                    year = int("20" + date_str[:2])
                    month = int(date_str[2:4])
                    day = int(date_str[4:6])
                    info["production_date_yyyymmdd"] = year * 10000 + month * 100 + day
                except ValueError:
                    pass

            info["machine_no"] = machine_str

        elif len(parts) >= 3:
            # P3_0902_P24 -> Date: 0902, Machine: P24
            date_str = parts[1]
            machine_str = parts[2]

            # 僅有 MMDD 無法推導年份；禁止用 now/year 猜測，以免污染資料。
            # 正確年份應從內容欄位（例如 114年09月02日）解析。
            # 因此這裡不設定 production_date_yyyymmdd。
            info["machine_no"] = machine_str

        # Try content overrides (prefer content values over filename parsing)
        if row_data:
            first_row = row_data[0]
            # Date (year-month-day etc.)
            for field in CSVFieldMapper.DATE_FIELD_NAMES:
                if field in first_row and first_row[field]:
                    try:
                        ymd = csv_field_mapper._normalize_date_to_yyyymmdd(
                            str(first_row[field])
                        )
                        if ymd:
                            info["production_date_yyyymmdd"] = ymd
                            break
                    except Exception:
                        pass

            # Machine
            for field in CSVFieldMapper.MACHINE_NO_FIELD_NAMES:
                if field in first_row and first_row[field]:
                    info["machine_no"] = str(first_row[field]).strip()
                    break

            # Mold
            for field in CSVFieldMapper.MOLD_NO_FIELD_NAMES:
                if field in first_row and first_row[field]:
                    info["mold_no"] = str(first_row[field]).strip()
                    break

            # Lot / production_lot
            for field in CSVFieldMapper.LOT_FIELD_NAMES:
                if field in first_row and first_row[field]:
                    try:
                        info["lot"] = int(float(first_row[field]))
                    except (ValueError, TypeError):
                        info["lot"] = str(first_row[field])
                    break

        # 最終保護：若仍無法取得日期，直接讓匯入失敗，避免寫入錯誤年份。
        if not info.get("production_date_yyyymmdd"):
            raise ValueError(
                f"P3 production_date missing or unparseable for file={filename}; "
                f"expected a parsable date in content (e.g. 114年09月02日 / 114/09/02)."
            )

        return info
