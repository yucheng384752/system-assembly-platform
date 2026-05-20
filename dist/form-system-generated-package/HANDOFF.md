# Form System Kit Composer Handoff

## Workspace

Project root:

```text
C:\Users\gslab\Documents\New project\form-system-kit-composer
```

Target source system used for extraction:

```text
C:\Users\gslab\Desktop\Form-analysis-server-specify-kit
```

## Product Goal

The project turns a mature user-provided system into selectable business kits,
then assembles selected kits into a generated system package.

The target package shape is:

```powershell
.\scripts\check-prerequisites.ps1
.\scripts\check-db.ps1
.\scripts\install.ps1
.\scripts\migrate.ps1
.\scripts\start.ps1 -Background
.\scripts\status.ps1
```

The user expects the final direction to be: unzip the package, run scripts, and
get a working system.

## Current Architecture

- Kit manifest: `kits/form-analysis.kit-manifest.json`
- Kit schema: `schemas/kit.schema.json`
- Recipe schema: `schemas/recipe.schema.json`
- Full recipe: `assembly/form-analysis-original.recipe.json`
- MVP recipe: `assembly/mvp-import-flow.recipe.json`
- Full resolved plan: `assembly/resolved-plan.json`
- MVP resolved plan: `assembly/mvp-resolved-plan.json`
- Generated MVP source: `generated/mvp-import-flow`
- Generated runnable envelope: `dist/generated-system`
- Packaged project folder: `dist/form-system-generated-package`

## Important Clarification

MOD subscription means internal paid/custom feature gating. It is not an
external platform integration by default.

Examples of gated features:

- PDF to CSV
- form analysis
- chart summary rendering
- custom validation rules

Current status: MOD subscription is a feature/backlog item only. Do not develop
runtime middleware or provider integration until the user explicitly confirms it.

## Completed Tooling

- `tools/validate-json.ps1`
- `tools/validate-recipe.ps1`
- `tools/resolve-recipe.ps1`
- `tools/generate-backend-registry.ps1`
- `tools/apply-backend-registry.ps1`
- `tools/generate-frontend-registry.ps1`
- `tools/generate-db-plan.ps1`
- `tools/generate-db-bootstrap.ps1`
- `tools/generate-model-init.ps1`
- `tools/generate-entitlement-plan.ps1`
- `tools/generate-dependency-files.ps1`
- `tools/extract-mvp-flow.ps1`
- `tools/assemble-system.ps1`
- `tools/validate-generated-system.ps1`
- `tools/package-system.ps1`
- `tools/validate-package-folder.ps1`
- `tools/test-gui-static.ps1`
- `tools/test-gui-browser.ps1`
- `tools/test-gui-browser.mjs`
- `tools/test-dependency-files.ps1`
- `tools/test-db-bootstrap.ps1`
- `tools/test-generated-start.ps1`
- `tools/test-process-supervision.ps1`
- `tools/test-gui-recipe-export.ps1`
- `tools/apply-upload-page-refactor.ps1`
- `tools/test-upload-page-refactor.ps1`
- `tools/test-resolver.ps1`
- `tools/test-all.ps1`

## Generated System Runtime State

`tools/assemble-system.ps1` now creates:

- `backend/`
- `frontend/`
- `.env.example`
- `dependency-manifest.json`
- `dependency-plan.json`
- `db-bootstrap-plan.json`
- `backend\app\core\generated_db_bootstrap.py`
- `backend\app\models\__init__.py`
- `backend\requirements.txt`
- `frontend\package.json`
- `package-manifest.json`
- `README.md`
- `scripts/check-prerequisites.ps1`
- `scripts/check-db.ps1`
- `scripts/install.ps1`
- `scripts/migrate.ps1`
- `scripts/smoke-start.ps1`
- `scripts/status.ps1`
- `scripts/stop.ps1`
- `scripts/restart.ps1`
- `scripts/start.ps1`

The current status is `runnable-envelope`.

Dependency files are now inferred from selected backend/frontend imports.
Production deployments should review `dependency-plan.json` and pin exact
versions before release.

Database bootstrap files are generated from `assembly\db-plan`. Generated
systems use Alembic when present; otherwise `scripts/migrate.ps1` calls
`backend\app\core\generated_db_bootstrap.py` to create SQLAlchemy tables.
`scripts\check-db.ps1` performs structural DB checks by default and can be run
with `-Connect` when a real database is available.

Generated start validation now includes `scripts\smoke-start.ps1`. The default
mode compiles selected backend Python files and checks start script wiring.
`-ImportApp` requires installed backend dependencies; `-StartBackend` also
requires a configured database.

Generated process supervision now supports:

- `scripts\start.ps1 -Background`
- `scripts\status.ps1`
- `scripts\stop.ps1`
- `scripts\restart.ps1`

Pid files are written under `runtime`; backend/frontend stdout and stderr logs
are written under `logs`.

## Kit Development Standard

New kits must follow:

```text
docs/kit-development-standard.md
```

Short rule: every new kit must be manifest-first, business-capability based,
registry-driven, entitlement-aware when needed, and covered by validation.

## Obsidian Documentation Rule

All future explanatory documents, architecture diagrams, long-form decisions,
handoff expansions, and process notes should be organized in:

```text
C:\Users\gslab\Desktop\Form System Kit Composer Obsidian
```

New notes added this round:

- `06 文件治理與 Skill.md`
- `07 前端更新紀錄.md`
- `08 系統架構圖.md`
- `Skills\form-system-kit-composer-obsidian\SKILL.md`

Repo docs should stay focused on files required by tools, schemas, tests, or
package distribution. Full knowledge linking belongs in Obsidian.

## GUI State

The static GUI has been refreshed with clean Traditional Chinese copy and now
shows the latest product capabilities:

- guided architecture questions
- kit catalog and subfeature tuning
- MOD subscription/paid gating
- chart summary options
- database recommendation and 80 percent standardization
- runtime envelope and dependency manifest status
- generated scripts and Obsidian documentation output
- recipe JSON export and assembly command output
- UploadPage phase 1/2 refactor for shared upload types, file utilities, CSV
  parsing, progress mapping, and first upload API client query helpers.
- UploadPage phase 3 refactor for remaining upload/import/PDF API actions:
  PDF upload, import job creation, import errors, PDF convert trigger, and
  import commit now go through `uploadApiClient.ts`.
- UploadPage workflow hook phase 1:
  `useUploadWorkflow.ts` now owns `files`, `setFiles`, `filesRef`
  synchronization, file removal, and expand/collapse transitions.
- UploadPage workflow hook phase 2:
  `useUploadWorkflow.ts` now owns PDF validation begin/success/failure
  transitions through `beginPdfValidation`, `completePdfUpload`, and
  `failPdfValidation`.
- UploadPage workflow hook phase 3:
  `useUploadWorkflow.ts` now owns CSV validation begin/progress/job
  preparation/poll/failure/error/pass transitions. `UploadPage.tsx` still owns
  API calls, duplicate confirmation, parsing, and toast decisions.
- UploadPage workflow hook phase 4:
  `useUploadWorkflow.ts` now owns PDF conversion begin/job/progress/replace/fail
  transitions. `UploadPage.tsx` still owns API calls, CSV file construction,
  and toast decisions.
- UploadPage workflow hook phase 5:
  `useUploadWorkflow.ts` now owns single and batch import begin/progress/
  complete/reset/remove transitions. `UploadPage.tsx` still owns API calls,
  polling, and toast decisions.
- UploadPage view/helper split phase 1:
  `uploadFileUtils.ts` now owns PDF conversion output-to-CSV-file construction
  through `buildUploadedCsvFilesFromPdfOutputs`. `UploadPage.tsx` still owns
  fetching converted outputs and toast decisions.
- UploadPage view/helper split phase 2:
  `uploadEligibility.ts` now owns validate/convert/import eligibility
  predicates. `UploadPage.tsx` uses named helper predicates instead of local
  rule functions.
  The refactor test now fails if inline validated/uploaded/error predicate
  bodies return to the page.
- UploadPage view/component split phase 3:
  `FileDropArea.tsx` now owns the drag-and-drop file selector UI.
  `UploadPage.tsx` imports the component and keeps only the workflow wiring.
  The refactor test now fails if `FileDropArea` returns to the page or the
  extracted upload UI is missing.
- UploadPage view/component split phase 4:
  `UploadedFileCard.tsx` now owns the uploaded file card and CSV editor UI,
  including validation badges, progress bars, per-file action buttons, and the
  validation error table. `UploadPage.tsx` imports the card and keeps list-level
  event wiring. The refactor test now fails if `UploadedFileCard`, `CsvEditor`,
  `ProgressBar`, or duplicate `uploadEligibility` imports return to the page.
- UploadPage view/component split phase 5:
  `BatchActionBar.tsx` now owns the batch validation, batch PDF conversion, and
  batch import action buttons. `UploadPage.tsx` passes files, busy flags, and
  handlers into the bar. The refactor test now fails if batch action button
  rendering or eligibility counts return to the page.
- UploadPage view/component split phase 6:
  `BatchImportConfirmModal.tsx` now owns the batch import confirmation dialog,
  including summary count, warning copy, skipped-error notice, and pending file
  list. `UploadPage.tsx` only passes open/files/close/confirm props. The
  refactor test now fails if the dialog rendering returns to the page.
- Static GUI repair:
  `gui/app.js` was rewritten with valid Traditional Chinese fallback content
  and current guided-question/kit/recipe/runtime behavior. `tools\test-gui-static.ps1`
  now fails when `node --check` returns a non-zero exit code, preventing hidden
  JavaScript syntax failures. Browser smoke also passes after avoiding hidden
  duplicate `dist/generated-system` text across tabs.
- UploadPage orchestration split phase 7:
  `uploadBatchOrchestrator.ts` now owns the batch validation and batch PDF
  conversion loops. `UploadPage.tsx` delegates `handleValidateAll` and
  `handleConvertAll` to `runBatchValidation` and `runBatchConversion`, while
  keeping single-file validation/conversion behavior local. The refactor test
  now fails if batch target filtering, loop control, or completion toast logic
  returns to the page.
- UploadPage orchestration split phase 8:
  `uploadBatchOrchestrator.ts` now also owns batch import commit/poll loops via
  `runBatchImport`. `UploadPage.tsx` still owns confirmation state,
  eligibility checks, start/success/error toast decisions, and post-import
  cleanup, but per-file commit, polling, progress, row-count accumulation, and
  `completeImport(file.id)` now live in the helper. The refactor test now
  fails if the batch import loop returns to the page or if `runBatchImport` is
  missing.
- UploadPage orchestration split phase 9:
  `uploadBatchOrchestrator.ts` now also owns single-file import commit/poll
  loops via `runSingleImport`. `UploadPage.tsx` still owns the single import
  confirmation state, start/success/error toast decisions, and post-import
  cleanup. The refactor test now fails if single import progress, polling, or
  `completeImport(id)` details return to the page.
- UploadPage orchestration split phase 10:
  `uploadPdfConversionOrchestrator.ts` now owns PDF conversion trigger/status
  polling/progress orchestration through `runPdfConversion`. `UploadPage.tsx`
  still owns converted CSV output fetching, generated CSV file construction,
  file replacement, and page-level toast decisions. The refactor test now fails
  if max retry/polling logic returns to the page or if the helper is missing.
- UploadPage edit/helper split phase 11:
  `uploadCsvEditUtils.ts` now owns CSV serialization, cell updates, edit-state
  reset mechanics, and save/rebuild-file behavior. `UploadPage.tsx` still owns
  `EDIT_ENABLED` checks and toast decisions. The refactor test now fails if
  CSV edit/save implementation details return to the page.
- UploadPage validation split phase 12:
  `uploadValidationOrchestrator.ts` now owns PDF upload validation via
  `runPdfValidation`, including upload API call, begin/success/failure state
  transitions, and validation result construction. `UploadPage.tsx` still owns
  page-level success/error toast decisions. The refactor test now fails if PDF
  upload validation details return to the page.
- UploadPage validation split phase 13:
  `uploadValidationOrchestrator.ts` now also owns CSV validation job
  orchestration via `runCsvValidationJob`, including CSV file rebuild/upload
  source selection, import job creation, duplicate-file confirmation callback,
  CSV parse, progress checkpoints, job polling, and validation timeout
  detection. `UploadPage.tsx` still owns validation result toast decisions,
  error fetching/flattening, and final passed/errors/failed state handling. The
  refactor test now fails if CSV import-job creation, duplicate detection, file
  rebuild, or validation polling logic returns to the page.
- UploadPage validation helper split phase 14:
  `uploadValidationErrorUtils.ts` now owns import validation error flattening
  through `flattenImportValidationErrors`. `UploadPage.tsx` still owns fetching
  import errors, final workflow state, and toast decisions. The refactor test
  now fails if row flattening details return to the page or the helper is
  missing.
- UploadPage file-add helper split phase 15:
  `uploadFileAddUtils.ts` now owns file-add validation and construction through
  `buildUploadFilesToAdd`, including CSV/PDF extension checks, local duplicate
  detection, size checks, lot number derivation, PDF defaults, and `UploadedFile`
  construction. `UploadPage.tsx` still owns the confirm prompt, toast messages,
  and final `setFiles` append. The refactor test now fails if file-add workflow
  details return to the page or the helper is missing.
- UploadPage API setup hook split phase 16:
  `useUploadApi.ts` now owns tenant header construction and upload API client
  memoization through `useUploadApi`. `UploadPage.tsx` only calls
  `useUploadApi(t)`. The refactor test now fails if `TENANT_STORAGE_KEY`,
  `buildTenantHeaders`, `createUploadApiClient`, or direct API client
  memoization returns to the page.
- UploadPage async utility split phase 17:
  `uploadAsyncUtils.ts` now owns the shared delay helper through `delay`.
  `UploadPage.tsx` imports `delay` and passes it into validation, conversion,
  and import orchestrators as `sleep: delay`. The refactor test now fails if a
  local `sleep` or `setTimeout(resolve, ms)` implementation returns to the page.
- UploadPage validation toast helper split phase 18:
  `uploadValidationToastUtils.ts` now owns validation-result toast routing
  through `showValidationResultToast`, including PDF upload result, edit-disabled
  notice, CSV failed/errors/passed, and CSV exception cases. `UploadPage.tsx`
  still owns validation state transitions and return outcomes, but passes
  validation toast context into the helper. The refactor test now fails if
  validation result toast keys return to the page.
- UploadPage import toast helper split phase 19:
  `uploadImportToastUtils.ts` now owns import-result toast routing for batch and
  single imports, including unavailable import reasons, skipped invalid files,
  start/completed import notices, cleanup remaining/all-done notices, missing
  target errors, and import error display. `UploadPage.tsx` still owns import
  eligibility filtering, import state transitions, and cleanup timing. The
  refactor test now fails if import result toast keys return to the page.
- UploadPage PDF conversion toast helper split phase 20:
  `uploadPdfConvertToastUtils.ts` now owns PDF conversion toast routing,
  including missing process id, CSV fetch progress, converted CSV success,
  no-output, output-fetch failure, conversion failure, and still-processing
  notices. `UploadPage.tsx` still owns conversion orchestration, converted CSV
  output fetching, and file replacement decisions. The refactor test now fails
  if PDF conversion toast keys return to the page.
- UploadPage CSV edit toast helper split phase 21:
  `uploadCsvEditToastUtils.ts` now owns CSV edit/save toast routing, including
  edit-disabled, save-error, and changes-applied notices. `UploadPage.tsx` still
  owns edit enablement checks, save result branching, file state updates, and
  CSV data mutation. The refactor test now fails if CSV save toast keys return
  to the page.
- UploadPage file-add toast helper split phase 22:
  `uploadFileAddToastUtils.ts` now owns file-add toast routing through
  `showFileAddResultToasts`, including unsupported file type, skipped likely
  duplicates, same-name notices, too-large errors, and files-added success.
  `UploadPage.tsx` still owns duplicate confirmation, file-add helper
  invocation, and final file append. The refactor test now fails if file-add
  toast keys return to the page. The generator also now uses a precise
  `handleValidate =` boundary when replacing `handleFiles`, preventing cold-path
  refactors from accidentally swallowing `handleValidate`.
- UploadPage async cleanup scheduling split phase 23:
  `uploadAsyncUtils.ts` now owns delayed cleanup scheduling through
  `scheduleAfterDelay`. `UploadPage.tsx` delegates the 2000 ms post-import
  cleanup timer for batch and single imports while still owning cleanup actions,
  remaining-file calculation, and cleanup toast context. The refactor test now
  fails if direct `setTimeout(() =>` cleanup scheduling returns to the page or
  the scheduling helper is missing.

## Current Next Priority

Continue `UploadPage` production refactor. Phase 24 is complete — post-import
cleanup scheduling is now in `uploadImportCleanupUtils.ts` via
`scheduleBatchPostImportCleanup` / `scheduleSinglePostImportCleanup`.

Next candidates:
1. Extract the `performBatchImport` eligibility check + `beginImport` +
   `resetImport` error path into a batch import orchestrator, keeping only
   `setShowBatchImportConfirm(false)` and the eligibility guard in the page.
2. Or continue reducing `handleValidate` — move the final CSV result dispatch
   (`completeValidationFailure` / `completeValidationWithErrors` /
   `completeValidationPassed`) into `uploadValidationOrchestrator.ts`.

Keep `tools\test-upload-page-refactor.ps1` as the guardrail and add targeted
assertions for each extracted helper.

## Browser GUI Test

Real browser smoke test command:

```powershell
powershell -ExecutionPolicy Bypass -File tools\test-gui-browser.ps1
```

It uses Playwright through `output\playwright\runner`, opens
`gui\index.html`, checks the configure/runtime/preview/generate views, and
writes:

```text
output\playwright\gui-smoke.png
```

The test intentionally uses `file:///` mode because starting a local background
server can be blocked by the current sandbox login session.

## Test Command

Run the full local verification with:

```powershell
powershell -ExecutionPolicy Bypass -File tools\test-all.ps1
```

Expected result:

```text
ALL TESTS PASSED
```

## Git Repository

The project folder is now its own Git repository:

```text
C:\Users\gslab\Documents\New project\form-system-kit-composer
```

Remote:

```text
origin https://github.com/yucheng384752/system-assembly-platform.git
```

## Registered Codex Skill

The Obsidian documentation governance skill is registered at:

```text
C:\Users\gslab\.codex\skills\form-system-kit-composer-obsidian\SKILL.md
```

## Next Best Work

1. Continue UploadPage refactor by extracting the next small page orchestration
   helper with tests.
2. Expand browser GUI smoke tests to multiple viewports.
3. Pin dependency versions for production targets.
4. Run full dependency install/start verification when package installation and
   database credentials are available.

## Prompt For Next Chat

Use this short prompt in a new chat window:

```text
Read C:\Users\gslab\Documents\New project\form-system-kit-composer\HANDOFF.md and TODO.md, then continue the Next Highest Priority work. Continue from the current UploadPage production refactor and do not redo completed phases. The next suggested priority is extracting the performBatchImport eligibility+beginImport+reset-on-error surface or the handleValidate final CSV result dispatch into a helper, and updating tools\test-upload-page-refactor.ps1 as the guardrail. After each implemented function, run the targeted test and tools\test-all.ps1. Report in Traditional Chinese with: feature completed, files changed, test results, and next step.
```

## Compact State For Next Chat

- Project root: `C:\Users\gslab\Documents\New project\form-system-kit-composer`
- User goal: turn selected kits into an unzip-and-run generated system package.
- MOD subscription: feature/backlog only; do not implement runtime subscription
  middleware until the user confirms.
- Obsidian rule: future long-form notes/architecture docs belong under
  `C:\Users\gslab\Desktop\Form System Kit Composer Obsidian`.
- Current highest-priority implementation track: continue reducing
  `generated\mvp-import-flow\form-analysis-server\frontend\src\pages\UploadPage.tsx`.
- Refactor source of truth: edit `tools\apply-upload-page-refactor.ps1`; it
  regenerates `UploadPage.tsx` and files under `frontend\src\pages\upload`.
- Guardrail test: `tools\test-upload-page-refactor.ps1`.
- Full test: `tools\test-all.ps1`; latest expected and observed result is
  `ALL TESTS PASSED`.
- Latest completed UploadPage phase: phase 24, post-import cleanup extracted
  into `uploadImportCleanupUtils.ts` via `scheduleBatchPostImportCleanup` and
  `scheduleSinglePostImportCleanup`. `UploadPage.tsx` no longer imports
  `scheduleAfterDelay` directly.
- Next likely extraction: (a) `performBatchImport` eligibility check +
  `beginImport` + error reset into batch import orchestrator, or (b) final CSV
  validation result dispatch into `uploadValidationOrchestrator.ts`.
- GUI fix in this session: added back `architectureQuestions`, `data-guide-choice`,
  and `architecture-guide` overlay to `gui/app.js` and `gui/index.html` (were
  lost during a prior rewrite).
- Git status note: the repository is initialized with origin
  `https://github.com/yucheng384752/system-assembly-platform.git`, but most
  files may still appear untracked. Do not commit/stage unless the user asks.
