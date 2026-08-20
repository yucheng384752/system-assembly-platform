# Form System Kit Composer

Form System Kit Composer 會把一個既有的正式表單分析系統，拆解成可獨立勾選的業務能力
「Kit」，再依使用者勾選的組合，重新組裝成一套可直接部署的產生式系統（generated
system）。

目前分析的來源系統位於：

```text
C:\Users\gslab\Desktop\Form-analysis-server-specify-kit
```

本地 composer 工作目錄為：

```text
C:\Users\gslab\Documents\New project\form-system-kit-composer
```

## 這個專案在做什麼

Composer 把一套成熟的應用程式拆成 manifest 驅動的 Kit。每個 Kit 描述交付一項業務能力
所需的前端頁面、後端 router、資料庫物件、權限、設定、依賴關係、預覽資料，以及選用的
權益（entitlement）閘門。

使用者在 GUI 上勾選要啟用的能力、填入部署設定與授權資訊，就能下載 recipe JSON 與一份
可直接部署的套件。套件內含完整前後端原始碼、資料庫初始化計畫、systemd 服務範本、初始
部署環境檔，以及一份 RSA 簽章的授權憑證。每一次下載動作都會寫入
`data/operations.jsonl`，供稽核與災難復原（DR）備援使用。

產生套件後，操作者的標準流程為：

```powershell
.\scripts\check-prerequisites.ps1
.\scripts\check-db.ps1
.\scripts\install.ps1
.\scripts\migrate.ps1
.\scripts\start.ps1 -Background
.\scripts\status.ps1
```

## 目前狀態

目前已有一套可運作的「產生式套件產生器」：可以抽取 MVP 匯入流程原始碼、解析 Kit
依賴關係、組裝勾選的前後端檔案、建立依賴與資料庫計畫，並在 `dist` 下打包出一套產生式
系統。

目前主要產出物：

- `generated/mvp-import-flow`：從來源系統抽取出的 MVP 原始碼切片。
- `dist/generated-system`：組裝完成、可運作的系統封裝。
- `dist/form-system-generated-package`：完整專案資料夾封裝（含 tools/kits/schemas）。
- `dist/client-deploy-gui-selected-form-system`：依 GUI 勾選組合出的客戶交付套件。
- `dist/generated-system.zip`、`dist/client-deploy-gui-selected-form-system.zip`：對應的
  壓縮封存檔（有建立時才存在）。

產生出的系統包含前後端原始碼、依賴清單、資料庫初始化計畫、環境變數範本、README，以及
用於環境檢查、安裝、migration、smoke 測試、程序監控與啟動的 PowerShell 腳本。

## 目錄結構與內容說明

```text
form-system-kit-composer/
├── assembly/         recipe、resolved plan 與資料庫組裝計畫（Assembly IR 的輸入/輸出）
├── data/             GUI server 執行期寫入的資料（操作紀錄、機器指紋登錄）
├── dist/             組裝與打包後的產生式系統輸出（不手動修改，見下方說明）
├── docs/             產品、架構、Kit 開發與知識圖譜等長篇文件
├── generated/         從來源系統抽取出的原始碼切片
├── gui/               Kit 勾選、recipe 匯出與操作紀錄用的靜態 GUI
├── kits/              Kit manifest 與各 Kit 原始碼（唯一的 Kit 定義來源）
├── schemas/           Kit manifest、recipe、Assembly IR 的 JSON Schema
├── templates/          組裝與打包用的樣板檔案
├── tools/              PowerShell／Node／Python 自動化工具（驗證、產生、測試、部署、簽章）
├── .codex-claude-mailbox/   Claude 與 Codex 協作用的 mailbox thread（已 gitignore，不進版控）
├── README.md          本檔案
├── HANDOFF.md          目前專案狀態與實作細節交接文件
├── TODO.md             已完成／待辦實作紀錄
├── AI_COWORK_DOC.md    AI 協作用的專案修改與上下文同步文件（已知問題、修改前後差異）
└── 通用化分析.md        Kit 通用化缺口分析與雙信任邊界補強紀錄
```

### `assembly/`

Recipe 解析與組裝流程的中繼與輸出檔案：

- `form-analysis-original.recipe.json`：完整來源系統的 recipe。
- `mvp-import-flow.recipe.json`：MVP 匯入流程的 recipe。
- `gui-all-kits-no-mod.recipe.json`：GUI 全選（不含 MOD）情境的 recipe。
- `resolved-plan.json` / `mvp-resolved-plan.json`：`resolve-recipe.ps1` 解析出的完整／MVP
  組裝計畫。
- `assembly-ir.json`：`generate-assembly-ir.ps1` 產生的中央 Assembly IR（見下方
  「Assembly Engine 通用化」）。
- `baselines/`：預設依賴清單、預設 DB schema、Daihui 表單 schema 等基準檔。
- `backend-registry/`、`backend-registry-mvp/`：產生出的後端 router 註冊清單（JSON +
  Python）。
- `frontend-registry/`：產生出的前端頁籤註冊清單（JSON + TypeScript）。
- `db-plan/`：資料庫組裝計畫與 Daihui schema 推論結果。
- `entitlement-plan/`：依勾選 subfeature 產生的付費／權益檢查計畫。
- `license.lic`：本機測試用授權憑證。

### `data/`

GUI server 執行期寫入的資料，非原始碼：

- `operations.jsonl`：每一次下載動作的操作紀錄（稽核與 DR 備援用）。
- `machines.json`：機器指紋登錄（License 綁定機器用）。

### `dist/`

組裝與打包工具的輸出目錄，**不要手動修改**——所有內容都應該透過
`tools/assemble-system.ps1`、`tools/package-client-deploy.ps1` 等腳本重新產生。內含
`generated-system`（組裝結果）、`form-system-generated-package`（完整專案封裝）、
`client-deploy-gui-selected-form-system`（客戶交付套件）與對應的簽章、壓縮檔。

### `docs/`

長篇架構與流程文件：

| 檔案 | 內容 |
|------|------|
| `architecture-diagrams.md` | 給客戶與開發交接用的架構圖（系統拆解、函式通訊、輸入輸出） |
| `competitor-analysis.md` | 競品分析 |
| `decomposition-process.md` | 來源系統拆解流程 |
| `development-standards.md` | 開發與文件標準 |
| `gui-production-spec.md` | GUI 正式環境規格 |
| `kit-development-standard.md` | 新增 Kit 的開發規範（見下方「Kit 開發規則」） |
| `kit-expansion-strategy.md` | Kit 擴充策略 |
| `knowledge-graph.md` | 專案知識圖譜 |
| `product-requirements.zh-TW.md` | 產品需求文件 |
| `recomposition-architecture.md` | 重組裝架構說明 |
| `system-decomposition.md` | 目標系統拆解分析 |

### `generated/`

`tools/extract-mvp-flow.ps1` 從來源系統抽取出的原始碼切片，目前為
`mvp-import-flow/`（內含 `extraction-report.json` 與抽取出的
`form-analysis-server`）。這是組裝流程的輸入之一，不是最終產出物。

### `gui/`

本地靜態 GUI 進入點：

- `index.html`：GUI 頁面本體。
- `app.js`：Kit 勾選、recipe 組裝、下載與操作紀錄邏輯。
- `styles.css`：樣式。
- `jszip.min.js`：前端打包用的第三方函式庫。

### `kits/`

Kit 定義的唯一真實來源（single source of truth）：

- `form-analysis.kit-manifest.json`：中央 Kit manifest，列出所有 Kit 的 id、
  displayName、category、依賴關係、subfeatures 與 contributions。
- 每個 Kit 一個資料夾，固定結構為：

  ```text
  kits/<kit-id>/
    manifest.json        installOrder、requires、runtimeEnv、scripts
    kit.contract.json     provides / consumes（API、DB capability）
    install.ps1           Windows 安裝腳本（有宣告才需要）
    install.sh             Linux 安裝腳本（有宣告才需要）
    src/                   manifest／contributions 宣告的前後端原始碼
  ```

目前已定義的 12 個 Kit：

| Kit id | 顯示名稱 | 業務能力 |
|--------|----------|----------|
| `platform-core-kit` | 平台核心 | 提供應用程式啟動、設定、資料庫連線、健康檢查、共用樣式、語系與 API 呼叫基礎 |
| `tenant-auth-kit` | 租戶與登入權限 | 讓不同公司或部門隔離資料，並管理登入、API key、使用者角色與管理員權限 |
| `station-data-link-kit` | 站點資料串聯 | 保存並標準化任意站點製程資料，依可配置的業務鍵與 dataflow 串成可追溯資料鏈 |
| `upload-validation-kit` | 檔案上傳與驗證 | 使用者上傳 CSV、Excel 或 PDF，系統建立上傳工作、驗證內容、顯示錯誤並允許修正 |
| `import-pipeline-kit` | 資料匯入流程 | 將已驗證檔案轉成匯入工作，暫存、驗證、提交到正式 P1/P2/P3 資料表 |
| `query-traceability-kit` | 查詢與追溯 | 依 lot、日期、機台、模具、winder、product_id 查詢資料並顯示跨站點追溯鏈 |
| `analytics-kit` | 分析與報表 | 提供分析儀表板、artifact 瀏覽、即時分析、客訴分析與 extraction analysis |
| `station-admin-kit` | 站點與規則管理 | 管理泛用站點、欄位 schema、驗證規則、分析欄位對應與站點連結 |
| `audit-edit-kit` | 稽核與資料修正 | 允許資料修正時保留原因、前後差異與操作稽核紀錄 |
| `logs-ops-kit` | 日誌與維運 | 查看、搜尋、統計、清理與下載系統日誌 |
| `mod-subscription-kit` | MOD 訂閱串接 | 串接 MOD 訂閱來源，接收訂閱狀態、方案、到期日與權益，供系統依訂閱方案啟用對應功能 |
| `generic-forms-kit` | 通用表格 | 提供 schema 驅動的通用表單類型與 JSONB 紀錄儲存，部署後管理者可自訂表單欄位、上傳資料，無需修改程式碼 |

### `schemas/`

JSON Schema，定義三份核心資料結構的合法形狀：

- `kit.schema.json`：中央 Kit manifest 與 subfeature contributions 的 schema。
- `recipe.schema.json`：recipe JSON 的 schema。
- `assembly-ir.schema.json`：Assembly IR 的 schema。

### `templates/`

組裝與打包流程使用的樣板檔案，例如 `frontend/`（前端專案樣板，含
`package-lock.json`）。

### `tools/`

自動化工具集中地，依用途大致分類（實際腳本數量會持續增加，以資料夾內容為準）：

- **驗證類**：`validate-json.ps1`、`validate-recipe.ps1`、`validate-kit-contracts.ps1`、
  `validate-external-kit.ps1`（外部 Kit 接入驗證，靜態 admission 檢查）、
  `validate-generated-system.ps1`、`validate-package-folder.ps1`。
- **解析與產生類**：`resolve-recipe.ps1`、`extract-mvp-flow.ps1`、
  `generate-assembly-ir.ps1`、`generate-backend-registry.ps1`、
  `generate-frontend-registry.ps1`、`generate-db-plan.ps1`、`generate-db-bootstrap.ps1`、
  `generate-dependency-files.ps1`、`generate-entitlement-plan.ps1`、
  `generate-form-schema.ps1`、`generate-model-init.ps1`、`assemble-system.ps1`。
- **打包與部署類**：`package-system.ps1`、`package-client-deploy.ps1`、
  `package-offline-deploy.ps1`、`bundle-offline.ps1` / `bundle-offline.sh`、
  `prepare-offline.ps1`、`download-docker-offline.sh`、`build-wizard-exe.ps1`、
  `install-wizard.py` / `install-wizard.exe`。
- **授權簽章類**：`generate-license-keys.ps1`、`sign-package.ps1`、
  `generate-issuer-key.cjs`、`keys/`（RSA 金鑰對，私鑰已 gitignore）。
- **GUI 相關**：`serve-gui.cjs`、`serve-gui-launcher.cjs`、`export-all-kits-from-gui.mjs`。
- **測試類**（`test-*.ps1` / `test-*.mjs` / `test_*.py`）：涵蓋 resolver、資料庫
  bootstrap、依賴檔案、GUI 靜態頁面／瀏覽器行為、程序監控、外部 Kit admission、
  station-data-link 通用化、Daihui schema 與上傳流程、License 簽章往返、TPM 執行期
  驗證、PostgreSQL provisioning 等情境；`test-all.ps1` 是總入口。
- **VM／TPM 診斷類**：`01_tpm_setup_windows.ps1`、`diagnose-tpm-license.py`、
  `vm_*.py`（VM 上的 API、資料庫、dataflow、查詢與部署診斷腳本）、
  `test-tpm-linux.sh`、`test-swtpm-auto.sh` 等。
- `backup-composer-data.ps1`：操作紀錄與 recipe 的 DR 備援腳本。
- `keys/`：License 簽章用 RSA 金鑰對（私鑰 `signing-private-key.pem` 已 gitignore）。

### `.codex-claude-mailbox/`

Claude 與 Codex 協作用的非同步溝通機制，已在 `.gitignore` 中排除、不進版控：

- `threads/`：一個工作項目一個 thread 檔案，記錄需求、規劃、review、實作紀錄與驗證結果。
- `inbox/` / `outbox/` / `archive/`：thread 的收件、送出與歸檔狀態。
- `index.md`：thread 索引。

## 前置需求

工具鏈設計目標是 Windows PowerShell。

建議的本機工具：

- PowerShell 5 以上。
- Node.js（靜態 GUI 服務與瀏覽器導向的 smoke 檢查）。
- Python（產生式後端的 smoke 驗證）。
- Git（版本控制與發布）。

部分產生式應用程式的執行模式需要額外的前後端依賴與已設定好的資料庫，但預設的 smoke
驗證會避免要求完整安裝正式環境依賴。

## 啟動 GUI

GUI 以 Node.js server 執行，並提供持久化的 API 端點：

```powershell
node tools\serve-gui.cjs
```

接著開啟：

```text
http://127.0.0.1:4173/
```

除了靜態檔案服務外，server 額外提供兩個 API 端點：

| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/log` | POST | 將一筆操作紀錄附加到 `data/operations.jsonl` |
| `/api/logs` | GET | 以 JSON 陣列回傳所有操作紀錄 |

GUI 支援：

- 引導式架構問答。
- Kit 目錄勾選與 subfeature 細部調整。
- MOD 訂閱與付費功能閘門中繼資料。
- 圖表摘要選項。
- 資料庫建議與標準化說明。
- 產生式系統與依賴清單狀態。
- **Step 4 — 部署設定**：授權資訊（被授權方名稱、email、有效天數）、部署初始設定
  （資料庫連線、初始管理者帳號）。
- Recipe JSON 匯出（Step 4 的 `licensee` 與 `deploymentConfig` 會寫入，密碼除外）。
- Deploy-init.env 下載（僅含帳密，瀏覽器端產生，不寫入 recipe）。
- 組裝指令輸出。
- **05 操作記錄** 頁面：在 GUI 內檢視與匯出 `data/operations.jsonl`。

## 核心工作流程

驗證來源 JSON：

```powershell
.\tools\validate-json.ps1 .\kits\form-analysis.kit-manifest.json
.\tools\validate-json.ps1 .\assembly\mvp-import-flow.recipe.json
```

依 schema 與 Kit 定義驗證 recipe：

```powershell
.\tools\validate-recipe.ps1 -RecipePath .\assembly\mvp-import-flow.recipe.json
```

將 recipe 解析成有序的組裝計畫：

```powershell
.\tools\resolve-recipe.ps1 `
  -RecipePath .\assembly\mvp-import-flow.recipe.json `
  -OutputPath .\assembly\mvp-resolved-plan.json
```

抽取 MVP 來源切片：

```powershell
.\tools\extract-mvp-flow.ps1
```

組裝產生式系統：

```powershell
.\tools\assemble-system.ps1 `
  -RecipePath .\assembly\mvp-import-flow.recipe.json `
  -OutputPath .\dist\generated-system
```

驗證產生式系統：

```powershell
.\tools\validate-generated-system.ps1 -GeneratedRoot .\dist\generated-system
```

打包產出（同時簽署授權並內嵌 `license.lic`）：

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

僅產生授權憑證（讀取 `assembly/` 內最新的 recipe）：

```powershell
.\tools\sign-package.ps1
# 或指定明確路徑：
.\tools\sign-package.ps1 -RecipePath .\assembly\my.recipe.json -PackageZipPath .\dist\my.zip
```

將操作紀錄與 recipe 備份到帶時間戳記的目錄（DR）：

```powershell
.\tools\backup-composer-data.ps1
# 或備份到網路共享路徑：
.\tools\backup-composer-data.ps1 -BackupRoot \\server\share\composer-backup
```

## 產生套件內容

組裝出的套件設計為解壓後即可直接運作。重要的執行期檔案包含：

- `recipe.json` — 已勾選的 Kit 設定（不含密碼）。
- `deploy.sh` — Linux 部署腳本（會自動偵測 `deploy-init.env`）。
- `deploy-init.env` — *（由操作者提供）* 初始資料庫帳密與管理者帳號；不會隨套件 zip
  一併交付，需另外透過 GUI 下載。
- `license.lic` — RSA-PSS 簽章的授權憑證（JSON + base64 簽章）。
- `form-system.service` — systemd unit 範本（`__SYS_ROOT__` 為安裝路徑佔位符）。
- `.gitignore` — 保護 `system/.env` 與 `deploy-init.env` 不被誤 commit。
- `dependency-manifest.json`
- `db-bootstrap-plan.json`
- `backend\requirements.txt`
- `backend\app\core\license.py` — 啟動時的授權驗證（不阻擋啟動）。
- `scripts\check-prerequisites.ps1`
- `scripts\install.ps1`
- `scripts\migrate.ps1`
- `scripts\start.ps1`
- `scripts\status.ps1`
- `scripts\stop.ps1`

資料庫初始化是依組裝資料庫計畫產生。若產生式後端有安裝 Alembic，migration 會使用
Alembic；否則會使用產生出的 SQLAlchemy bootstrap 腳本建立勾選的資料表。

在有 systemd 的 Linux 部署環境上，`deploy.sh` 部署成功後會印出三步驟 systemd 安裝
指引：

```bash
sudo sed -i 's|__SYS_ROOT__|/opt/form-system|g' form-system.service
sudo cp form-system.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now form-system
```

程序監控會在 `runtime` 下寫入 pid 檔、在 `logs` 下寫入日誌檔。

## License 簽章

Composer 透過 Node.js `crypto` 使用 RSA-2048 非對稱簽章。私鑰不會離開 composer 機器，
只有公鑰會內嵌進產生式系統。

**首次設定**（只需執行一次；金鑰已存在時會跳過）：

```powershell
.\tools\generate-license-keys.ps1
```

輸出：
- `tools\keys\signing-private-key.pem` — 已 gitignore，請妥善保管。
- `tools\keys\signing-public-key.pem` — 內嵌進 `license.py`。

**簽署套件**（`package-client-deploy.ps1` 也會自動呼叫）：

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

輸出寫到與 recipe 相同的目錄下：
- `license.lic` — JSON payload + RSA-PSS/SHA-256 base64 簽章。
- `<name>.sig.json` — zip 檔的 SHA-256 雜湊 + 簽章（有指定 `-PackageZipPath` 時才產生）。

**執行期驗證**：產生式系統的 `backend/app/core/license.py` 會在啟動時驗證憑證。驗證失敗
只會記錄警告，不會阻擋應用程式啟動。

## 操作紀錄與 DR 備援

GUI 內每一次下載動作（recipe JSON、部署套件、deploy-init.env）都會由 server 透過
`POST /api/log` 記錄到 `data/operations.jsonl`。

每一行是一筆 JSON 物件：

```json
{ "ts": "2026-06-01T10:00:00Z", "ip": "127.0.0.1", "action": "download-package", "recipeName": "form-system-import", "kits": ["platform-core-kit", "upload-validation-kit"], "licensee": "" }
```

可在 GUI 的 **05 操作記錄** 頁面內檢視與匯出紀錄。

備份紀錄與所有 recipe 檔案到帶時間戳記的目錄：

```powershell
.\tools\backup-composer-data.ps1
# 異地／網路共享路徑：
.\tools\backup-composer-data.ps1 -BackupRoot \\server\share\composer-backup
```

## 驗證

執行完整的本機驗證套件：

```powershell
.\tools\test-all.ps1
```

單項檢查：

```powershell
.\tools\test-gui-static.ps1
.\tools\test-gui-recipe-export.ps1
.\tools\test-upload-page-refactor.ps1
.\tools\test-resolver.ps1
.\tools\test-dependency-files.ps1
.\tools\test-db-bootstrap.ps1
.\tools\test-generated-start.ps1
.\tools\test-process-supervision.ps1
.\tools\test-external-kit-validation.ps1
```

若機器上的 PowerShell 執行原則有限制，可用以下方式執行檢查：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\test-all.ps1
```

## UploadPage 重構狀態

MVP 前端上傳頁面重構（Phase 29）已完成。邏輯已逐步拆分為以下路徑下的專責模組：

```text
generated\mvp-import-flow\form-analysis-server\frontend\src\pages\upload
```

拆出的模組涵蓋：共用上傳型別、檔案解析、上傳資格判斷、API client 設定、工作流程狀態
轉換、批次驗證／轉換／匯入協調、PDF 轉換協調、CSV 編輯與儲存機制、驗證錯誤正規化、
toast 路由、批次匯入清理排程，以及所有子元件。

`tools\test-upload-page-refactor.ps1` 會重新套用重構，若主要邏輯又被搬回
`UploadPage.tsx` 就會失敗。

## Kit 開發規則

新增 Kit 應遵循 `docs/kit-development-standard.md`。

給客戶說明與開發交接用的架構圖收錄在 `docs/architecture-diagrams.md`，涵蓋系統拆解、
函式通訊與客戶端網頁輸入輸出。

簡短版：

- 先在 manifest 中定義業務能力。
- Kit 邊界依業務能力劃分，不依檔案資料夾劃分。
- 透過產生出的 registry 註冊前端頁籤與後端 router。
- 明確描述資料庫物件與依賴需求。
- 功能屬付費或需權益閘門時，補上 entitlement 中繼資料。
- 新 Kit 行為要有對應的驗證工具覆蓋。

外部（非本專案內建）Kit 若要接入正式 catalog／recipe／assembly／runtime，需先通過
`tools\validate-external-kit.ps1` 的靜態 admission 檢查（資料模型、設定驅動、組裝
流程、執行期、相容層、驗證六個面向），詳見該工具與對應的
`.codex-claude-mailbox` thread 記錄。

## MOD 訂閱說明

MOD 訂閱目前指的是內部的付費／客製功能閘門，預設不是對接外部平台的整合。

已閘門的功能範例：

- PDF 轉 CSV。
- 表單分析。
- 圖表摘要繪製。
- 自訂驗證規則。

除非明確確認過範圍，否則不要新增執行期中介層或第三方訂閱供應商整合。

## Assembly Engine 通用化

組裝引擎目前會從 resolved plan、Kit manifest、基準依賴與資料庫合約、entitlement
plan，以及 Daihui 表單 schema 基準，產生一份中央 Assembly IR，輸出到
`assembly\assembly-ir.json`。IR 會經 `tools\validate-json.ps1` 驗證 JSON 格式，並由
`tools\generate-assembly-ir.ps1` 產生。

各產生器腳本仍可讀取原本的輸入來源，但後端與前端 registry 產生器也可以帶入
`-IRPath assembly\assembly-ir.json` 改用共用合約。這樣可以維持目前的 patch 行為不變，
同時讓未來的產生器都有一份穩定的資料來源，涵蓋勾選的 Kit、feature flag、router
註冊、前端導覽、資料庫儲存決策、依賴基準、環境需求、腳本與 entitlement。

Daihui schema pack 採用混合式「physical-first」儲存策略：穩定的執行期與查詢介面
維持實體資料表，而 Daihui 樣本表單則使用泛用紀錄，把常用查詢欄位實體化抽出，同時完整
保留原始資料列於 JSON 欄位中。基準檔是作為輸入讀取，IR 產生器不會改寫它。

## 產生式執行期狀態拓樸

Assembly IR 包含 `runtimeStateTopology`，是一份產生出的執行期狀態擁有者與關聯關係圖。
節點涵蓋身份範疇、API key 行為者、環境設定、資料庫狀態、後端 router、必要的資料模型，
以及已選用的外部服務。邊描述租戶範疇、資料模型持久化，以及環境設定驅動的服務關聯。

這份拓樸圖是為了下游套件檢查與未來的 GUI 預覽而設計：讓執行期狀態在程式碼組裝之前就
可見，因此在檢視某個勾選的 Kit 時，可以直接看出它的租戶範疇、資料庫影響、外部設定與
服務擁有權，不需要另外檢查產生出的原始碼。

## 文件政策

Repository 內的文件應聚焦在工具、schema、測試、套件發佈與實作交接所需的內容。

長篇的說明筆記、架構圖、決策紀錄與流程知識放在 Obsidian 工作區：

```text
C:\Users\gslab\Desktop\Form System Kit Composer Obsidian
```

## Git 與 Commit 慣例

Repository 變更一律使用 Conventional Commits：

```text
feat: 新增功能
fix: 修正錯誤行為
docs: 更新專案文件
test: 新增或更新驗證
refactor: 不改變行為的重構
chore: 更新維護性檔案
```

純文件變更建議使用：

```text
docs: update project readme
```

## 建議後續工作

以下功能狀態記錄於 2026-06-01（歷史快照，非即時狀態；最新狀態請以 `HANDOFF.md` 與
`TODO.md` 為準）：

| 功能 | 說明 | 狀態 |
|------|------|------|
| B | Kit CSS 打包 | ✓ 完成 |
| C | deploy-init.env GUI 輸入 + deploy.sh 自動偵測 | ✓ 完成 |
| D1 | GUI Server 化（API log endpoints） | ✓ 完成 |
| D2 | 產生式系統 systemd service 範本 | ✓ 完成 |
| E1/E2 | GUI 操作記錄頁面 | ✓ 完成 |
| E3 | DR 備援腳本 | ✓ 完成 |
| A | License RSA 簽章 + 後端驗證 | ✓ 完成 |
| UploadPage | Phase 29 重構 | ✓ 完成 |

適合接續的工作方向：

1. 為 log server 的 `GET /api/logs` 加上 `?action=&from=&to=` 查詢過濾支援。
2. 擴充 Kit 涵蓋範圍：在目前 platform/upload/PDF/query 等 Kit 之外新增 Kit manifest。
3. 建立 `tools\rotate-license-keys.ps1`，用於重新產生金鑰對並將公鑰重新內嵌進
   `license.py`，以支援金鑰輪替。
4. 加入會在 push 時執行 `.\tools\test-all.ps1` 的 GitHub Actions 或 CI 流程。

完整的交接內容與實作歷史請閱讀 `HANDOFF.md` 與 `TODO.md`。
