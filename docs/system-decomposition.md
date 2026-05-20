# Target System Decomposition

## Target Summary

The target system is a manufacturing form analysis platform. It accepts CSV,
Excel, and PDF inputs, validates and imports P1/P2/P3 production records, allows
tenant-scoped query and traceability lookup, provides analytics workflows, and
includes admin, manager, audit, and logging functions.

Observed stack:

- Frontend: React 18, Vite, TypeScript, i18next, Radix UI, Recharts, PrimeReact.
- Backend: FastAPI, SQLAlchemy async, Alembic, Pydantic, pandas.
- Database: PostgreSQL primary, with some SQLite-compatible test/dev paths.
- Runtime features: multi-tenant API-key auth, upload jobs, import jobs, audit
  events, generic station schema feature flag, PDF conversion integration.

## Business Kits

### 1. `platform-core-kit`

Purpose: shared runtime foundation.

Frontend source:

- `form-analysis-server/frontend/src/App.tsx`
- `form-analysis-server/frontend/src/main.tsx`
- `form-analysis-server/frontend/src/styles/app.css`
- `form-analysis-server/frontend/src/styles/globals.css`
- `form-analysis-server/frontend/src/i18n.ts`
- `form-analysis-server/frontend/src/locales/**`
- `form-analysis-server/frontend/src/services/fetchWrapper.ts`
- `form-analysis-server/frontend/src/services/a11y.ts`

Backend source:

- `form-analysis-server/backend/app/main.py`
- `form-analysis-server/backend/app/core/config.py`
- `form-analysis-server/backend/app/core/database.py`
- `form-analysis-server/backend/app/core/logging.py`
- `form-analysis-server/backend/app/core/middleware.py`
- `form-analysis-server/backend/app/api/deps.py`
- `form-analysis-server/backend/app/api/routes_health.py`

Database:

- Base metadata, connection setup, Alembic env, health/readiness support.

Notes:

This kit should be mandatory for every generated system.

### 2. `tenant-auth-kit`

Purpose: tenant registration, login, API key issue, user roles, manager/admin
access.

Frontend source:

- `form-analysis-server/frontend/src/pages/RegisterPage.tsx`
- `form-analysis-server/frontend/src/pages/AdminPage.tsx`
- `form-analysis-server/frontend/src/pages/ManagerPage.tsx`
- `form-analysis-server/frontend/src/services/auth.ts`
- `form-analysis-server/frontend/src/services/adminAuth.ts`
- `form-analysis-server/frontend/src/services/tenant.ts`
- `form-analysis-server/frontend/src/services/tenantMap.ts`

Backend source:

- `form-analysis-server/backend/app/api/routes_auth.py`
- `form-analysis-server/backend/app/api/routes_tenants.py`
- `form-analysis-server/backend/app/core/auth.py`
- `form-analysis-server/backend/app/core/bootstrap.py`
- `form-analysis-server/backend/app/core/password.py`
- `form-analysis-server/backend/app/core/tenant_resolver.py`

Database/models:

- `Tenant`
- `TenantUser`
- `TenantApiKey`

Primary APIs:

- `GET /api/auth/whoami`
- `POST /api/auth/login`
- `POST /api/auth/me/password`
- `GET /api/auth/users`
- `PATCH /api/auth/users/{user_id}`
- `DELETE /api/auth/users/{user_id}`
- `POST /api/auth/admin/tenant-api-keys`
- `GET /api/tenants`
- `POST /api/tenants`
- `PATCH /api/tenants/{tenant_id}`
- `DELETE /api/tenants/{tenant_id}`

### 3. `upload-validation-kit`

Purpose: upload CSV/Excel/PDF, validate file content, edit uploaded CSV content,
track upload jobs and errors.

Frontend source:

- `form-analysis-server/frontend/src/pages/UploadPage.tsx`
- `form-analysis-server/frontend/src/components/FileUpload.tsx`
- `form-analysis-server/frontend/src/components/CSVEditor.tsx`
- `form-analysis-server/frontend/src/hooks/useUpload.ts`
- `form-analysis-server/frontend/src/styles/upload-page.css`
- `form-analysis-server/frontend/public/assets/upload-icon.svg`
- `form-analysis-server/frontend/public/assets/file-icon.svg`

Backend source:

- `form-analysis-server/backend/app/api/routes_upload.py`
- `form-analysis-server/backend/app/api/routes_validate.py`
- `form-analysis-server/backend/app/services/validation.py`
- `form-analysis-server/backend/app/services/pdf_conversion.py`

Database/models:

- `UploadJob`
- `UploadError`
- `PdfUpload`
- `PdfConversionJob`

Primary APIs:

- `POST /api/upload`
- `GET /api/upload/{process_id}/status`
- `POST /api/upload/{process_id}/validate`
- `PUT /api/upload/{process_id}/content`
- `GET /api/upload/pdf/service-status`
- `POST /api/upload/pdf/{process_id}/convert`
- `GET /api/upload/pdf/{process_id}/convert/status`
- `POST /api/upload/pdf/{process_id}/convert/ingest`
- `GET /api/upload/pdf/{process_id}/convert/outputs`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`
- Optional: `import-pipeline-kit`
- Optional: external PDF conversion service

### 4. `import-pipeline-kit`

Purpose: create import jobs, parse files, stage rows, validate, commit to target
tables, cancel jobs.

Frontend source:

- Mostly invoked through `UploadPage.tsx`; extract import-job UI into a dedicated
  component during refactor.
- `form-analysis-server/frontend/src/services/api.ts`

Backend source:

- `form-analysis-server/backend/app/api/routes_import.py`
- `form-analysis-server/backend/app/api/routes_import_v2.py`
- `form-analysis-server/backend/app/services/import_v2.py`
- `form-analysis-server/backend/app/services/csv_field_mapper.py`
- `form-analysis-server/backend/app/services/generic_validator.py`

Database/models:

- `ImportJob`
- `ImportFile`
- `StagingRow`
- `TableRegistry`
- `SchemaVersion`

Primary APIs:

- `POST /api/import`
- `POST /api/v2/import/jobs`
- `POST /api/v2/import/jobs/from-upload-job`
- `GET /api/v2/import/jobs/{job_id}`
- `GET /api/v2/import/jobs/{job_id}/errors`
- `POST /api/v2/import/jobs/{job_id}/commit`
- `POST /api/v2/import/jobs/{job_id}/cancel`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`
- `station-data-link-kit`

### 5. `station-data-link-kit`

Purpose: store and normalize station-linked production records. The current
target system uses P1/P2/P3, but the kit should be understood as a generic
station data linking capability.

Frontend source:

- Used indirectly by upload, query, traceability, analytics, and manager screens.

Backend source:

- `form-analysis-server/backend/app/models/p1_record.py`
- `form-analysis-server/backend/app/models/p2_record.py`
- `form-analysis-server/backend/app/models/p3_record.py`
- `form-analysis-server/backend/app/models/p2_item_v2.py`
- `form-analysis-server/backend/app/models/p3_item_v2.py`
- `form-analysis-server/backend/app/models/business/records.py`
- `form-analysis-server/backend/app/models/generic_record.py`
- `form-analysis-server/backend/app/utils/normalization.py`
- `form-analysis-server/backend/app/services/product_id_generator.py`
- `form-analysis-server/backend/app/services/production_date_extractor.py`

Database/models:

- `P1Record`
- `P2Record`
- `P2ItemV2`
- `P3Record`
- `P3ItemV2`
- `GenericRecord`
- `GenericRecordItem`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`

### 6. `query-traceability-kit`

Purpose: lot search, advanced query, dynamic filters, product/lot/winder
traceability, and trace detail views.

Frontend source:

- `form-analysis-server/frontend/src/pages/QueryPage.tsx`
- `form-analysis-server/frontend/src/components/AdvancedSearch.tsx`
- `form-analysis-server/frontend/src/components/DataQuery.tsx`
- `form-analysis-server/frontend/src/components/TraceabilityFlow.tsx`
- `form-analysis-server/frontend/src/components/GenericTraceabilityFlow.tsx`
- `form-analysis-server/frontend/src/services/api.ts`
- `form-analysis-server/frontend/src/styles/query-page.css`
- `form-analysis-server/frontend/src/styles/traceability-flow.css`

Backend source:

- `form-analysis-server/backend/app/api/routes_query_v2.py`
- `form-analysis-server/backend/app/api/traceability.py`
- `form-analysis-server/backend/app/services/traceability_flattener.py`
- `form-analysis-server/backend/app/services/ut_flattener.py`

Primary APIs:

- `GET /api/v2/query/lots`
- `POST /api/v2/query/advanced`
- `GET /api/v2/query/lots/suggestions`
- `GET /api/v2/query/options/{field_name}`
- `GET /api/v2/query/records`
- `GET /api/v2/query/records/advanced`
- `POST /api/v2/query/records/dynamic`
- `GET /api/v2/query/records/stats`
- `GET /api/v2/query/records/{record_id}`
- `GET /api/v2/query/trace/{trace_key}`
- `GET /product/{product_id}`
- `GET /lot/{lot_no}`
- `GET /winder/{lot_no}/{winder_number}`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`
- `station-data-link-kit`

### 7. `analytics-kit`

Purpose: analytics views, artifact browsing, realtime analysis, complaint
analysis, extraction analysis.

Frontend source:

- `form-analysis-server/frontend/src/pages/AnalyticsPage.tsx`
- `form-analysis-server/frontend/src/components/analytics/**`
- `form-analysis-server/frontend/src/services/analyticsArtifacts.ts`
- `form-analysis-server/frontend/src/utils/analyticsDateRange.ts`
- `form-analysis-server/frontend/src/styles/analytics-page.css`

Backend source:

- `form-analysis-server/backend/app/api/routes_analytics.py`
- `form-analysis-server/backend/app/api/routes_ut.py`
- `form-analysis-server/backend/app/services/analytics_external.py`
- `form-analysis-server/backend/app/services/analytics_data_fetcher.py`
- `form-analysis-server/backend/app/services/analytical_four_adapter.py`
- `form-analysis-server/backend/app/config/analytics_config.py`
- `form-analysis-server/backend/app/config/analytics_field_mapping.py`

Primary APIs:

- `GET /api/v2/analytics/flatten/monthly`
- `GET /api/v2/analytics/flatten`
- `GET /api/v2/analytics/health`
- `POST /api/v2/analytics/analyze`
- `GET /api/v2/analytics/artifacts`
- `GET /api/v2/analytics/artifacts/{artifact_key}`
- `GET /api/v2/analytics/artifacts/{artifact_key}/list`
- `GET /api/v2/analytics/artifacts/{artifact_key}/snapshot`
- `POST /api/v2/analytics/realtime-analysis`
- `POST /api/v2/analytics/complaint-analysis`
- `POST /api/v2/analytics/extraction-analysis`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`
- `station-data-link-kit`
- `query-traceability-kit`

### 8. `station-admin-kit`

Purpose: configure stations, station schemas, validation rules, analytics
mappings, station links, and generic traceability.

Frontend source:

- `form-analysis-server/frontend/src/pages/ManagerPage.tsx`
- `form-analysis-server/frontend/src/components/admin/StationManager.tsx`
- `form-analysis-server/frontend/src/components/admin/StationLinkManager.tsx`
- `form-analysis-server/frontend/src/components/admin/ValidationRuleManager.tsx`
- `form-analysis-server/frontend/src/components/admin/AnalyticsMappingManager.tsx`
- `form-analysis-server/frontend/src/hooks/useStations.ts`
- `form-analysis-server/frontend/src/hooks/useStationSchema.ts`
- `form-analysis-server/frontend/src/services/stationApi.ts`
- `form-analysis-server/frontend/src/styles/manager-page.css`

Backend source:

- `form-analysis-server/backend/app/api/routes_stations.py`
- `form-analysis-server/backend/app/core/seed_stations.py`
- `form-analysis-server/backend/app/services/schema_service.py`

Database/models:

- `Station`
- `StationSchema`
- `StationLink`
- `ValidationRule`
- `AnalyticsMapping`

Primary APIs:

- `GET /stations`
- `POST /stations`
- `PUT /stations/{code}`
- `DELETE /stations/{code}`
- `GET /stations/{code}/schema`
- `PUT /stations/{code}/schema`
- `GET /stations/{code}/validation-rules`
- `POST /stations/validation-rules`
- `GET /stations/{code}/analytics-mapping`
- `POST /stations/analytics-mappings`
- `GET /stations/links`
- `POST /stations/links`
- `GET /stations/traceability/{lot_no_norm}`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`
- `station-data-link-kit`

### 9. `audit-edit-kit`

Purpose: inline record editing, edit reasons, row edit history, audit events.

Frontend source:

- `form-analysis-server/frontend/src/components/EditRecordModal.tsx`
- Used by `QueryPage.tsx`, `UploadPage.tsx`, and admin/manager views.

Backend source:

- `form-analysis-server/backend/app/api/routes_edit.py`
- `form-analysis-server/backend/app/api/routes_audit_events.py`
- `form-analysis-server/backend/app/services/audit_events.py`

Database/models:

- `EditReason`
- `RowEdit`
- `AuditEvent`

Primary APIs:

- `GET /api/edit/reasons`
- `POST /api/edit/reasons`
- `PATCH /api/edit/reasons/{reason_id}`
- `PATCH /api/edit/records/{table_code}/{record_id}`
- `GET /api/audit-events`
- `GET /api/admin/audit-events`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`
- `station-data-link-kit`

### 10. `logs-ops-kit`

Purpose: log viewer, log search, log statistics, cleanup, download.

Frontend source:

- `form-analysis-server/frontend/src/components/SimpleLogViewer.tsx`
- `form-analysis-server/frontend/src/components/LogViewer.tsx`
- `form-analysis-server/frontend/src/services/logService.ts`

Backend source:

- `form-analysis-server/backend/app/api/routes_logs.py`

Primary APIs:

- `GET /api/logs/files`
- `GET /api/logs/view/{log_type}`
- `GET /api/logs/stats`
- `GET /api/logs/search`
- `DELETE /api/logs/cleanup`
- `GET /api/logs/download/{log_type}`

Dependencies:

- `platform-core-kit`
- `tenant-auth-kit`

## Important Refactor Observations

The target system already contains useful boundaries through FastAPI routers and
frontend pages. However, some files are large and mix UI, workflow state, API
calls, and domain rules:

- `UploadPage.tsx`
- `QueryPage.tsx`
- `AnalyticsPage.tsx`
- `AdminPage.tsx`
- `routes_upload.py`
- `routes_query_v2.py`
- `routes_analytics.py`

Before physically extracting SDKs, split these into:

- page shell
- feature components
- API client
- domain model/types
- kit registration metadata

## Database Choice For Non-Technical Users

The recomposed system should not ask users to pick SQLite/PostgreSQL/MySQL first.
Ask operational questions instead:

- Is this a demo or production system?
- How many users will use it at the same time?
- Is the data business-critical?
- Do you need tenant isolation?
- Do you need analytics or heavy search?
- Do you need PDF conversion and background jobs?

Recommendation rules:

- SQLite: demo, local prototype, single user, no tenant isolation requirement.
- PostgreSQL: default for this target system, required for production, tenant
  isolation, analytics, JSON/JSONB query, background import jobs.
- MySQL: possible future adapter, not recommended for this target until query,
  JSON, migration, and tests are adapted.
