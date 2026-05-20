# Kit 擴充策略

## 目標

Kit 不應只是一個大顆功能開關。正式環境中，每個 kit 需要能繼續細分子功能，
讓使用者可以從「業務能力」逐步展開到「流程、頁面、API、資料表、權限與預覽」。

## 建議結構

每個 kit 應調整成以下層級：

```text
Kit
  -> 子功能 groups
    -> 功能 capability
      -> frontend
      -> backend
      -> api
      -> database
      -> permissions
      -> preview
      -> config
```

範例：

```text
upload-validation-kit
  -> CSV / Excel 上傳
  -> PDF 轉換
  -> CSV 內容修正
  -> 驗證錯誤摘要
  -> 建立 import job
```

## Manifest 調整方向

後續 `kit-manifest.json` 可新增 `subfeatures` 欄位：

```json
{
  "id": "upload-validation-kit",
  "displayName": "檔案上傳與驗證",
  "subfeatures": [
    {
      "id": "csv-excel-upload",
      "displayName": "CSV / Excel 上傳",
      "businessCapability": "上傳表單檔案並建立 upload job",
      "defaultEnabled": true,
      "dependencies": [],
      "frontend": {
        "components": ["FileUpload.tsx"]
      },
      "backend": {
        "apis": ["POST /api/upload"]
      }
    }
  ]
}
```

## GUI 呈現方式

依你的想法，kit 在 GUI 中應改為橫向長條：

- 第一層：kit 名稱、分類、選取狀態、必要/可選標籤。
- 展開後：子功能、來源檔案、API、資料表、相依套件。
- 使用者先選 kit，再視需求展開細節。

這種方式比卡片更適合正式工作台：

- 可容納更多資訊。
- 可逐層揭露複雜度。
- 適合之後加入子功能開關。
- 適合比較多個 kit 的相依關係。

## 子功能拆分原則

子功能應符合以下規則：

- 使用者能理解它的業務意義。
- 可被獨立預覽。
- 可追蹤來源檔案。
- 可定義 API 與資料表歸屬。
- 若停用會有明確影響。

不建議把子功能切得太技術導向，例如：

- 不要切成 `useUpload hook`。
- 不要切成 `routes_upload helper function`。
- 不要切成 `SQLAlchemy model file`。

應切成：

- 上傳檔案。
- 驗證資料。
- 修正錯誤。
- 建立匯入工作。
- 查詢追溯鏈。
- 產生分析結果。

## 第一批建議子功能

### `tenant-auth-kit`

- 租戶列表與建立。
- 使用者登入。
- API key 發行。
- 使用者管理。
- 管理員解鎖。

### `upload-validation-kit`

- CSV / Excel 上傳。
- PDF 上傳。
- PDF 轉 CSV。
- 上傳狀態查詢。
- CSV 內容修正。
- 驗證錯誤摘要。

### `import-pipeline-kit`

- 建立 import job。
- 從 upload job 建立 import job。
- 暫存列驗證。
- 錯誤列查詢。
- commit 到正式資料表。
- 取消匯入。

### `station-data-link-kit`

- 站點資料模型。
- P1/P2/P3 既有站點相容層。
- 新站點資料定義。
- lot normalization。
- product_id 產生。
- generic record。

## 即時渲染策略

前端元件可以即時渲染，但需分成兩個階段：

1. **Mock preview**
   使用 kit manifest 中的 preview metadata 與 sample data，在 GUI 中立即渲染。

2. **Runtime preview**
   當 kit 真正抽成可註冊前端模組後，以 iframe、module federation 或本機 dev server
   載入真實元件。

第一版建議先做 mock preview，因為它不需要 target system 完全模組化即可驗證選配流程。
