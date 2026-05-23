# Form System Kit Composer

Form System Kit Composer turns an existing production-style Form Analysis
application into selectable business capability kits, then assembles selected
kits back into a generated runnable system package.

The project is currently focused on the Form Analysis source system at:

```text
C:\Users\gslab\Desktop\Form-analysis-server-specify-kit
```

The local composer workspace is:

```text
C:\Users\gslab\Documents\New project\form-system-kit-composer
```

## What This Project Does

The composer separates a mature application into manifest-driven kits. Each kit
describes the frontend pages, backend routers, database objects, permissions,
configuration, dependencies, preview data, and optional entitlement gates needed
to deliver one business capability.

Users select capabilities in a GUI, export the selected recipe JSON, and run the
assembly tooling to produce a system package with operational scripts.

The intended operator flow for a generated package is:

```powershell
.\scripts\check-prerequisites.ps1
.\scripts\check-db.ps1
.\scripts\install.ps1
.\scripts\migrate.ps1
.\scripts\start.ps1 -Background
.\scripts\status.ps1
```

## Current Status

The project has a runnable-envelope generator. It can extract the MVP import
flow, resolve kit dependencies, assemble selected backend/frontend files, create
dependency and database plans, and package a generated system under `dist`.

Current generated outputs include:

- `generated/mvp-import-flow`: extracted MVP source slice.
- `dist/generated-system`: assembled runnable envelope.
- `dist/form-system-generated-package`: packaged project folder.
- `dist/generated-system.zip`: optional archive output when created.

The generated system includes backend/frontend source, dependency manifests,
database bootstrap plans, environment template, README, and PowerShell scripts
for prerequisite checks, install, migration, smoke validation, process
supervision, and startup.

## Repository Layout

```text
assembly/     Recipe files, resolved plans, and database assembly plans.
dist/         Generated runnable system output and packaged folder.
docs/         Product, architecture, kit, and development documentation.
generated/    Extracted source slices from the target system.
gui/          Static GUI prototype for selecting kits and exporting recipes.
kits/         Kit manifest source of truth.
schemas/      JSON schemas for kit manifests and recipes.
templates/    Assembly and package templates.
tools/        PowerShell and Node automation for validation and generation.
```

Important files:

- `kits/form-analysis.kit-manifest.json`: primary kit manifest.
- `schemas/kit.schema.json`: kit manifest schema.
- `schemas/recipe.schema.json`: recipe schema.
- `assembly/form-analysis-original.recipe.json`: full source-system recipe.
- `assembly/mvp-import-flow.recipe.json`: MVP import-flow recipe.
- `assembly/resolved-plan.json`: resolved full assembly plan.
- `assembly/mvp-resolved-plan.json`: resolved MVP assembly plan.
- `gui/index.html`: local static GUI entry point.
- `HANDOFF.md`: detailed current project state and implementation notes.
- `TODO.md`: completed and pending implementation log.

## Prerequisites

The tooling is designed for Windows PowerShell.

Recommended local tools:

- PowerShell 5 or later.
- Node.js for static GUI serving and browser-oriented smoke checks.
- Python for generated backend smoke validation.
- Git for source control and publishing.

Some generated application runtime modes require additional backend/frontend
dependencies and a configured database. The default smoke validations avoid
requiring full production dependency installation.

## Start The GUI

The GUI is a static prototype. The repository includes a local Node server:

```powershell
node tools\serve-gui.cjs
```

Then open:

```text
http://127.0.0.1:4173/
```

The GUI supports:

- Guided architecture questions.
- Kit catalog selection and subfeature tuning.
- MOD subscription and paid feature gating metadata.
- Chart summary options.
- Database recommendation and standardization notes.
- Runtime envelope and dependency manifest status.
- Recipe JSON export.
- Assembly command output.

## Core Workflow

Validate source JSON:

```powershell
.\tools\validate-json.ps1 .\kits\form-analysis.kit-manifest.json
.\tools\validate-json.ps1 .\assembly\mvp-import-flow.recipe.json
```

Validate a recipe against schemas and kit definitions:

```powershell
.\tools\validate-recipe.ps1 -RecipePath .\assembly\mvp-import-flow.recipe.json
```

Resolve a recipe into an ordered assembly plan:

```powershell
.\tools\resolve-recipe.ps1 `
  -RecipePath .\assembly\mvp-import-flow.recipe.json `
  -OutputPath .\assembly\mvp-resolved-plan.json
```

Extract the MVP source slice:

```powershell
.\tools\extract-mvp-flow.ps1
```

Assemble the generated system:

```powershell
.\tools\assemble-system.ps1 `
  -RecipePath .\assembly\mvp-import-flow.recipe.json `
  -OutputPath .\dist\generated-system
```

Validate the generated system:

```powershell
.\tools\validate-generated-system.ps1 -GeneratedRoot .\dist\generated-system
```

Package the generated output:

```powershell
.\tools\package-system.ps1
```

## Generated Package

The assembled package is intended to be operable after extraction. Its important
runtime files include:

- `.env.example`
- `dependency-manifest.json`
- `dependency-plan.json`
- `db-bootstrap-plan.json`
- `package-manifest.json`
- `backend\requirements.txt`
- `frontend\package.json`
- `backend\app\core\generated_db_bootstrap.py`
- `backend\app\models\__init__.py`
- `scripts\check-prerequisites.ps1`
- `scripts\check-db.ps1`
- `scripts\install.ps1`
- `scripts\migrate.ps1`
- `scripts\smoke-start.ps1`
- `scripts\start.ps1`
- `scripts\status.ps1`
- `scripts\stop.ps1`
- `scripts\restart.ps1`

Database bootstrap is generated from the assembly database plan. If Alembic is
available in the generated backend, migration uses Alembic. Otherwise the
generated SQLAlchemy bootstrap script creates the selected tables.

Process supervision writes pid files under `runtime` and log files under `logs`.

## Validation

Run the full local validation suite:

```powershell
.\tools\test-all.ps1
```

Focused checks:

```powershell
.\tools\test-gui-static.ps1
.\tools\test-gui-recipe-export.ps1
.\tools\test-upload-page-refactor.ps1
.\tools\test-resolver.ps1
.\tools\test-dependency-files.ps1
.\tools\test-db-bootstrap.ps1
.\tools\test-generated-start.ps1
.\tools\test-process-supervision.ps1
```

If PowerShell script execution is restricted on the machine, run a check with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test-all.ps1
```

## UploadPage Refactor State

The MVP frontend upload page has been progressively split into focused modules
under:

```text
generated\mvp-import-flow\form-analysis-server\frontend\src\pages\upload
```

The refactor currently separates:

- Shared upload types.
- File parsing and file construction helpers.
- Upload eligibility predicates.
- API client setup.
- Upload workflow state transitions.
- Batch validation, conversion, and import orchestration.
- PDF conversion orchestration.
- CSV edit and save mechanics.
- Validation error normalization.
- Toast routing.
- Batch import cleanup scheduling.
- File drop area, uploaded file card, batch action bar, and confirmation modal
  components.

`tools\test-upload-page-refactor.ps1` reapplies the refactor and fails if major
logic moves back into `UploadPage.tsx`.

## Kit Development Rules

New kits should follow `docs/kit-development-standard.md`.

Architecture diagrams for customer-facing explanation and developer handoff are
available in `docs/architecture-diagrams.md`. They cover system breakdown,
function communication, and customer web input/output.

Short version:

- Define the business capability in the manifest first.
- Keep kit boundaries capability-based, not file-folder based.
- Register frontend tabs and backend routers through generated registries.
- Describe database objects and dependency requirements explicitly.
- Add entitlement metadata when a feature is paid or gated.
- Cover new kit behavior with validation tooling.

## MOD Subscription Note

MOD subscription currently means internal paid/custom feature gating. It is not
an external platform integration by default.

Examples of gated features:

- PDF to CSV.
- Form analysis.
- Chart summary rendering.
- Custom validation rules.

Do not add runtime middleware or third-party subscription provider integration
unless that scope is explicitly confirmed.

## Assembly Engine Generalization

The assembly engine now emits a central Assembly IR at
`assembly\assembly-ir.json` from the resolved plan, kit manifest, baseline
dependency and database contracts, entitlement plan, and Daihui form schema
baseline. The IR is validated as JSON by `tools\validate-json.ps1` and is
generated by `tools\generate-assembly-ir.ps1`.

Generator scripts can still read their original inputs, but backend and
frontend registry generation may receive `-IRPath assembly\assembly-ir.json` to
use the shared contract. This keeps current patch behavior intact while giving
future generators one stable source for selected kits, feature flags, router
registrations, frontend navigation, database storage decisions, dependency
baselines, environment requirements, scripts, and entitlements.

The Daihui schema pack is represented with hybrid physical-first storage
decisions: stable runtime and query surfaces remain physical tables, while
Daihui sample forms use generic records with common query fields extracted and
full source rows preserved in JSON data. The baseline file is read as an input;
the IR generator does not rewrite it.

## Generated Runtime State Topology

The Assembly IR includes `runtimeStateTopology`, a generated graph of runtime
state owners and relationships. Nodes cover identity scope, API key actors,
environment configuration, database state, backend routers, required models, and
selected external services. Edges describe tenant scoping, model persistence,
and environment-backed service configuration.

This topology is intended for downstream package checks and future GUI previews:
it makes runtime state visible before code is assembled, so a selected kit can be
reviewed for tenant scope, database impact, external configuration, and service
ownership without inspecting generated source files.

## Documentation Policy

Repository docs should stay focused on files required by tools, schemas, tests,
package distribution, and implementation handoff.

Long-form explanatory notes, architecture diagrams, decisions, and process
knowledge belong in the Obsidian workspace:

```text
C:\Users\gslab\Desktop\Form System Kit Composer Obsidian
```

## Git And Commit Convention

Use Conventional Commits for repository changes:

```text
feat: add new capability
fix: correct broken behavior
docs: update project documentation
test: add or update validation
refactor: restructure without behavior change
chore: update maintenance files
```

For documentation-only changes, prefer:

```text
docs: update project readme
```

## Recommended Next Work

The next engineering priority is continuing the UploadPage production refactor.
Good candidates are:

1. Move remaining final CSV validation result dispatch out of `UploadPage.tsx`
   when additional simplification is needed.
2. Continue shrinking page-owned import and validation orchestration.
3. Keep extending `tools\test-upload-page-refactor.ps1` so generated refactors
   remain repeatable.

For the complete handoff and implementation history, read `HANDOFF.md` and
`TODO.md`.
