# TODO

## Completed

- Added kit manifest support for `subfeatures`, `options`, entitlement metadata,
  backend router registrations, and templates.
- Added `schemas/recipe.schema.json` and expanded `schemas/kit.schema.json`.
- Added guided card-style architecture questions in the GUI.
- Removed the unused "recompose original system" GUI action.
- Added kit classification and color mapping in the GUI.
- Added chart summary rendering options to `analytics-kit`.
- Moved MOD subscription to feature/backlog status until the user confirms runtime development.
- Added backend router registry generation and application to the generated app.
- Added frontend tab registry generation.
- Added database assembly plan generation.
- Added entitlement plan generation.
- Added MVP extraction with dry-run support.
- Added generated system assembly under `dist/generated-system`.
- Added generated system archive support under `dist/generated-system.zip`.
- Added package folder generation under `dist/form-system-generated-package`.
- Added generated system validation and package folder validation.
- Added GUI static smoke test, resolver smoke test, and full `tools/test-all.ps1`.
- Added real browser GUI smoke test:
  - `tools/test-gui-browser.ps1`
  - `tools/test-gui-browser.mjs`
  - screenshot output: `output\playwright\gui-smoke.png`
- Added kit expansion strategy and kit development standard documents.
- Added Obsidian documentation governance:
  - `C:\Users\gslab\Desktop\Form System Kit Composer Obsidian\06 文件治理與 Skill.md`
  - `C:\Users\gslab\Desktop\Form System Kit Composer Obsidian\07 前端更新紀錄.md`
  - `C:\Users\gslab\Desktop\Form System Kit Composer Obsidian\08 系統架構圖.md`
  - `C:\Users\gslab\Desktop\Form System Kit Composer Obsidian\Skills\form-system-kit-composer-obsidian\SKILL.md`
- Updated the static GUI to clean Traditional Chinese copy and current feature support.
- Upgraded generated runtime scripts:
  - `scripts/check-prerequisites.ps1`
  - `scripts/install.ps1`
  - `scripts/migrate.ps1`
  - `scripts/start.ps1`
  - `dependency-manifest.json`
- Added dependency file generation:
  - `tools/generate-dependency-files.ps1`
  - `tools/test-dependency-files.ps1`
  - generated `backend/requirements.txt`
  - generated `frontend/package.json`
  - generated `dependency-plan.json`
- Added database bootstrap generation:
  - `tools/generate-db-bootstrap.ps1`
  - `tools/test-db-bootstrap.ps1`
  - generated `backend/app/core/generated_db_bootstrap.py`
  - generated `scripts/check-db.ps1`
  - generated `db-bootstrap-plan.json`
  - `scripts/migrate.ps1` now falls back to SQLAlchemy bootstrap when Alembic
    is not present.
- Added generated start validation:
  - `tools/generate-model-init.ps1`
  - `tools/test-generated-start.ps1`
  - generated `backend/app/models/__init__.py`
  - generated `scripts/smoke-start.ps1`
  - MVP extraction now includes core tenant/auth, schema registry, upload,
    import, station, and base record model dependencies required before app
    startup.
- Added process supervision scripts:
  - `tools/test-process-supervision.ps1`
  - generated `scripts/status.ps1`
  - generated `scripts/stop.ps1`
  - generated `scripts/restart.ps1`
  - `scripts/start.ps1 -Background` now writes pid files under `runtime` and
    backend/frontend logs under `logs`.
- Added GUI recipe export and assembly command output:
  - `tools/test-gui-recipe-export.ps1`
  - GUI output view now renders valid recipe JSON from current selections.
  - GUI supports copying/downloading `gui-selected-form-system.recipe.json`.
  - GUI lists assembly commands for validate, resolve, extract, assemble, and
    validate-generated-system.
- Added UploadPage production refactor phase 1:
  - `tools/apply-upload-page-refactor.ps1`
  - `tools/test-upload-page-refactor.ps1`
  - extracted `uploadTypes.ts`, `uploadFileUtils.ts`, and `uploadProgress.ts`
    under `frontend/src/pages/upload`.
  - `extract-mvp-flow.ps1` applies the refactor after every MVP extraction.
- Added UploadPage API client split phase 2:
  - extracted `uploadApiClient.ts` under `frontend/src/pages/upload`.
  - moved PDF convert status, converted CSV outputs, and import job status
    fetch helpers behind `createUploadApiClient`.
  - `UploadPage.tsx` now instantiates `uploadApi` and calls the extracted
    client for those repeated query paths.
- Added UploadPage API client split phase 3:
  - moved PDF upload, v2 import job creation, import error query, PDF convert
    trigger, and import commit actions behind `createUploadApiClient`.
  - updated `tools\test-upload-page-refactor.ps1` to fail if inline fetch
    actions return to `UploadPage.tsx` or if duplicated `uploadApi.uploadApi`
    replacements are generated.
- Added UploadPage workflow hook split phase 1:
  - extracted `useUploadWorkflow.ts` under `frontend/src/pages/upload`.
  - moved `files`, `setFiles`, and `filesRef` synchronization behind the hook.
  - moved basic file transitions for remove and expand/collapse into hook
    actions.
  - extended `tools\test-upload-page-refactor.ps1` to verify hook generation
    and page delegation.
- Added UploadPage workflow hook split phase 2:
  - moved PDF validation state transitions into `useUploadWorkflow.ts`.
  - `UploadPage.tsx` now delegates PDF upload begin/success/failure state
    updates to `beginPdfValidation`, `completePdfUpload`, and
    `failPdfValidation`.
  - extended `tools\test-upload-page-refactor.ps1` to prevent PDF validation
    transition details from moving back into the page.
- Added UploadPage workflow hook split phase 3:
  - moved CSV validation state transitions into `useUploadWorkflow.ts`.
  - `UploadPage.tsx` now delegates CSV validation begin/progress/job
    preparation/poll/failure/error/pass state updates to workflow actions.
  - extended `tools\test-upload-page-refactor.ps1` to prevent CSV validation
    transition details from moving back into the page.
- Added UploadPage workflow hook split phase 4:
  - moved PDF conversion state transitions into `useUploadWorkflow.ts`.
  - `UploadPage.tsx` now delegates PDF convert begin/job/progress/replace/fail
    state updates to workflow actions.
  - extended `tools\test-upload-page-refactor.ps1` to prevent PDF conversion
    transition details from moving back into the page.
- Added UploadPage workflow hook split phase 5:
  - moved single and batch import state transitions into
    `useUploadWorkflow.ts`.
  - `UploadPage.tsx` now delegates import begin/progress/complete/reset/remove
    state updates to workflow actions.
  - extended `tools\test-upload-page-refactor.ps1` to prevent import
    transition details from moving back into the page and to ensure single
    import cleanup removes the imported file exactly once.
- Added UploadPage view/helper split phase 1:
  - extracted PDF conversion output-to-CSV-file creation into
    `buildUploadedCsvFilesFromPdfOutputs`.
  - `UploadPage.tsx` now delegates converted CSV file construction to
    `uploadFileUtils.ts`.
  - extended `tools\test-upload-page-refactor.ps1` to prevent PDF output file
    construction details from moving back into the page.
- Added UploadPage view/helper split phase 2:
  - extracted upload eligibility predicates into `uploadEligibility.ts`.
  - `UploadPage.tsx` now delegates validate/convert/import eligibility checks
    to named helper predicates.
  - extended `tools\test-upload-page-refactor.ps1` to prevent local predicate
    definitions from moving back into the page.
- Hardened UploadPage view/helper split phase 2:
  - replaced remaining batch-import modal eligibility filters with
    `uploadEligibility.ts` predicates.
  - extended `tools\test-upload-page-refactor.ps1` to fail on inline validated,
    uploaded, or validation-error predicate bodies in `UploadPage.tsx`.
- Added UploadPage view/component split phase 3:
  - extracted the drag-and-drop upload selector into `FileDropArea.tsx`.
  - `UploadPage.tsx` now imports the file drop area instead of owning the
    component implementation.
  - extended `tools\test-upload-page-refactor.ps1` to fail if `FileDropArea`
    moves back into `UploadPage.tsx` or the extracted upload UI is missing.
- Added UploadPage view/component split phase 4:
  - extracted uploaded file card and CSV editor UI into
    `UploadedFileCard.tsx`.
  - `UploadPage.tsx` now owns the upload list wiring while the card module owns
    per-file actions, progress rendering, validation badges, and CSV editing.
  - removed duplicate `uploadEligibility` import generation and added a test
    guard for it.
  - extended `tools\test-upload-page-refactor.ps1` to fail if
    `UploadedFileCard`, `CsvEditor`, or `ProgressBar` ownership moves back into
    `UploadPage.tsx`.
- Added UploadPage view/component split phase 5:
  - extracted batch validation, batch PDF conversion, and batch import action
    buttons into `BatchActionBar.tsx`.
  - `UploadPage.tsx` now passes files, busy flags, and handlers into the batch
    action bar instead of owning button eligibility/title rendering.
  - extended `tools\test-upload-page-refactor.ps1` to fail if
    `className="batch-actions"` or batch action eligibility rendering moves
    back into `UploadPage.tsx`.
- Added UploadPage view/component split phase 6:
  - extracted the batch import confirmation dialog into
    `BatchImportConfirmModal.tsx`.
  - `UploadPage.tsx` now passes open/files/close/confirm props instead of
    owning the modal summary, warning, skipped-error notice, or pending file
    list rendering.
  - extended `tools\test-upload-page-refactor.ps1` to fail if batch import
    confirmation rendering moves back into `UploadPage.tsx`.
- Repaired static GUI runtime:
  - rewrote `gui/app.js` with valid Traditional Chinese fallback content and
    preserved guided questions, kit catalog, recipe export, runtime, preview,
    and generation views.
  - hardened `tools\test-gui-static.ps1` so `node --check` failures now fail
    the test instead of printing a hidden error after success.
  - adjusted runtime copy to avoid hidden duplicate text that made browser
    smoke tests unstable.
- Added UploadPage orchestration split phase 7:
  - extracted batch validation and batch PDF conversion loops into
    `uploadBatchOrchestrator.ts`.
  - `UploadPage.tsx` now delegates `handleValidateAll` and `handleConvertAll`
    to `runBatchValidation` and `runBatchConversion`.
  - moved `ValidateOutcome` into the orchestration helper module.
  - extended `tools\test-upload-page-refactor.ps1` to fail if batch
    validation/conversion target filtering, loop control, or completion toast
    logic returns to `UploadPage.tsx`.
- Added UploadPage orchestration split phase 8:
  - extracted batch import commit/poll orchestration into
    `runBatchImport` in `uploadBatchOrchestrator.ts`.
  - `UploadPage.tsx` now delegates per-file import commit, import job polling,
    progress updates, row-count accumulation, and per-file completion updates
    to the helper.
  - kept page-level confirmation state, pre-import eligibility checks,
    start/success/error toast decisions, and post-import cleanup in
    `UploadPage.tsx`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if the batch import
    commit/poll loop returns to `UploadPage.tsx` or if `runBatchImport` is
    missing from the orchestration helper.
- Added UploadPage orchestration split phase 9:
  - extracted single-file import commit/poll orchestration into
    `runSingleImport` in `uploadBatchOrchestrator.ts`.
  - `UploadPage.tsx` now delegates single-file import commit, import job
    polling, progress updates, and `completeImport(file.id)` to the helper.
  - kept single import confirmation state, start/success/error toast decisions,
    and post-import cleanup in `UploadPage.tsx`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if single import
    progress/poll/complete details return to `UploadPage.tsx`.
- Added UploadPage orchestration split phase 10:
  - extracted PDF conversion trigger/status polling/progress orchestration into
    `runPdfConversion` in `uploadPdfConversionOrchestrator.ts`.
  - `UploadPage.tsx` now delegates PDF convert job trigger, transient polling
    retries, progress updates, and completed/failed/still-processing outcome
    detection to the helper.
  - kept converted CSV output fetching, generated CSV file construction, file
    replacement, and page-level toast decisions in `UploadPage.tsx`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if PDF conversion
    polling details return to `UploadPage.tsx` or if the helper module is
    missing expected behavior.
- Added UploadPage edit/helper split phase 11:
  - extracted CSV serialization, cell updates, and save/rebuild-file behavior
    into `uploadCsvEditUtils.ts`.
  - `UploadPage.tsx` now delegates cell edit reset logic to
    `updateCsvCellInFiles` and save/revalidate file rebuilding to
    `saveCsvChangesInFiles`.
  - kept `EDIT_ENABLED` checks and toast decisions in `UploadPage.tsx`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if CSV edit/save
    implementation details return to `UploadPage.tsx`.
- Added UploadPage validation split phase 12:
  - extracted PDF upload validation into `runPdfValidation` in
    `uploadValidationOrchestrator.ts`.
  - `UploadPage.tsx` now delegates PDF upload, begin/success/failure state
    transitions, and validation result construction to the helper.
  - kept page-level success/error toast decisions in `UploadPage.tsx`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if PDF upload
    validation details return to `UploadPage.tsx` or if the helper module is
    missing expected behavior.
- Added UploadPage validation split phase 13:
  - extracted CSV validation job orchestration into `runCsvValidationJob` in
    `uploadValidationOrchestrator.ts`.
  - `UploadPage.tsx` now delegates CSV file rebuild/upload source selection,
    import job creation, duplicate-file confirmation callback, CSV parse,
    progress checkpoints, job polling, and validation timeout detection to the
    helper.
  - kept validation result toast decisions, error fetching/flattening, and
    final passed/errors/failed state handling in `UploadPage.tsx`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if import-job
    creation, duplicate detection, file rebuild, or validation polling logic
    returns to `UploadPage.tsx`.
- Added UploadPage validation helper split phase 14:
  - extracted import validation error flattening into
    `flattenImportValidationErrors` in `uploadValidationErrorUtils.ts`.
  - `UploadPage.tsx` now delegates v2 import error row normalization while
    keeping error fetching, final validation workflow state, and toast
    decisions local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if flattening
    details return to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage file-add helper split phase 15:
  - extracted file-add validation and `UploadedFile` construction into
    `buildUploadFilesToAdd` in `uploadFileAddUtils.ts`.
  - `UploadPage.tsx` now delegates extension checks, local duplicate detection,
    size checks, lot number derivation, PDF defaults, and new-file object
    construction while keeping confirm prompts, toast decisions, and final
    `setFiles` append local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if file-add
    workflow details return to `UploadPage.tsx` or if the helper module is
    missing.
- Added UploadPage API setup hook split phase 16:
  - extracted tenant header construction and upload API client memoization into
    `useUploadApi` in `useUploadApi.ts`.
  - `UploadPage.tsx` now calls `useUploadApi(t)` instead of importing
    `TENANT_STORAGE_KEY` or `createUploadApiClient` directly.
  - extended `tools\test-upload-page-refactor.ps1` to fail if API setup details
    return to `UploadPage.tsx` or if the hook module is missing.
- Added UploadPage async utility split phase 17:
  - extracted the shared timer helper into `delay` in `uploadAsyncUtils.ts`.
  - `UploadPage.tsx` now passes `sleep: delay` into validation, PDF conversion,
    batch import, and single import orchestrators instead of declaring a local
    `sleep` function.
  - extended `tools\test-upload-page-refactor.ps1` to fail if local timer
    plumbing returns to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage validation toast helper split phase 18:
  - extracted validation-result toast routing into `showValidationResultToast`
    in `uploadValidationToastUtils.ts`.
  - `UploadPage.tsx` now delegates PDF validation result, edit-disabled notice,
    CSV failed/errors/passed, and CSV exception toast decisions while keeping
    validation workflow state and return outcomes local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if validation result
    toast keys return to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage import toast helper split phase 19:
  - extracted batch and single import result toast routing into
    `uploadImportToastUtils.ts`.
  - `UploadPage.tsx` now delegates unavailable import reasons, skipped-invalid
    notices, start/completed notices, cleanup remaining/all-done notices,
    missing-target errors, and import error display while keeping eligibility
    filtering, import state transitions, and cleanup timing local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if import result
    toast keys return to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage PDF conversion toast helper split phase 20:
  - extracted PDF conversion toast routing into
    `uploadPdfConvertToastUtils.ts`.
  - `UploadPage.tsx` now delegates missing-process, CSV-fetching,
    converted-CSV success, no-output, output-fetch failure, conversion failure,
    and still-processing notices while keeping conversion orchestration,
    converted output fetching, and file replacement decisions local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if PDF conversion
    toast keys return to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage CSV edit toast helper split phase 21:
  - extracted CSV edit/save toast routing into `uploadCsvEditToastUtils.ts`.
  - `UploadPage.tsx` now delegates edit-disabled, save-error, and
    changes-applied notices while keeping edit enablement checks, save result
    branching, file state updates, and CSV data mutation local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if CSV save toast
    keys return to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage file-add toast helper split phase 22:
  - extracted file-add toast routing into `showFileAddResultToasts` in
    `uploadFileAddToastUtils.ts`.
  - `UploadPage.tsx` now delegates unsupported file type, skipped likely
    duplicate, same-name, too-large, and files-added notices while keeping
    duplicate confirmation, file-add helper invocation, and final file append
    local.
  - hardened `tools\apply-upload-page-refactor.ps1` so the `handleFiles`
    replacement stops only at `const handleValidate =`, preventing cold-path
    refactors from accidentally swallowing `handleValidate`.
  - extended `tools\test-upload-page-refactor.ps1` to fail if file-add toast
    keys return to `UploadPage.tsx` or if the helper module is missing.
- Added UploadPage post-import cleanup helper split phase 24:
  - extracted post-import cleanup scheduling into `scheduleBatchPostImportCleanup`
    and `scheduleSinglePostImportCleanup` in `uploadImportCleanupUtils.ts`.
  - `UploadPage.tsx` now passes `ids`/`id`, `removeImportedFiles`, `showToast`,
    and `t` into the helpers instead of owning the `scheduleAfterDelay` +
    `removeImportedFiles` + cleanup toast blocks directly.
  - `showBatchImportCleanupToast` and `showSingleImportCleanupToast` are now
    only used inside `uploadImportCleanupUtils.ts`, not imported by the page.
  - `scheduleAfterDelay` is no longer imported by `UploadPage.tsx`; only `delay`
    remains for passing `sleep:` into orchestrators.
  - extended `tools\test-upload-page-refactor.ps1` to fail if cleanup scheduling
    details return to `UploadPage.tsx` or if the helper module is missing.
  - restored missing GUI guided architecture question stubs (`architectureQuestions`,
    `data-guide-choice`, `architecture-guide`) that were lost during GUI rewrite.
- Added UploadPage async cleanup scheduling split phase 23:
  - extracted delayed cleanup scheduling into `scheduleAfterDelay` in
    `uploadAsyncUtils.ts`.
  - `UploadPage.tsx` now delegates the 2000 ms post-import cleanup timer for
    batch and single imports while keeping cleanup actions, remaining-file
    calculation, and cleanup toast context local.
  - extended `tools\test-upload-page-refactor.ps1` to fail if direct
    `setTimeout(() =>` cleanup scheduling returns to `UploadPage.tsx` or if the
    scheduling helper module behavior is missing.
- Initialized project git repository and set origin:
  - `https://github.com/yucheng384752/system-assembly-platform.git`
- Registered Codex skill:
  - `C:\Users\gslab\.codex\skills\form-system-kit-composer-obsidian\SKILL.md`

## Current Runtime Status

The generated package is now a runnable envelope. After extraction, the operator
has script entry points for prerequisite checks, install, migration, and start.

Dependency manifests are now generated from selected backend/frontend imports.
The generated output includes `backend/requirements.txt`,
`frontend/package.json`, and `dependency-plan.json`.

Database bootstrap files are now generated from `assembly\db-plan`. The
generated `scripts\migrate.ps1` uses Alembic when available and otherwise
falls back to `backend\app\core\generated_db_bootstrap.py`.

Generated start validation now compiles the selected backend source and checks
startup script wiring. Full `-ImportApp` and `-StartBackend` modes are available
after generated dependencies and a real database are installed.

Generated process supervision now supports background start, status, stop, and
restart scripts with pid/log tracking.

GUI selections now become a concrete recipe JSON artifact in the output view.
Static and browser tests verify the recipe export wiring.

UploadPage refactor phase 1 now separates shared upload types, CSV/file helpers,
and progress mapping from the page shell.

UploadPage refactor phase 2/3 now separates repeated API query helpers and
remaining upload/import/PDF action calls into a focused upload API client.
UploadPage workflow hook phase 1 now centralizes file state, the latest-files
ref, and basic remove/expand transitions.
UploadPage workflow hook phase 2 now centralizes PDF validation/upload
transitions.
UploadPage workflow hook phase 3 now centralizes CSV validation state
transitions while leaving API calls and toast decisions in the page.
UploadPage workflow hook phase 4 now centralizes PDF conversion state
transitions while leaving API calls, CSV file construction, and toast decisions
in the page.
UploadPage workflow hook phase 5 now centralizes single and batch import state
transitions while leaving API calls, polling, and toast decisions in the page.
UploadPage view/helper split phase 1 now centralizes PDF conversion output file
construction in upload utilities.
UploadPage view/helper split phase 2 now centralizes upload eligibility rules
in `uploadEligibility.ts`.
UploadPage view/component split phase 3 now centralizes the drag-and-drop file
selection UI in `FileDropArea.tsx`.
UploadPage view/component split phase 4 now centralizes the uploaded file card
and CSV editor UI in `UploadedFileCard.tsx`.
UploadPage view/component split phase 5 now centralizes the batch action bar in
`BatchActionBar.tsx`.
UploadPage view/component split phase 6 now centralizes the batch import
confirmation dialog in `BatchImportConfirmModal.tsx`.
The static GUI now has a valid `gui/app.js`; syntax failures are enforced by
`tools\test-gui-static.ps1`.
UploadPage orchestration split phase 7 now centralizes batch validation and
batch PDF conversion loops in `uploadBatchOrchestrator.ts`.
UploadPage orchestration split phase 8 now centralizes batch import commit/poll
loops in `uploadBatchOrchestrator.ts`.
UploadPage orchestration split phase 9 now centralizes single-file import
commit/poll loops in `uploadBatchOrchestrator.ts`.
UploadPage orchestration split phase 10 now centralizes PDF conversion polling
in `uploadPdfConversionOrchestrator.ts`.
UploadPage edit/helper split phase 11 now centralizes CSV edit/save mechanics
in `uploadCsvEditUtils.ts`.
UploadPage validation split phase 12 now centralizes PDF upload validation in
`uploadValidationOrchestrator.ts`.
UploadPage validation split phase 13 now centralizes CSV validation job
orchestration in `uploadValidationOrchestrator.ts` while leaving final
validation result decisions in the page.
UploadPage validation helper split phase 14 now centralizes import validation
error flattening in `uploadValidationErrorUtils.ts`.
UploadPage file-add helper split phase 15 now centralizes file-add validation
and `UploadedFile` construction in `uploadFileAddUtils.ts`.
UploadPage API setup hook split phase 16 now centralizes tenant header
construction and API client memoization in `useUploadApi.ts`.
UploadPage async utility split phase 17 now centralizes shared polling delay in
`uploadAsyncUtils.ts`.
UploadPage validation toast helper split phase 18 now centralizes validation
result toast routing in `uploadValidationToastUtils.ts`.
UploadPage import toast helper split phase 19 now centralizes batch and single
import result toast routing in `uploadImportToastUtils.ts`.
UploadPage PDF conversion toast helper split phase 20 now centralizes PDF
conversion toast routing in `uploadPdfConvertToastUtils.ts`.
UploadPage CSV edit toast helper split phase 21 now centralizes CSV edit/save
toast routing in `uploadCsvEditToastUtils.ts`.
UploadPage file-add toast helper split phase 22 now centralizes file-add toast
routing in `uploadFileAddToastUtils.ts`.
UploadPage async cleanup scheduling split phase 23 now centralizes delayed
post-import cleanup scheduling in `uploadAsyncUtils.ts`.
UploadPage post-import cleanup helper split phase 24 now centralizes the
cleanup action (remove imported files + show cleanup toast) in
`uploadImportCleanupUtils.ts` through `scheduleBatchPostImportCleanup` and
`scheduleSinglePostImportCleanup`. `UploadPage.tsx` no longer imports
`scheduleAfterDelay` or the cleanup toast functions directly.

## Code Quality Improvement Phases

經由代碼審查確認的三階段改善計畫，依 UI 可見性 → 功能正確性 → 設計穩健性排序。

### Phase 1 — UI 與顯示層修正

目標：消除用戶可見的錯誤資訊與阻塞行為。

- [x] 新增 manifest 載入狀態警告：`loadKitCatalog()` 靜默降級，用戶無感知；在 Kit Catalog 面板加入警告橫幅。
- [x] 修正 fallback kit 名稱（5 處與 manifest 不一致）：`platform-core-kit`、`analytics-kit`、`station-admin-kit`、`audit-edit-kit`、`logs-ops-kit`。
- [x] 修正 `packageFiles()` 路徑：`assembly/mvp-resolved-plan.json` → `assembly/gui-selected-resolved-plan.json`（與實際組裝指令輸出一致）。
- [x] 修正 `parseSubfeatureKey()` 無 null 防護：key 格式錯誤時 `subfeatureId` 為 `undefined`。
- [x] 以非阻塞方式取代 `window.prompt()` 剪貼簿 fallback（目前會彈出同步 modal）。

### Phase 2 — 高優先：功能正確性修正

目標：消除邏輯缺陷與狀態管理反模式，確保 recipe 輸出正確。

- [x] 移除 `subfeatureList()` 硬編碼 fallback catalog：catalog 用 `slug()` 產生的 ID 與 manifest 不相容，切換時狀態不可恢復；manifest 失敗時直接回傳 `[]` 更誠實。
- [x] 修正 fallback `analytics-kit` 缺少兩個依賴：fallback 中依賴為 `["station-data-link-kit", "query-traceability-kit"]`，manifest 正確值為加上 `platform-core-kit` 與 `tenant-auth-kit`。
- [x] 提取 `computeDbEngine()` 純函數：目前 `renderDatabaseRecommendation()` 寫入 DOM，`buildRecipe()` 再從 DOM 讀回，渲染順序若異常 recipe 拿到空字串。
- [x] `addKitWithDependencies()`（app.js）加入循環依賴偵測：目前無 visited set，循環依賴會 stack overflow。
- [x] `Add-Kit`（resolve-recipe.ps1）加入循環依賴偵測：同樣問題的 PowerShell 版本。

### Phase 3 — 中優先：設計穩健性改善

目標：修補邊界案例、降低安全風險、理清資料模型所有權。

- [x] `removeOptionalKit()` 處理 `optionalDependencies`：目前移除 `upload-validation-kit` 不會連帶移除依賴它的 `import-pipeline-kit`（manifest 宣告為 optionalDependency）。
- [x] Kit card template 函數的 innerHTML XSS 緩解：`item.name`、`item.capability` 等 manifest 資料直接插入 innerHTML，需改用 `textContent` 或逸脫函數。
- [x] 修正 manifest 中 `platform-core-kit` 錯誤包含 `audit_event.py`：此模型屬 `audit-edit-kit`，不選稽核 kit 時仍會被提取。
- [x] 補齊 `mod-subscription-kit` 宣告的 template 文件或標注為 stub：manifest 中 `templates.backend` 指向不存在的 `templates/backend/mod-subscription/...` 路徑。

### Phase 4 — 最低優先：Schema 一致性與工具可靠性

目標：讓 GUI 輸出的 recipe 通過 schema 驗證、fallback 資料完整、驗證工具覆蓋實際錯誤。

- [x] 修正 `buildRecipe()` 欄位名稱：`schemaVersion` → `recipeVersion`（schema 要求欄位、現有 recipe 檔案皆使用 `recipeVersion`）。
- [x] 修正 `buildRecipe()` `featureFlags` 型別：輸出陣列 `["MOD_SUBSCRIPTION_ENABLED"]`，schema 要求為 object；改為 `{}`（resolver 已從 kit manifest 收集 flags，recipe 僅用於覆寫）。
- [x] 修正 `buildRecipe()` `frontendNavigation` 結構：輸出字串陣列，schema 要求每項須含 `tab`、`labelKey`、`kit` 欄位；GUI 無 UX 填寫導航項目，改為 `[]`。
- [x] 提取 `computeDbEngine()` 純函數（Phase 2 漏做）：`buildRecipe()` 仍從 DOM 讀取 `"PostgreSQL"`（大寫），schema enum 要求小寫 `"postgresql"`；提取後兩處共用同一計算結果。
- [x] 補齊 fallback `upload-validation-kit` 的 `optionalDependencies: ["import-pipeline-kit"]`：fallback 未傳第 8 參數，移除 upload-validation-kit 時不觸發連帶移除。
- [x] `validate-recipe.ps1` 加入 `featureFlags` 型別檢查：GUI 舊版輸出陣列時，驗證不報錯；現在明確拒絕 array。
- [x] 修正 `assemblyCommands()` 硬編碼 `mvp-import-flow.recipe.json`：應參照 GUI 匯出的 `gui-selected-form-system.recipe.json` 與對應 resolved plan 路徑。

---

## Next Highest Priority

### 1. UploadPage view/component split

- Planned function:
  - Continue splitting extracted `UploadPage` into smaller view components and
    focused helpers.
  - Reduce the remaining `UploadPage.tsx` upload/validation surface by
    extracting the next small page orchestration helper.
- Expected result:
  - Upload workflow becomes maintainable and easier to reuse in generated
    systems.
  - Unit tests can target state transitions and API calls without rendering the
    full page.
  - Next candidate: move the post-import cleanup action itself into a
    helper/workflow, or continue component/helper cleanup while keeping
    page-level workflow decisions explicit. Direct toast routing branches are
    already extracted.

### 2. Dependency version pinning

### 3. Full dependency install/start verification

- Planned function:
  - Run generated `scripts\install.ps1` in a controlled runtime with network or
    cached packages available.
  - Run `scripts\smoke-start.ps1 -ImportApp` after install.
  - Run `scripts\smoke-start.ps1 -StartBackend` after a real database is
    configured.
- Expected result:
  - The generated FastAPI app imports successfully.
  - The `/healthz` endpoint is verified by an automated start/stop smoke test.

- Planned function:
  - Extend `tools\generate-dependency-files.ps1` with runtime profiles.
  - Support generated dependency files with pinned production versions instead
    of only inferred package names and `latest`.
- Expected result:
  - Generated systems become reproducible across machines.
  - `dependency-plan.json` clearly records inferred packages, chosen versions,
    and any packages that require manual review.

### Additional Validation Backlog

- Expand browser GUI smoke test into multiple viewport checks.

## Standardization Backlog

- MySQL adapter for generated database connection plans.
- React component-level kit preview.
- Runtime preview for selected kit combinations.
- Vite/React production GUI migration if the current static GUI becomes too
  limiting.
- MOD subscription runtime middleware/service, pending explicit user approval.

## Recipe Status

Recipe backend/tooling is partially developed and currently usable:

- Done:
  - `schemas\recipe.schema.json`
  - `assembly\form-analysis-original.recipe.json`
  - `assembly\mvp-import-flow.recipe.json`
  - `tools\validate-recipe.ps1`
  - `tools\resolve-recipe.ps1`
  - resolved plan output in `assembly\resolved-plan.json` and
    `assembly\mvp-resolved-plan.json`
  - recipe support for `enabledKits`, `selectedSubfeatures`,
    `selectedSubfeatureOptions`, `featureFlags`, `frontendNavigation`, and
    database intent.
- Not done:
  - GUI selections are not yet written to a `.recipe.json` file.
  - GUI cannot yet trigger validate/resolve/extract/assemble directly.
  - Recipe authoring UX is still preview-only in the static GUI.
