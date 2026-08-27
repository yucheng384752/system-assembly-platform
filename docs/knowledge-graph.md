# Form System Kit Composer Knowledge Graph

This document initializes the project knowledge graph. It is based on the current kit manifest, resolved assembly plan, backend registry, frontend registry, DB assembly plan, and GUI/tooling layout.

## Source Map

| Knowledge Area | Source |
| --- | --- |
| Kit catalog and dependencies | `kits/form-analysis.kit-manifest.json` |
| Selected kit order and enabled APIs | `assembly/resolved-plan.json` |
| Assembly IR and install plan | `assembly/assembly-ir.json` |
| Backend router registration | `assembly/backend-registry/backend-router-registry.json` |
| Frontend navigation tabs | `assembly/frontend-registry/frontend-tab-registry.json` |
| Database schema plan | `assembly/db-plan/db-assembly-plan.json` |
| Composer GUI and local API | `gui/*`, `tools/serve-gui.cjs` |
| Packaging and deployment scripts | `tools/*.ps1`, `dist/*` |

## Project Graph

```mermaid
flowchart TD
  user["User"] --> gui["Kit Composer GUI"]
  gui --> recipe["Recipe JSON"]
  gui --> pem["Machine public key PEM"]
  gui --> sampleData["CSV/TSV source samples"]

  recipe --> manifest["Kit Manifest"]
  manifest --> resolver["Dependency Resolver"]
  resolver --> resolvedPlan["Resolved Plan"]
  resolvedPlan --> assemblyIr["Assembly IR"]

  assemblyIr --> backendRegistry["Backend Router Registry"]
  assemblyIr --> frontendRegistry["Frontend Tab Registry"]
  assemblyIr --> dbPlan["DB Assembly Plan"]
  assemblyIr --> entitlementPlan["Entitlement Plan"]

  backendRegistry --> generatedBackend["Generated FastAPI Backend"]
  frontendRegistry --> generatedFrontend["Generated React Frontend"]
  dbPlan --> postgres["PostgreSQL Schema"]
  entitlementPlan --> license["License and Feature Gates"]

  generatedBackend --> packageSystem["Client Deploy Package"]
  generatedFrontend --> packageSystem
  postgres --> packageSystem
  license --> packageSystem

  packageSystem --> clientVm["Client VM or Daihui Deployment"]
```

## Assembly Pipeline

```mermaid
flowchart LR
  gui["Composer GUI"] --> recipe["recipe.json"]
  recipe --> validate["Validate Recipe"]
  validate --> resolve["Resolve Kit Order"]
  resolve --> plan["resolved-plan.json"]
  plan --> backend["Generate Backend Registry"]
  plan --> frontend["Generate Frontend Registry"]
  plan --> db["Generate DB Plan"]
  plan --> entitlements["Generate Entitlement Plan"]
  backend --> ir["Generate Assembly IR"]
  frontend --> ir
  db --> ir
  entitlements --> ir
  ir --> assemble["Assemble System"]
  assemble --> package["Package Client Deploy ZIP"]
```

## Kit Dependency Graph

```mermaid
graph LR
  platform["platform-core-kit"]
  auth["tenant-auth-kit"]
  stationLink["station-data-link-kit"]
  upload["upload-validation-kit"]
  import["import-pipeline-kit"]
  query["query-traceability-kit"]
  analytics["analytics-kit"]
  stationAdmin["station-admin-kit"]
  audit["audit-edit-kit"]
  logs["logs-ops-kit"]
  genericForms["generic-forms-kit"]
  modSub["mod-subscription-kit"]

  platform --> auth
  platform --> stationLink
  platform --> upload
  platform --> import
  platform --> query
  platform --> analytics
  platform --> stationAdmin
  platform --> audit
  platform --> logs
  platform --> genericForms
  platform --> modSub

  auth --> upload
  auth --> import
  auth --> query
  auth --> analytics
  auth --> stationAdmin
  auth --> audit
  auth --> logs
  auth --> genericForms
  auth --> modSub

  stationLink --> upload
  stationLink --> import
  stationLink --> query
  stationLink --> analytics
  stationLink --> stationAdmin
  stationLink --> genericForms

  upload --> import
  import --> query
  query --> analytics
  stationAdmin --> query
  audit --> query
```

## Runtime Capability Graph

```mermaid
flowchart TD
  tenant["Tenant and API key"] --> uploadPage["Upload Page"]
  uploadPage --> validation["Upload Validation"]
  validation --> importJob["Import Job"]
  importJob --> staging["Staging Rows"]
  staging --> commit["Commit Production Records"]
  commit --> records["Production Records"]

  records --> trace["Traceability Query"]
  trace --> analytics["Analytics"]
  records --> stationAdmin["Station and Schema Admin"]
  stationAdmin --> validationRules["Validation Rules"]
  validationRules --> validation

  records --> edit["Inline Edit"]
  edit --> audit["Audit Events"]
  logs["Logs Ops"] --> ops["Troubleshooting and Download"]
```

## Frontend Navigation Graph

```mermaid
graph LR
  app["React App Shell"]
  app --> register["register tab"]
  app --> upload["upload tab"]
  app --> query["query tab"]
  app --> analysis["analysis tab"]
  app --> manager["manager tab"]
  app --> admin["admin tab"]

  register --> authKit["tenant-auth-kit"]
  admin --> authKit
  upload --> uploadKit["upload-validation-kit"]
  query --> queryKit["query-traceability-kit"]
  analysis --> analyticsKit["analytics-kit"]
  manager --> stationKit["station-admin-kit"]
```

## Backend API Graph

```mermaid
graph LR
  app["FastAPI App"]
  app --> health["/healthz"]
  app --> auth["/api/auth"]
  app --> tenants["/api/tenants"]
  app --> upload["/api upload and validate"]
  app --> import["/api/v2/import"]
  app --> query["/api/v2/query"]
  app --> trace["traceability routes"]
  app --> analytics["analytics routes"]
  app --> stations["station admin routes"]
  app --> edit["/api/edit"]
  app --> audit["audit event routes"]
  app --> logs["/api/logs"]
  app --> broker["/api/kit"]

  broker --> contracts["Kit Contracts"]
  broker --> capability["DB and API Capabilities"]
```

## Database Knowledge Graph

```mermaid
erDiagram
  tenants ||--o{ tenant_users : owns
  tenants ||--o{ tenant_api_keys : issues
  tenants ||--o{ upload_jobs : scopes
  tenants ||--o{ import_jobs : scopes
  tenants ||--o{ stations : scopes

  table_registry ||--o{ schema_versions : versions
  schema_versions ||--o{ generic_records : shapes
  stations ||--o{ station_schemas : has
  stations ||--o{ validation_rules : validates
  stations ||--o{ analytics_mappings : maps

  upload_jobs ||--o{ upload_errors : reports
  upload_jobs ||--o{ pdf_conversion_jobs : converts
  import_jobs ||--o{ import_files : contains
  import_jobs ||--o{ staging_rows : stages
  generic_records ||--o{ row_edits : edited_by
  generic_records ||--o{ audit_events : records
```

## Packaging and Client Runtime Graph

```mermaid
sequenceDiagram
  participant U as User
  participant G as Kit Composer GUI
  participant S as serve-gui.cjs
  participant A as Assembly Tools
  participant D as Deploy Package
  participant C as Client VM

  U->>G: Select kits and data requirements
  U->>G: Upload machine public key PEM
  G->>S: Request package manifest and system bundle
  S->>A: Read generated system artifacts
  S-->>G: Return files, license, and wizard assets
  G->>D: Build deploy ZIP
  U->>C: Install ZIP
  C->>C: Configure env, DB, backend, frontend
  C-->>U: Start local client system
```

## Knowledge Graph Maintenance Rules

- Update this document when adding a new kit, router registry, frontend tab, DB table group, or deploy phase.
- Prefer adding a focused graph instead of expanding one diagram beyond readability.
- Keep node ids ASCII and labels quoted when using CJK text.
- Treat `assembly/*.json` as generated knowledge sources and `kits/*.kit-manifest.json` as source-of-truth inputs.
- Cross-check generated runtime behavior against `dist/client-deploy-gui-selected-form-system/system` before claiming a kit is active in client deployments.
