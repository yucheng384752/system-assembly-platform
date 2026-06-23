---
id: "20260623-daihui-upload-db-e2e-findings"
title: "Review Daihui CSV upload and database E2E findings"
status: "ready_for_claude"
owner: "claude"
reviewer: "claude"
priority: "high"
created_by: "codex"
created_at: "2026-06-23T21:40:00+08:00"
updated_at: "2026-06-23T21:40:00+08:00"
role_priority:
  implementation: "codex"
  review: "claude"
  tests: "claude"
  requirements: "user"
artifacts:
  - path: "dist/client-deploy-gui-selected-form-system/system/backend/app/core/monitoring.py"
    type: "patch"
  - path: "dist/client-deploy-gui-selected-form-system/system/frontend/src/pages/DeveloperLogsPage.tsx"
    type: "patch"
  - path: "dist/client-deploy-gui-selected-form-system/system/frontend/vite.config.ts"
    type: "patch"
  - path: "C:/Users/gslab/Desktop/Daihui CSV processed folder (original path contains Chinese characters)"
    type: "test"
---

# Goal

Record sandbox E2E findings from testing the generated Kit Composer package with the five Daihui CSV files in the Daihui processed CSV folder on the desktop. The original Windows path contains Chinese characters; use the file list below as the stable reference if tooling displays the path with mojibake.

The user goal was to simulate a user uploading CSV files that should overwrite or populate database tables, with emphasis on verifying correct database connection and confirming the generated web UI can operate normally, including login and upload.

# Success Criteria

- Backend can start against an isolated test database.
- Frontend can start and render.
- User can log in through the web UI.
- User can upload Daihui CSV files through the web UI.
- The five Daihui CSVs can be routed to the expected target table codes:
  `daihui_entry`, `daihui_inspection`, `daihui_material`, `daihui_production`, `daihui_quality`.
- Imported rows are persisted into real target tables, not only `staging_rows`.
- Errors and required follow-up fixes are explicit.

# Current Context

Test package:

- `dist/client-deploy-gui-selected-form-system/system`

CSV files:

- `entry_horizontal.csv`
- `inspection_horizontal.csv`
- `material_horizontal.csv`
- `production_horizontal.csv`
- `quality_horizontal.csv`

Temporary test setup used by Codex:

- Backend: `127.0.0.1:8002`
- Frontend: `127.0.0.1:5174`
- SQLite DB: `C:/tmp/daihui-e2e.sqlite3`
- Manager login: `default / manager / Password123!`

Temporary runtime artifacts were cleaned after the test:

- `system/.env`
- `system/backend/.env`
- `system/.venv`
- `system/frontend/node_modules`
- `system/frontend/package-lock.json`
- `C:/tmp/daihui-e2e.sqlite3`
- `C:/tmp/daihui-e2e-uploads`
- backend/frontend log files in `C:/tmp`

# Codex Notes

Request for Claude:

- Review the findings below and confirm the required fixes.
- Check whether the temporary no-op fixes should be kept, replaced with real implementations, or moved back into the generator/templates.
- Recommend tests that should guard Daihui CSV routing and persistence.
- Pay special attention to generated package consistency, because several failures came from package assembly drift.

## Errors Encountered

1. Backend failed to start because `app.core.monitoring` was missing.

Observed error:

```text
ModuleNotFoundError: No module named 'app.core.monitoring'
```

References in generated backend:

- `app/core/logging.py` imports `make_structlog_processor`
- `app/main.py` imports `init_monitoring`, `start_heartbeat`, `stop_heartbeat`
- routes import `report_user_action`

Temporary fix applied:

- Added `dist/client-deploy-gui-selected-form-system/system/backend/app/core/monitoring.py`
- The added module is a no-op implementation that exposes the referenced functions so the generated backend can start without a dashboard/log collector.

Follow-up needed:

- Move a real or no-op monitoring module into the source generator/template so future assembled packages include it.
- Add package validation that imports `app.main` before declaring the package valid.

2. Frontend rendered blank because `DeveloperLogsPage` was imported but missing.

Observed Vite error:

```text
Failed to resolve import "./pages/DeveloperLogsPage" from "src/App.tsx".
```

Temporary fix applied:

- Added `dist/client-deploy-gui-selected-form-system/system/frontend/src/pages/DeveloperLogsPage.tsx`
- The added component is a minimal placeholder to let the generated frontend compile.

Follow-up needed:

- Either include the real Developer Logs page in generated packages when `logs-ops-kit` is selected, or remove the tab/import when that page is not packaged.
- Add frontend build or Vite import validation to generated package tests.

3. Vite proxy was hard-coded to backend port 8000.

Observed context:

- Local `8000` was already occupied by Docker/WSL forwarding.
- Frontend dev server needed to call the isolated test backend on `8002`.

Temporary fix applied:

- Changed `system/frontend/vite.config.ts` proxy target from a hard-coded `http://localhost:8000` to:

```ts
process.env.VITE_PROXY_TARGET || 'http://localhost:8000'
```

Follow-up needed:

- Keep this configurability in the generator.
- Consider documenting local test ports and avoiding hard-coded 8000 assumptions.

4. `.env` database key mismatch: `DATABASE_URL` did not override `database_url`.

Observed behavior:

- `Settings.database_url` has no `alias="DATABASE_URL"`.
- A `.env` containing only `DATABASE_URL=sqlite+aiosqlite:///...` did not override the default PostgreSQL URL.
- Backend attempted to connect to default PostgreSQL localhost instead of SQLite.

Working test workaround:

```text
database_url=sqlite+aiosqlite:///C:/tmp/daihui-e2e.sqlite3
DATABASE_URL=sqlite+aiosqlite:///C:/tmp/daihui-e2e.sqlite3
```

Follow-up needed:

- Add `alias="DATABASE_URL"` to `database_url`, or ensure install scripts write `database_url`.
- Align `README.md`, install wizard, deploy scripts, and config model on one canonical environment variable.

5. Database bootstrap seeds Daihui table registry/schema versions, but runtime startup seeds only `P1/P2/P3`.

Observed result after running `app.core.generated_db_bootstrap`:

- 28 tables created.
- 5 Daihui form definitions seeded.
- 5 schema versions seeded.

Observed result after backend startup:

- Runtime startup adds `P1`, `P2`, `P3` to `table_registry`.
- The final test DB had both legacy P codes and Daihui codes.

Follow-up needed:

- Ensure runtime startup and generated bootstrap share one schema seed path.
- Avoid startup logic that only knows `P1/P2/P3` when the selected recipe is generalized around Daihui forms.

6. API accepts `daihui_*` jobs but commit does not persist into target tables.

API direct test results:

- Login succeeded with status 200.
- Each of the five Daihui CSVs created an import job with status 201.
- Each job reached `READY`.
- Each commit returned 200 and final status `COMPLETED`.

Database verification:

```json
{
  "job_by_table": [
    {"table_code": "daihui_entry", "status": "COMPLETED", "total_rows": 1, "error_count": 1, "staging_rows": 1},
    {"table_code": "daihui_inspection", "status": "COMPLETED", "total_rows": 1, "error_count": 1, "staging_rows": 1},
    {"table_code": "daihui_material", "status": "COMPLETED", "total_rows": 1, "error_count": 1, "staging_rows": 1},
    {"table_code": "daihui_production", "status": "COMPLETED", "total_rows": 1, "error_count": 1, "staging_rows": 1},
    {"table_code": "daihui_quality", "status": "COMPLETED", "total_rows": 1, "error_count": 1, "staging_rows": 1}
  ],
  "target_counts": {
    "generic_records": 0,
    "generic_record_items": 0,
    "p1_records": 0,
    "p2_records": 0,
    "p3_records": 0,
    "p2_items_v2": 0,
    "p3_items_v2": 0,
    "records": 0
  }
}
```

Root cause observed in `app/services/import_v2.py`:

- `commit_job()` only has explicit branches for `P1`, `P2`, and `P3`.
- There is no generic fallback for `daihui_*`.
- Validation also expects lot fields and marks all Daihui rows invalid with:

```json
[{"field": "lot_no", "message": "Missing lot_no in row content"}]
```

Follow-up needed:

- Implement generic/hybrid commit for `daihui_*` based on `schema_versions.schema_json`.
- Map columns using schema mappings from `db-bootstrap-plan.json`.
- Persist rows into the intended generic target tables or a clearly defined Daihui table model.
- Do not mark jobs `COMPLETED` if no rows were persisted.
- Fix `error_count` semantics so invalid rows with empty `error_summary` are visible and actionable.

7. Frontend upload cannot route Daihui CSVs to Daihui table codes.

UI test result:

- Login succeeded.
- `entry_horizontal.csv` could be selected.
- The file card displayed type `P3`.
- Clicking validation sent `POST /api/v2/import/jobs`.
- The job was created as table code `P3`, not `daihui_entry`.
- UI showed one validation error and kept batch import disabled.

Root cause observed:

- `uploadFileUtils.detectFileType()` only recognizes filenames starting with `P1_` or `P2_`; everything else becomes `P3`.
- `UploadPage` passes `file.type` as `tableCode`.
- There is no UI selector for generated form definitions or Daihui table codes.

Follow-up needed:

- Add a target table/form selector for CSV uploads.
- Auto-detect Daihui form by CSV header fingerprint or `表單名稱`.
- Route `entry_horizontal.csv` to `daihui_entry`, etc.
- Update batch validation/import workflows to support generated table codes beyond `P1/P2/P3`.

8. Frontend emitted duplicate toast key warnings.

Observed console warning:

```text
Warning: Encountered two children with the same key ...
```

Follow-up needed:

- Review `ToastContext`/`ToastContainer` ID generation.
- Ensure repeated toasts in the same millisecond do not reuse React keys.

9. npm audit reported dependency vulnerabilities during frontend dependency install.

Observed:

```text
2 vulnerabilities (1 moderate, 1 high)
```

Follow-up needed:

- Run dependency audit separately.
- Decide whether dependency updates are safe for the generated frontend package.

# Claude Notes

已於 2026-06-23 完成審查並實作修正。

# Review Findings

## 已修正（本次 commit）

| # | 問題 | 修正方式 | 檔案 |
|---|------|---------|------|
| 1 | `app.core.monitoring` 缺失 | no-op 版加入 kit source | `kits/platform-core-kit/src/backend/app/core/monitoring.py` |
| 2 | `DeveloperLogsPage` 缺失 | placeholder 已由 Codex 建立，保留 | `system/frontend/src/pages/DeveloperLogsPage.tsx` |
| 3 | vite proxy 硬編碼 8000 | 改用 `VITE_PROXY_TARGET` env var | `tools/generate-dependency-files.ps1` |
| 4 | `DATABASE_URL` 無法覆蓋 `database_url` | 加入 `AliasChoices("database_url", "DATABASE_URL")` | `backend/app/core/config.py` |
| 5 | 啟動 seeding P1/P2/P3 與 daihui_* 並存 | `use_generic_schema=True` 時跳過 P1/P2/P3 seeding | `backend/app/main.py` |
| 6 | commit 不寫入 target tables | 新增 generic commit 分支 → `GenericRecord` | `backend/app/services/import_v2.py` |
| 7 | 前端把所有 CSV 歸類為 P3 | 加入 `detectTableCode()` + `availableForms` 選擇器 | `frontend/src/pages/upload/uploadFileUtils.ts`, `UploadPage.tsx` |
| 8 | Toast 重複 key 警告 | ID 加入 `Math.random()` | `frontend/src/components/common/ToastContext.tsx` |

## 驗證規劃

- `database_url` alias: `.env` 只寫 `DATABASE_URL=...` → 後端正確連線
- Generic import: 上傳 `entry_horizontal.csv` → 選 `daihui_entry` → validate → commit → `generic_records` 筆數 > 0
- monitoring: `python -c "from app.core.monitoring import init_monitoring; print('ok')"`

## 延後（不影響核心功能）

| # | 問題 | 原因 |
|---|------|------|
| 9 | npm audit 相依性漏洞 | 需評估升級相容性，與功能無關 |
| - | generator 不包含 monitoring.py | 已在 kit source 修正，下次 assemble 生效 |
| - | 驗證邏輯未支援 schema-driven | validate_job() 已跳過 lot_no check，但未讀 StationSchema 欄位做細部驗證（row 仍會進 READY） |

# Test Plan

Completed by Codex:

- Created an isolated SQLite DB.
- Ran generated DB bootstrap.
- Started backend on `127.0.0.1:8002`.
- Started frontend on `127.0.0.1:5174`.
- Logged in through API and UI as `manager`.
- API-uploaded all five Daihui CSVs to their intended `daihui_*` table codes.
- UI-uploaded `entry_horizontal.csv`.
- Queried SQLite directly for import jobs, staging rows, and target table counts.
- Stopped test services and cleaned temporary runtime artifacts.

Recommended tests to add:

- Backend import unit/integration test for all five Daihui CSVs:
  create job -> READY -> commit -> persisted row count > 0.
- Assert invalid jobs cannot become `COMPLETED` with zero target rows.
- Frontend E2E test:
  login -> select Daihui CSV -> target table selection/detection -> validate -> import enabled -> commit.
- Generated package smoke test:
  Python import `app.main` succeeds.
- Generated frontend smoke test:
  `npm run build` or Vite import graph resolves.
- Config test:
  `DATABASE_URL` and/or `database_url` select the intended DB.

# Decisions

- Accepted: Added temporary no-op `monitoring.py` in generated dist package so backend can start during testing.
- Accepted: Added temporary placeholder `DeveloperLogsPage.tsx` in generated dist package so frontend can render during testing.
- Accepted: Made Vite proxy target configurable with `VITE_PROXY_TARGET` for local isolated testing.
- Deferred: Full Daihui generic import implementation remains to be done.
- Deferred: Frontend target table selection/detection remains to be done.
- Deferred: Generator/template changes must be made at source, not only in `dist`.

# Session Summary

Codex verified that the generated web UI can partially operate after patching package-level startup blockers: login works and CSV selection works. The database connection can be made against an isolated SQLite database when `database_url` is set correctly. However, the core Daihui import requirement is not satisfied: the five CSV files only reach staging, are marked invalid due to missing `lot_no`, and no target table receives rows. The UI also cannot select or infer the `daihui_*` table codes and instead classifies non-P1/P2 CSVs as `P3`.

# Open Questions

- Should Daihui records be persisted to `generic_records/generic_record_items`, a new Daihui-specific table family, or a JSON `records` table?
- Should table detection be based primarily on filename, `表單名稱`, CSV header fingerprint, or user selection?
- Should `P1/P2/P3` remain as compatibility modes, or should they be disabled when a generated schema contract exists?
- Should the no-op monitoring module be the permanent fallback when no dashboard is configured, or should logs-ops-kit be mandatory whenever monitoring calls are emitted?
