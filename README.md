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

Users select capabilities in a GUI, fill in deployment configuration and license
information, then download the recipe JSON and a ready-to-deploy package. The
package includes all backend/frontend source, a database bootstrap plan, systemd
service template, initial deployment environment file, and an RSA-signed license
certificate. Every download action is logged to `data/operations.jsonl` for audit
and DR backup.

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
data/         Runtime data written by the GUI server (operations.jsonl).
dist/         Generated runnable system output and packaged folder.
docs/         Product, architecture, kit, and development documentation.
generated/    Extracted source slices from the target system.
gui/          GUI server (Node.js) for kit selection, recipe export, and logging.
kits/         Kit manifest source of truth.
schemas/      JSON schemas for kit manifests and recipes.
templates/    Assembly and package templates.
tools/        PowerShell and Node automation for validation and generation.
tools/keys/   RSA key pair for license signing (private key gitignored).
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

The GUI runs as a Node.js server with persistent API endpoints:

```powershell
node tools\serve-gui.cjs
```

Then open:

```text
http://127.0.0.1:4173/
```

The server exposes two API endpoints in addition to static file serving:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/log` | POST | Append one operation record to `data/operations.jsonl` |
| `/api/logs` | GET | Return all operation records as a JSON array |

The GUI supports:

- Guided architecture questions.
- Kit catalog selection and subfeature tuning.
- MOD subscription and paid feature gating metadata.
- Chart summary options.
- Database recommendation and standardization notes.
- Runtime envelope and dependency manifest status.
- **Step 4 — 部署設定**：授權資訊（licensee name, email, expiry days）、部署初始設定（DB connection, initial manager account）。
- Recipe JSON export (Step 4 `licensee` and `deploymentConfig` written in; passwords excluded).
- Deploy-init.env download (credentials only, browser-side, not saved to recipe).
- Assembly command output.
- **05 操作記錄** page: view and export `data/operations.jsonl` from inside the GUI.

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

Package the generated output (also signs the license and embeds `license.lic`):

```powershell
# 預設（licensee 留空）
.\tools\package-client-deploy.ps1

# 指定被授權方（用於 demo 或正式交付）
.\tools\package-client-deploy.ps1 `
    -LicenseeName "Demo 展示版" `
    -LicenseeEmail "demo@example.com" `
    -ExpiresAfterDays 90

# 指定 recipe（不使用最新 recipe 時）
.\tools\package-client-deploy.ps1 -RecipeName "gui-all-kits" -LicenseeName "客戶公司" -LicenseeEmail "admin@client.com" -ExpiresAfterDays 365
```

Generate a license certificate only (reads latest recipe in `assembly/`):

```powershell
.\tools\sign-package.ps1
# or with explicit paths:
.\tools\sign-package.ps1 -RecipePath .\assembly\my.recipe.json -PackageZipPath .\dist\my.zip
```

Back up operation logs and recipes to a timestamped directory (DR):

```powershell
.\tools\backup-composer-data.ps1
# or to a network share:
.\tools\backup-composer-data.ps1 -BackupRoot \\server\share\composer-backup
```

## Generated Package

The assembled package is intended to be operable after extraction. Its important
runtime files include:

- `recipe.json` — selected kit configuration (no passwords).
- `deploy.sh` — Linux deployment script (auto-detects `deploy-init.env`).
- `deploy-init.env` — *(operator-provided)* initial DB credentials and manager account; not shipped inside the package zip, downloaded separately via the GUI.
- `license.lic` — RSA-PSS signed license certificate (JSON + base64 signature).
- `form-system.service` — systemd unit template (`__SYS_ROOT__` placeholder for install path).
- `.gitignore` — protects `system/.env` and `deploy-init.env` from accidental commit.
- `dependency-manifest.json`
- `db-bootstrap-plan.json`
- `backend\requirements.txt`
- `backend\app\core\license.py` — startup license verification (non-blocking).
- `scripts\check-prerequisites.ps1`
- `scripts\install.ps1`
- `scripts\migrate.ps1`
- `scripts\start.ps1`
- `scripts\status.ps1`
- `scripts\stop.ps1`

Database bootstrap is generated from the assembly database plan. If Alembic is
available in the generated backend, migration uses Alembic. Otherwise the
generated SQLAlchemy bootstrap script creates the selected tables.

On Linux deployments with systemd available, `deploy.sh` prints the three-step
systemd installation instructions after a successful deploy:

```bash
sudo sed -i 's|__SYS_ROOT__|/opt/form-system|g' form-system.service
sudo cp form-system.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now form-system
```

Process supervision writes pid files under `runtime` and log files under `logs`.

## License Signing

The composer uses RSA-2048 asymmetric signing via Node.js `crypto`. The private
key never leaves the composer machine; only the public key is embedded in the
generated system.

**First-time setup** (run once; skipped if keys already exist):

```powershell
.\tools\generate-license-keys.ps1
```

Outputs:
- `tools\keys\signing-private-key.pem` — gitignored, keep safe.
- `tools\keys\signing-public-key.pem` — embedded in `license.py`.

**Sign a package** (also called automatically by `package-client-deploy.ps1`):

```powershell
# 最簡呼叫（讀取 assembly/ 最新 recipe）
.\tools\sign-package.ps1

# 明確指定被授權方與有效期（直接交付時使用）
.\tools\sign-package.ps1 `
    -LicenseeName "客戶公司" `
    -LicenseeEmail "admin@client.com" `
    -ExpiresAfterDays 365 `
    -PackageZipPath .\dist\client-deploy-gui-selected-form-system.zip

# 含機器指紋綁定（防止 license 複製到其他機器）
.\tools\sign-package.ps1 `
    -MachineId "$(cat /etc/machine-id)" `
    -LicenseeName "客戶公司" `
    -LicenseeEmail "admin@client.com" `
    -ExpiresAfterDays 365
```

Outputs written to the same directory as the recipe:
- `license.lic` — JSON payload + RSA-PSS/SHA-256 base64 signature.
- `<name>.sig.json` — zip SHA-256 hash + signature (when `-PackageZipPath` given).

**Runtime verification**: the generated system's `backend/app/core/license.py`
verifies the certificate on startup. A failed check logs a warning but does not
block the application from starting.

## Operation Logs and DR Backup

Every download action in the GUI (recipe JSON, deploy package, deploy-init.env)
is recorded by the server to `data/operations.jsonl` via `POST /api/log`.

Each line is a JSON object:

```json
{ "ts": "2026-06-01T10:00:00Z", "ip": "127.0.0.1", "action": "download-package", "recipeName": "form-system-import", "kits": ["platform-core-kit", "upload-validation-kit"], "licensee": "" }
```

View and export logs from inside the GUI on the **05 操作記錄** page.

Back up logs and all recipe files to a timestamped directory:

```powershell
.\tools\backup-composer-data.ps1
# offsite / network share:
.\tools\backup-composer-data.ps1 -BackupRoot \\server\share\composer-backup
```

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

The MVP frontend upload page refactor (Phase 29) is complete. Logic has been
progressively split into focused modules under:

```text
generated\mvp-import-flow\form-analysis-server\frontend\src\pages\upload
```

Extracted modules cover: shared upload types, file parsing, upload eligibility
predicates, API client setup, workflow state transitions, batch
validation/conversion/import orchestration, PDF conversion orchestration, CSV
edit and save mechanics, validation error normalization, toast routing, batch
import cleanup scheduling, and all sub-components.

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

Completed features as of 2026-06-01:

| Feature | Description | Status |
|---------|-------------|--------|
| B | Kit CSS 打包 | ✓ Done |
| C | deploy-init.env GUI 輸入 + auto-detect in deploy.sh | ✓ Done |
| D1 | GUI Server 化 (API log endpoints) | ✓ Done |
| D2 | 生成系統 systemd service 模板 | ✓ Done |
| E1/E2 | GUI 操作記錄頁面 | ✓ Done |
| E3 | DR 備援腳本 | ✓ Done |
| A | License RSA 簽章 + 後端驗證 | ✓ Done |
| UploadPage | Phase 29 refactor | ✓ Done |

Good candidates for next work:

1. Add `GET /api/logs?action=&from=&to=` query filter support to the log server.
2. Extend kit coverage: add new kit manifests beyond the current platform/upload/PDF/query kits.
3. Build a `tools\rotate-license-keys.ps1` that regenerates the key pair and re-embeds the public key into `license.py` for key rotation.
4. Add a GitHub Actions or CI workflow that runs `.\tools\test-all.ps1` on push.

For the complete handoff and implementation history, read `HANDOFF.md` and
`TODO.md`.
