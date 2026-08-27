# AI Development Spec 專案驗證報表

產出時間：2026-07-05

驗證範圍：依 `ai-development-spec` 原則檢查 Form System Kit Composer 專案的 source-of-truth、schema/API/DB contract、kit assembly 流程、生成系統、測試可執行性、安全與維護風險。

## Executive Summary

本專案目前具備清楚的 kit/recipe/schema/assembly/generated-system 分層，核心資料流符合 Data-First 方向：`schemas/` 定義 recipe 與 kit manifest，`assembly/` 產生 resolved plan、DB plan、Assembly IR，`kits/*/kit.contract.json` 補充 kit 間 API/DB contract，`dist/generated-system` 則作為可部署輸出。

本次核心驗證通過：

- Recipe schema validation 通過。
- Kit contract validation 通過：11 kits、25 API capabilities、8 DB capabilities。
- Generated system validation 通過。
- 主要 backend Python 檔案 compile 通過。
- GUI JS syntax check 通過。

主要風險集中在：

- `tools/issuer-private-key.pem` 與 `tools/keys/signing-private-key.pem` 存在於工作樹；目前未被 Git 追蹤，但仍應建立本機密鑰管理與輪替流程。
- `tools/test-all.ps1` 目前會在 `GUI static smoke` 失敗，測試基準仍期待舊的 `architectureQuestions` snippet，和目前 GUI 的 flow-based 實作不一致。
- `generated/mvp-import-flow/extraction-report.json` 顯示 MVP extraction 缺少 5 個 platform-core/kit broker 相關來源檔。
- `README.md` 與 `docs/development-standards.md` 有明顯文字編碼破損，會降低 handoff 與需求追蹤可靠性。
- 前端 build 未完成驗證，因為 `dist/generated-system/frontend/node_modules` 不存在，`vite` 無法執行。

## 驗證命令與結果

| 類別 | 命令 | 結果 |
|---|---|---|
| Recipe validation | `powershell -ExecutionPolicy Bypass -File .\tools\validate-recipe.ps1 -RecipePath .\assembly\mvp-import-flow.recipe.json` | PASS |
| Kit contract validation | `powershell -ExecutionPolicy Bypass -File .\tools\validate-kit-contracts.ps1 -ProjectRoot . -ResolvedPlanPath .\assembly\mvp-resolved-plan.json -OutputPath .\assembly\kit-contract-report.json` | PASS |
| Generated system validation | `powershell -ExecutionPolicy Bypass -File .\tools\validate-generated-system.ps1 -GeneratedRoot .\dist\generated-system` | PASS |
| Full local suite | `powershell -ExecutionPolicy Bypass -File .\tools\test-all.ps1` | FAIL at GUI static smoke |
| Backend compile | `python -m py_compile ...` for main generated backend files | PASS |
| GUI syntax | `node --check gui\app.js` | PASS |
| GUI server syntax | `node --check tools\serve-gui.cjs` | PASS |
| Frontend build | `npm.cmd run build` in `dist\generated-system\frontend` | NOT VERIFIED: `vite` not installed |

## Critical Issues

### 1. Local private keys exist inside the project workspace

Severity: Critical

Files:

- `tools/issuer-private-key.pem`
- `tools/keys/signing-private-key.pem`

Problem: Private signing keys are present in the project directory. `git ls-files` showed only `tools/keys/signing-public-key.pem` is tracked, so the private keys are not currently committed. However, keeping private keys inside the repo workspace still creates accidental copy/package/leak risk.

Why it matters: The generated package license/signature trust model depends on these keys. If leaked, an attacker can issue valid-looking licenses or package signatures.

Suggested fix:

- Move private keys to a non-repo secret store or user-local protected directory.
- Keep only public keys in repo.
- Add automated validation that fails if any `*-private-key.pem` or `BEGIN PRIVATE KEY` appears outside an approved secret path.
- Rotate keys if there is any chance these files were shared through zip, backup, or screen/session export.

## High Priority Issues

### 1. Full validation suite fails because GUI smoke test is stale

Severity: High

File: `tools/test-gui-static.ps1`

Problem: `test-all.ps1` fails at `GUI static smoke` because the test still requires `architectureQuestions`, but current `gui/app.js` appears to use a flow-based UI (`flows`, `flow-grid`, `data-flow-toggle`, `data-subflow-toggle`).

Why it matters: The project no longer has a green top-level validation command. This weakens merge confidence and makes regressions harder to distinguish from stale tests.

Suggested fix:

- Update `tools/test-gui-static.ps1` to assert current GUI contract:
  - `flow-grid`
  - `data-flow-toggle`
  - `data-subflow-toggle`
  - pem gate modal elements if required
  - package generation summary
- Keep a separate regression test for removed architecture-question behavior only if it is still intentionally supported.

### 2. MVP extraction reports missing platform core / kit broker sources

Severity: High

File: `generated/mvp-import-flow/extraction-report.json`

Problem: `missingSources` includes:

- `frontend/src/services/kitClient.ts`
- `backend/app/api/routes_kit_broker.py`
- `backend/app/core/kit_contracts.py`
- `backend/app/core/kit_broker.py`
- `backend/app/core/db_capabilities.py`

Why it matters: These are exactly the files that support generalized kit communication and broker capabilities. If the MVP extraction remains the source for downstream assembly, missing files can cause runtime import failure or degraded kit communication.

Suggested fix:

- Decide whether these files are required for MVP output.
- If required, ensure extraction source paths exist and are copied into `generated/mvp-import-flow`.
- If not required, remove them from the MVP resolved source list to prevent false missing-source reports.

### 3. Frontend production build is not currently verified

Severity: High

File: `dist/generated-system/frontend/package.json`

Problem: `npm.cmd run build` failed because `vite` is unavailable. `node_modules` is absent under `dist/generated-system/frontend`.

Why it matters: The generated frontend may have TypeScript or Vite build errors that are currently hidden. Given recent Query/Analytics/Generic Forms changes, build verification is important.

Suggested fix:

- Add a documented validation path that runs `npm install` or `npm ci` for generated frontend before `npm run build`.
- If offline packaging is expected, include an offline dependency validation step.
- Treat frontend build as a required release gate for generated packages.

## Medium Priority Issues

### 1. Documentation has encoding corruption

Severity: Medium

Files:

- `README.md`
- `docs/development-standards.md`

Problem: Several Chinese sections contain mojibake/corrupted text. Examples appear around Step 4, generated package notes, license signing examples, and development standards.

Why it matters: This project relies heavily on docs as handoff and process source-of-truth. Corrupted text breaks requirement traceability and increases AI-agent misunderstanding risk.

Suggested fix:

- Restore these files from a known-good UTF-8 source.
- Add an encoding check to validation, especially for docs that mix English and Traditional Chinese.

### 2. Resolved plan contains an empty API entry

Severity: Medium

File: `assembly/mvp-resolved-plan.json`

Problem: `enabledApis` starts with an empty string entry.

Why it matters: Empty API declarations weaken contract quality. They can leak into generated docs, capability maps, API broker metadata, or validation reports.

Suggested fix:

- Locate the kit manifest or resolver input producing the empty API.
- Reject empty API strings in schema or resolver validation.

### 3. GUI uses multiple dynamic `innerHTML` writes

Severity: Medium

File: `gui/app.js`

Problem: The GUI writes several dynamic UI fragments using `innerHTML`. Some calls are wrapped with `sanitizeHtml`, but not all call sites are obviously sanitized from the scan alone.

Why it matters: Kit names, recipe metadata, uploaded table names, field names, and generated content can become XSS vectors if any user-controlled string reaches unsanitized HTML.

Suggested fix:

- Audit all `innerHTML` assignments.
- Require `escapeHtml` or DOM node creation for user-provided values.
- Keep `sanitizeHtml` use explicit and covered by tests for uploaded CSV/table/column names.

## Data-First / Contract Assessment

Strengths:

- `schemas/recipe.schema.json`, `schemas/kit.schema.json`, and `schemas/assembly-ir.schema.json` provide explicit structured contracts.
- `assembly/kit-contract-report.json` currently reports no contract errors.
- `assembly/db-plan/db-assembly-plan.json` and Daihui schema inference exist as DB-facing source-of-truth.
- Kit contracts are present for 12 kit folders, including cross-cutting kits such as `platform-core-kit`, `query-traceability-kit`, `analytics-kit`, `generic-forms-kit`, and `logs-ops-kit`.

Gaps:

- `kit.schema.json` still leaves many important sections as broad `object` types, especially `frontend`, `database`, and parts of `externalServices`.
- API capability contracts are summarized, but endpoint input/output payload contracts are not strongly enforced by schema.
- DB contract validation currently checks declared capabilities, but should also assert migration/bootstrap compatibility and FK/index requirements.

Recommended contract improvements:

- Add strict schema for kit `database.tables`, `database.indexes`, `database.foreignKeys`, and storage ownership.
- Add per-API I/O contract files or embedded schemas for request/response payloads.
- Make `validate-kit-contracts.ps1` fail on empty API strings and missing I/O contract metadata.

## Security Assessment

Observed strengths:

- Private signing key paths are listed in `.gitignore`.
- Generated runtime config expects `SECRET_KEY`, API key auth, and non-default production values.
- `tools/keys/signing-public-key.pem` is the only signing key tracked by Git among checked key paths.

Risks:

- Private keys still reside inside the workspace.
- Generated docker compose defaults include fallback `SECRET_KEY=${SECRET_KEY:-changeme-replace-before-production}` and `.env.example` style defaults; acceptable for templates, but validation should fail production mode if unchanged.
- Browser-side API keys are stored in frontend local storage (`form_analysis_api_key`, `form_analysis_admin_api_key`), which increases XSS impact.

Recommended controls:

- Add a secret scanner to `test-all.ps1`.
- Add production config validation that blocks default `SECRET_KEY`, default DB password, and empty admin keys.
- Continue tightening XSS boundaries because local storage API keys amplify any script injection.

## Maintainability Assessment

Strengths:

- The project has a clear generation pipeline:
  - recipe -> resolver -> assembly IR -> backend/frontend registry -> DB plan -> generated system -> client package.
- Tooling is organized under `tools/`.
- Kit source and generated output are separated.

Risks:

- `dist/` and `generated/` are both large and frequently modified, making review noise high.
- Running validation can rewrite generated artifacts, so validation is not purely read-only.
- Some tests assert string snippets rather than behavior or contract outputs, causing brittle failures after UI refactors.

Recommendations:

- Separate read-only validation from regeneration commands.
- Add `tools/test-static-contracts.ps1` for schema/contract checks that never writes files.
- Keep GUI smoke tests tied to stable DOM contracts, not old implementation variable names.

## Testing Gaps

Missing or incomplete coverage:

- Frontend generated build was not verified because dependencies are not installed.
- Browser-level GUI flow was not run in this validation.
- Docker rebuild/deploy path was not run.
- Database migration/bootstrap was not executed against a live PostgreSQL instance.
- CSV upload/import E2E was not run with the user's Daihui data path in this validation.
- XSS tests for uploaded table/column names and recipe metadata are not visible.
- Secret scanning is not part of `test-all.ps1`.

## Recommended Fix Order

1. Move private keys out of the repo workspace and add secret scanning.
2. Update `tools/test-gui-static.ps1` so `test-all.ps1` becomes green again.
3. Resolve or intentionally suppress the 5 missing MVP extraction sources.
4. Install or provide frontend dependencies and run `npm run build` for generated frontend.
5. Repair corrupted UTF-8 docs.
6. Tighten kit/API/DB I/O contract schemas and reject empty API entries.
7. Add XSS-focused tests for GUI-generated HTML and uploaded CSV metadata.

## Final Risk Assessment

Current merge/release confidence: Medium.

The core assembly contracts and generated-system validation pass, which is a good baseline. However, the top-level test suite is not green, frontend build is unverified, private keys exist inside the workspace, and MVP extraction reports missing platform broker files. For data correctness and production packaging, these should be resolved before treating the generated client package as release-ready.
