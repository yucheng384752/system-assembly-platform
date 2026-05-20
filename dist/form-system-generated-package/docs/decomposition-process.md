# Decomposition Process

This document turns the target-system split into an operating workflow.

## Phase 1: Inventory

Goal: find every user-facing capability and map it to source files.

Checklist:

- Identify frontend entry points.
- Identify backend routers.
- Identify database models and migrations.
- Identify services used by each router.
- Identify feature flags and environment variables.
- Identify external services.

Current target-system result:

- Frontend tabs: register, upload, query, analysis, manager, admin, logs.
- Backend routers: auth, tenants, upload, validate, import, import_v2, query_v2,
  traceability, analytics, stations, edit, audit_events, logs, health.
- Database families: tenant/auth, upload jobs, import jobs, P1/P2/P3 records,
  generic station records, audit/edit, analytics mapping.

## Phase 2: Boundary Definition

Goal: define one kit per business capability, not one kit per folder.

Rules:

- A kit must describe a user-recognizable capability.
- A kit owns its frontend surfaces, backend APIs, database models, permissions,
  preview data, and dependencies.
- Shared runtime code belongs to `platform-core-kit`.
- Shared station-linked production data belongs to `station-data-link-kit`.
- Large files should be split only after kit ownership is agreed.

Current kit boundaries:

- `platform-core-kit`
- `tenant-auth-kit`
- `station-data-link-kit`
- `upload-validation-kit`
- `import-pipeline-kit`
- `query-traceability-kit`
- `analytics-kit`
- `station-admin-kit`
- `audit-edit-kit`
- `logs-ops-kit`

## Phase 3: Dependency Resolution

Goal: make kit selection safe.

Rules:

- Selecting a kit auto-selects required dependencies.
- Optional dependencies are shown as recommendations.
- Feature flags are generated from selected kits.
- Database recommendation is derived from selected kits and user intent.

Current dependency chain:

```text
platform-core-kit
  -> tenant-auth-kit
    -> station-data-link-kit
      -> upload-validation-kit
      -> import-pipeline-kit
      -> query-traceability-kit
        -> analytics-kit
      -> station-admin-kit
      -> audit-edit-kit
    -> logs-ops-kit
```

## Phase 4: Extraction

Goal: move from manifest-only to code-level modularity.

First extraction target:

```text
tenant-auth-kit
upload-validation-kit
import-pipeline-kit
station-data-link-kit
```

Recommended steps:

1. Create a kit registry in the backend.
2. Move hard-coded router includes behind registration functions.
3. Create a frontend route/tab registry.
4. Move hard-coded tabs in `App.tsx` behind kit metadata.
5. Split large pages into shell, API client, workflow state, and view components.
6. Add preview mocks for each selected kit.
7. Generate a deployable recipe from selected kits.

## Phase 5: Recomposition

Goal: rebuild the original target system from the recipe.

The recipe must generate:

- frontend navigation
- backend router registration
- database migrations
- environment variables
- feature flags
- preview scenarios
- deployment notes

The current full-system recipe is:

`assembly/form-analysis-original.recipe.json`

## Current Next Technical Task

Implement `resolve-recipe`:

Input:

- `kits/form-analysis.kit-manifest.json`
- `assembly/form-analysis-original.recipe.json`

Output:

- resolved kit order
- missing dependencies
- enabled APIs
- required models
- feature flags
- database recommendation
