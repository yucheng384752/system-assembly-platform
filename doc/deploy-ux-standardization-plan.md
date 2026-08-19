# Deploy UX Standardization Plan

Created: 2026-07-06T16:21:25+08:00

## Goal

Standardize the generated deployment package and installation flow while keeping the system generic, decoupled, and reusable across kit combinations.

## Design Principles

- Generic: deployment naming, install output, import flow, and offline package flow must not depend on a single customer recipe.
- Decoupled: installer, package generator, generic table kit, and offline bundle tools should communicate through explicit files/contracts, not hidden assumptions.
- Standardized: every generated package should expose the same names, scripts, output locations, and success messages.

## Scope

1. Use one stable ZIP/package name: `form-manager-system`.
2. Make the install wizard output downloadable startup instructions, ideally as generated launch scripts.
3. Add "import from CSV directly" to the generic table kit.
4. Simplify the offline installation ZIP download flow.

## Current Problems

### 1. Package Name Drift

Generated client deploy folders and ZIPs currently derive names from recipe IDs such as `gui-selected-form-system`. This makes user instructions and offline deployment harder because every recipe can produce a different artifact name.

### 2. Startup Instructions Are Not First-Class Artifacts

The install wizard can guide installation, but users still need to infer or manually copy startup commands. This is fragile when deployment mode changes between online, offline, Docker, and local scripts.

### 3. Generic Table Kit Lacks Direct CSV Import

The generic table kit can represent dynamic schema/table views, but it does not yet provide a user-facing path for adding records by directly uploading a CSV into a selected generic table.

### 4. Offline Download Flow Is Too Fragmented

Offline deployment currently involves multiple concepts: generated deploy package, Docker images bundle, backend wheels, frontend npm cache, and offline scripts. These are technically correct but too many steps for factory-side use.

## Proposed Architecture

### A. Stable Package Naming

Introduce a package identity layer:

- `systemName`: internal generated system identity.
- `packageName`: downloadable artifact name, default `form-manager-system`.
- `recipeName`: source recipe name, preserved only in manifest metadata.

Required behavior:

- Client deploy folder: `dist/client-deploy-form-manager-system`
- ZIP name: `form-manager-system.zip`
- Signature name: `form-manager-system.sig.json`
- Internal manifest keeps original recipe name for traceability.

Affected areas:

- `tools/package-client-deploy.ps1`
- package manifest/signature generation
- GUI export/download labels
- tests that assert output folder/ZIP names

### B. Startup Script Export From Install Wizard

Add a generated startup bundle after installation:

- `start-form-manager.ps1`
- `start-form-manager.sh`
- `README-START.md`
- optional `startup-command.json` for GUI or support tooling

The install wizard should show and allow download/open of these artifacts after successful install.

Recommended contract:

```json
{
  "systemName": "form-manager-system",
  "mode": "docker-compose",
  "commands": {
    "windows": ".\\start-form-manager.ps1",
    "linux": "./start-form-manager.sh"
  },
  "urls": {
    "frontend": "http://localhost:8080",
    "backendHealth": "http://localhost:8000/healthz"
  }
}
```

Implementation direction:

- Keep wizard UI thin.
- Generate scripts from package metadata and deployment mode.
- Do not hard-code kit-specific startup commands inside the wizard.

### C. Generic Table CSV Direct Import

Add a generic import workflow to the generic table kit by **extending the existing `/api/forms/{code}/upload` endpoint** rather than introducing a parallel `/api/v2/generic-forms/` prefix. This keeps the API surface consistent.

Workflow:

1. User selects a generic table/schema.
2. User uploads CSV.
3. Frontend previews header mapping.
4. Backend validates:
   - table exists in generic schema registry
   - columns are allowed
   - required fields are present
   - type conversion is safe
   - row count and file size are within configured limits
5. Backend inserts rows in one transaction or returns row-level errors without partial commit.

**Decided API contract** (extends existing `/api/forms/` prefix):

```text
POST /api/forms/{code}/import/preview   ← new: dry-run, returns mapped rows + errors
POST /api/forms/{code}/import/commit    ← new: actual insert, atomic transaction
GET  /api/forms/{code}/import-jobs/{job_id}  ← new: async job status (large files only)
```

The existing `POST /api/forms/{code}/upload` endpoint remains unchanged for backward compatibility.

**Decided duplicate handling**: skip rows where all `unique_key_fields` (defined in `StationSchema`) already exist. No upsert in Phase 3; upsert can be added as an option in a later phase.

**Decided sync vs async**: synchronous commit for files under 1 MB; async (job-based) for files 1 MB and above. Threshold is configurable via `GENERIC_FORMS_ASYNC_THRESHOLD_MB` env var (default: 1).

Data correctness requirements:

- No ad hoc table name string interpolation in SQL.
- Use schema registry/table allowlist.
- Preserve import audit metadata.
- Prefer staged preview before commit.
- Roll back failed commit transactions atomically.

Affected areas:

- `kits/generic-forms-kit/src/backend/app/api/routes_generic_forms.py`
- `dist/client-deploy-gui-selected-form-system/system/backend/app/api/routes_generic_forms.py`
- frontend `FormsPage.tsx` (add preview/commit UI in 上傳資料 subtab)
- tests for CSV validation, duplicate columns, missing columns, type coercion, and rollback

### D. Simplified Offline Download

Create one user-facing action: "Download offline install package".

Behind the scenes it should produce one folder/ZIP containing:

- `form-manager-system.zip` or extracted `system/`
- Docker image archive including `node:20-slim`
- backend wheels
- frontend `.npm-cache`
- `install-offline.ps1`
- `install-offline.sh`
- `README-OFFLINE.md`

Preferred user flow:

1. User selects package mode: online or offline.
2. User clicks one button.
3. System runs all required preparation checks.
4. User downloads one artifact.
5. Offline machine runs one entry script.

Implementation direction:

- Keep `prepare-offline.ps1` and `bundle-offline.ps1/sh` as low-level tools.
- Add a higher-level orchestrator:
  - `tools/package-offline-deploy.ps1`
  - optional GUI action calling that flow
- Avoid duplicating Docker/pip/npm logic in the GUI.

## Phased Implementation Plan

### Phase 1: Package Identity Contract

- Add `packageName` defaulting to `form-manager-system`.
- Update client deploy output folder, ZIP, signature, manifests, and GUI labels.
- Add tests ensuring all package names remain stable while recipe metadata is preserved.

### Phase 2: Startup Artifact Contract

- Define `startup-command.json`.
- Generate `start-form-manager.ps1`, `start-form-manager.sh`, and `README-START.md`.
- Update install wizard to show/download startup artifacts.
- Add validation that generated scripts exist in every package.

### Phase 3: Generic Table CSV Import

- Add preview/commit APIs to generic forms kit.
- Add frontend upload/preview/commit UI in generic table area.
- Add validation and transaction tests.
- Add import audit event support.

### Phase 4: Offline Package Simplification

- Add `tools/package-offline-deploy.ps1` as the one-command offline bundle builder.
- Ensure it invokes package generation, offline dependency preparation, Docker image bundling, and final ZIP creation.
- Update GUI to expose a single offline download button.
- Add tests that offline package contains Docker images, wheels, npm cache, startup scripts, and manifests.

## Test Plan

- Static tests:
  - package naming contract
  - generated startup files exist
  - package manifest includes recipe metadata and stable package name
  - offline package manifest includes required artifacts
- Backend tests:
  - generic CSV preview validation
  - generic CSV commit transaction rollback
  - invalid table/form ID rejection
  - type conversion and required field checks
- Frontend tests:
  - generic table import button appears
  - CSV preview flow renders errors and commit action
  - installer shows startup command output
- E2E/manual:
  - build online package
  - build offline package
  - install on clean client environment
  - run generated startup script
  - import CSV into a generic table

## Decisions (2026-07-06, finalized by user)

| # | Question | Decision |
|---|----------|----------|
| 1 | packageName: hard-coded or configurable? | **Configurable**, default `form-manager-system`. Recipe name is preserved in manifest metadata only. |
| 2 | Offline package format? | **Single ZIP only**. Simplest for factory-side deployment. |
| 3 | CSV duplicate handling? | **Skip** rows where all `unique_key_fields` already exist. Upsert deferred to a later phase. |
| 4 | CSV commit sync or async? | **Sync** for files < 1 MB, **async** (job-based) for ≥ 1 MB. Threshold configurable via `GENERIC_FORMS_ASYNC_THRESHOLD_MB` (default: 1). |

Additional architectural decision from Claude review:
- Phase 3 API must extend `/api/forms/` (existing prefix) rather than introduce a new `/api/v2/generic-forms/` prefix to avoid dual-path confusion.

## Open Questions

None — all questions resolved. Proceed to implementation.
