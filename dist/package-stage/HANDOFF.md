# Form System Kit Composer 交接紀錄

本文件用於傳承到下一個聊天或下一位協作者。

## 專案位置

`C:\Users\gslab\Documents\New project\form-system-kit-composer`

Target system：

`C:\Users\gslab\Desktop\Form-analysis-server-specify-kit`

## 產品目標

建立一套正式環境使用的「系統選配與重組工作台」。

使用者不需要懂前端、後端、API、資料庫與部署，只需要用 GUI 選擇業務功能。每個功能 kit 對應：

- 前端元件與頁面
- 後端服務
- API
- 資料庫模型
- 權限
- 預覽資料
- 部署/外部服務設定

目標是從已完成的 target system 反向拆解成 kit，再用 recipe 重新組合。

## 核心設計決策

1. 原本的 `P1/P2/P3 生產資料` 已抽象化為：

   `station-data-link-kit` / `站點資料串聯`

   P1/P2/P3 是目前 target system 的相容層，不是產品概念的固定邊界。

2. `upload-validation-kit` 拆成 CSV/Excel 與 PDF 語意：

   - CSV / Excel 上傳驗證
   - CSV / Excel 錯誤摘要
   - CSV 內容修正
   - PDF 上傳選項
   - PDF 轉 CSV 綁定
   - 轉換結果匯入 upload job

   選 PDF 時後續需綁定轉換服務，例如 `PDF_SERVER_URL`。

3. GUI 是正式環境工作台，不是 landing page 或 demo page。

4. GUI 目前主要頁籤：

   - 選配
   - 資料庫推薦
   - 即時預覽
   - 系統生成

   `Recipe` 與 `競品定位` tab 已移除。

5. 相依關係不直接顯示 technical dependency graph。
   現在改為「系統自動包含」，用一般使用者可理解的句子說明。

6. 必選父 kit 的子功能已鎖定，避免父層必選但子層被拆空，符合階層不可踰越性。

7. 可選父 kit 可以：

   - 只選父功能
   - 全選子功能
   - 個別微調子功能

8. 資料庫推薦預設正式場景為 PostgreSQL，並已加入選配摘要。

## 已完成內容

### 文件

- `README.md`
- `TODO.md`
- `HANDOFF.md`
- `docs/product-requirements.zh-TW.md`
- `docs/gui-production-spec.md`
- `docs/development-standards.md`
- `docs/kit-expansion-strategy.md`
- `docs/decomposition-process.md`
- `docs/recomposition-architecture.md`
- `docs/system-decomposition.md`
- `docs/competitor-analysis.md`

### Kit 與 Recipe

- `kits/form-analysis.kit-manifest.json`
- `assembly/form-analysis-original.recipe.json`
- `assembly/mvp-import-flow.recipe.json`
- `assembly/resolved-plan.json`
- `assembly/mvp-resolved-plan.json`

### GUI

- `gui/index.html`
- `gui/app.js`
- `gui/styles.css`

目前 GUI 已支援：

- 父 kit 橫向列顯示
- 點擊父 kit 整列展開/收合子功能
- 子功能橫向列顯示
- 模糊搜尋
- 搜尋可用子功能名稱找到對應父 kit
- 必選 kit 子功能鎖定
- 可選 kit 子功能微調
- 選配摘要
- 人性化「系統自動包含」
- 資料庫推薦
- 即時 mock preview
- 系統生成頁
- GUI 端產生選配資料 zip

### 工具

- `tools/validate-json.ps1`
- `tools/resolve-recipe.ps1`
- `tools/extract-mvp-flow.ps1`
- `tools/package-system.ps1`

### 產出

- `generated/mvp-import-flow`
- `generated/mvp-import-flow/extraction-report.json`
- `dist/form-system-generated-package.zip`

目前 MVP 抽碼結果：

- copied sources: 50
- missing sources: 0

## 第一條 MVP 抽碼流程

目標流程：

```text
tenant-auth-kit -> upload-validation-kit -> import-pipeline-kit -> station-data-link-kit
```

業務閉環：

```text
登入/租戶 -> 上傳檔案 -> 驗證 -> 匯入 -> 寫入正式資料表
```

目前已能透過：

```powershell
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\extract-mvp-flow.ps1
```

將第一條 MVP source slice 抽出到：

`generated/mvp-import-flow`

## 系統打包

正式打包工具：

```powershell
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\package-system.ps1
```

輸出：

`dist/form-system-generated-package.zip`

注意：目前這是「打包選配資料與 MVP 抽碼結果」，還不是完整 deployable system generator。

## Clean Code 與文件規範

使用者提供的 clean code 準則位於：

`C:\Users\gslab\Desktop\clean_code 驗證.txt`

已整理到：

`docs/development-standards.md`

後續要求：

- 必要文件使用繁體中文。
- 程式碼需遵守 clean code 原則。
- 函數簡短、單一職責、命名清楚。
- 避免不必要註解。
- GUI 設計維持正式環境工具風格。

## 待辦重點

詳見：

`TODO.md`

本輪已完成：

- 子功能已正式寫入 `kits/form-analysis.kit-manifest.json` 的 `subfeatures` 欄位。
- `schemas/kit.schema.json` 已支援 `subfeatures`。
- 兩個既有 recipe 已加入 `selectedSubfeatures`。
- Resolver 已檢查子功能相依關係與 PDF 子功能的 `PDF_SERVER_URL` 綁定需求。
- GUI 已改為 manifest/subfeatures 驅動，搜尋支援 aliases，PDF 子功能會顯示外部服務需求。
- `tools/package-system.ps1` 已將 `schemas/kit.schema.json` 納入 zip。

重要待辦：

1. 建立 backend kit registry。
2. 建立 frontend tab registry。
3. 將 target system hard-coded router include 改成 kit registration。
4. 拆 `UploadPage`：

   - page shell
   - workflow state
   - API client
   - view components

5. 建立真正的 assembly engine，產生可部署系統。
6. 加 GUI smoke test。
7. 加 package-system zip 內容驗證。
8. 補正式 recipe schema，驗證 `selectedSubfeatures`。

## 驗證指令

常用驗證：

```powershell
node --check form-system-kit-composer\gui\app.js
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\validate-json.ps1
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\resolve-recipe.ps1
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\resolve-recipe.ps1 -RecipePath assembly\mvp-import-flow.recipe.json -OutputPath assembly\mvp-resolved-plan.json
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\extract-mvp-flow.ps1
powershell -ExecutionPolicy Bypass -File form-system-kit-composer\tools\package-system.ps1
```

最近一次驗證結果：

- GUI JS 語法檢查通過
- JSON 驗證通過
- full resolver 成功
- MVP resolver 成功
- MVP 抽碼成功
- package-system 成功產出 zip

## 下一步建議

下一步優先做：

1. 建立 `backend kit registry` 的第一版。
2. 建立 `frontend tab registry` 的第一版。
3. 將 MVP 產物從「抽碼資料夾」推進到「可註冊模組」。
4. 拆 `UploadPage`，讓 page shell、workflow state、API client、view components 可被 kit registration 接管。
5. 補 GUI smoke test，確認主要 tab、kit toggle、subfeature toggle、zip download 可操作。
