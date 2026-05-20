# Recomposition Architecture

## Product Concept

The new project acts as a composer for the target system. A GUI can later edit a
recipe that selects kits. The assembly engine reads the recipe and generates a
working application from selected frontend modules, backend routers, database
models, migrations, permissions, and environment settings.

## Assembly Layers

```text
GUI Composer
  -> Recipe JSON
  -> Kit Manifest
  -> Dependency Resolver
  -> Frontend App Generator
  -> Backend Router/Model Generator
  -> Migration Selector
  -> Preview Data Builder
  -> Deployable System
```

## Minimal Recomposition Of The Original System

To rebuild the current target system, enable these kits:

1. `platform-core-kit`
2. `tenant-auth-kit`
3. `station-data-link-kit`
4. `upload-validation-kit`
5. `import-pipeline-kit`
6. `query-traceability-kit`
7. `analytics-kit`
8. `station-admin-kit`
9. `audit-edit-kit`
10. `logs-ops-kit`

## Generated Backend Shape

The backend generator should create a FastAPI app that registers routers from
enabled kits:

```python
enabled_kits = recipe["kits"]

app = create_platform_app(settings)

for kit in resolve_dependency_order(enabled_kits):
    kit.register_models(Base)
    kit.register_startup(app)
    kit.register_routes(app)
    kit.register_middleware(app)
```

For the first implementation, this can be simpler:

- keep the current target source layout
- generate `app/kit_registry.py`
- generate conditional router includes in `app/main.py`
- gradually move each kit's code behind registration functions

## Generated Frontend Shape

The frontend generator should build navigation from selected kit manifests:

```ts
const routes = enabledKits.flatMap((kit) => kit.frontend.routes)
const navItems = enabledKits.flatMap((kit) => kit.frontend.navItems)
```

The current target uses tab state in `App.tsx`, so the first extraction should
replace hard-coded tabs with kit-provided tabs.

## Preview Strategy

Realtime preview is feasible with three modes:

- UI preview: render kit pages/components with mock data.
- Workflow preview: simulate upload -> validation -> import -> query -> analysis.
- Data model preview: show tables, fields, links, and required database choice in
  business language.

Each kit should provide:

- `previewData`
- `previewScenarios`
- `mockApiResponses`
- `businessExplanation`

## Recomposition Risks

1. Large files contain multiple responsibilities.
2. Some comments and strings appear mojibake/encoding-corrupted.
3. PostgreSQL is assumed in runtime messages and JSONB-heavy query paths.
4. PDF conversion depends on an external service.
5. Analytics depends on artifact files and analytical adapter conventions.
6. Some routes are feature-flagged by `USE_GENERIC_SCHEMA`.

## Recommended MVP Extraction

Start with:

```text
platform-core-kit
tenant-auth-kit
upload-validation-kit
import-pipeline-kit
station-data-link-kit
```

This gives a complete vertical slice:

```text
login/register -> upload file -> validate -> import job -> committed records
```

Then add:

```text
query-traceability-kit -> analytics-kit -> station-admin-kit -> audit-edit-kit
```
