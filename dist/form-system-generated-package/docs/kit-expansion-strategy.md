# Kit Expansion Strategy

This project extracts kits from user-provided mature systems first, then allows
new kits to be added later. To keep that flow maintainable, every added kit must
follow the same contract as extracted kits.

## Core Principle

A kit is a business capability package, not a random collection of files.

Each kit should describe:

- what user-facing capability it provides
- which subfeatures can be enabled independently
- which source files or templates are needed
- which backend routes, frontend tabs, database models, permissions, and
  entitlement rules it contributes
- which runtime assumptions are required after assembly

## Extraction Flow

1. Start from the mature source system provided by the user.
2. Identify business capabilities before technical files.
3. Map each capability to one kit or one subfeature.
4. Register source paths in the manifest.
5. Generate registry files instead of hand-editing runtime entry points.
6. Validate the recipe, resolved plan, generated registries, and generated
   system folder.

## New Kit Flow

New kits must be added as manifest-first changes:

1. Add the kit or subfeature to `kits/form-analysis.kit-manifest.json`.
2. Declare dependencies and runtime contracts explicitly.
3. Add backend/frontend templates only when the source system does not already
   contain the required files.
4. Add schema fields before using new manifest concepts.
5. Add or update assembly tests.

## 80 Percent Standardization Rule

The standardized 80 percent should include:

- authentication and tenant boundary
- upload/import pipeline shape
- kit manifest schema
- router and tab registration
- database connection ownership
- entitlement checks
- install, migrate, and start script contract
- package validation

The custom 20 percent should be isolated behind:

- kit options
- subfeature selections
- adapter files
- customer-specific validation rules
- customer-specific report/chart rendering options
- paid or custom entitlement flags

## Package Goal

The target output is a folder that can be zipped, moved, extracted, and operated
through scripts:

```powershell
.\scripts\install.ps1
.\scripts\migrate.ps1
.\scripts\start.ps1
```

Scripts must fail with actionable messages when a required runtime contract is
missing. They should never print success for work they did not perform.
