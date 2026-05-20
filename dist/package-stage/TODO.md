# TODO

## 已完成

- 已將子功能寫入 manifest 的 `subfeatures` 欄位。
- 已在 PDF 子功能選取時，於 GUI 顯示 `PDF_SERVER_URL` 外部服務需求。
- 已將 GUI 搜尋改為 manifest/subfeatures 驅動，並支援 aliases。
- 已在 `kit.schema.json` 加入 `subfeatures` schema。
- 已在現有 recipe 加入 `selectedSubfeatures` 欄位。
- Resolver 已檢查子功能相依關係。
- Resolver 已檢查 PDF 子功能是否已綁定轉換服務。
- `package-system.ps1` 已將 `schemas/kit.schema.json` 納入 zip。

## GUI

- 子功能選擇需支援「必選、可選、需授權、需外部服務」等狀態。
- PDF 子功能選取時，後續可補轉換服務健康檢查結果。
- 系統生成頁需顯示更多正式打包狀態，例如輸出檔名、版本、生成時間、檔案大小。
- GUI 目前可產生選配資料 zip；完整系統 zip 仍由 `tools/package-system.ps1` 產生。

## Kit 與 Recipe

- 後續可補正式 recipe schema，讓 `selectedSubfeatures` 也有 schema 驗證。
- 站點資料串聯需進一步定義泛用站點 schema 與 P1/P2/P3 adapter 邊界。

## Assembly Engine

- 建立 backend kit registry。
- 建立 frontend tab registry。
- 將 target system 的 hard-coded router include 改為 kit registration。
- 將 `UploadPage` 拆成 page shell、workflow state、API client、view components。
- 建立可部署系統產生器，而不只是抽碼與 zip 打包。

## 測試

- 為 `resolve-recipe.ps1` 補測試資料。
- 為 `extract-mvp-flow.ps1` 補 dry-run 模式。
- 為 `package-system.ps1` 補檔案存在與 zip 內容驗證。
- 加入 GUI smoke test，確認主要 tab、kit toggle、subfeature toggle、zip download 可操作。
- 加入搜尋測試，確認可用子功能名稱找到父 kit 並展開匹配子功能。

## 待定

- 是否支援 MySQL adapter。
- 是否支援真正的 React component-level preview。
- 是否需要範例網頁或競品截圖作為 GUI 參考。
- 是否將 GUI 改成 Vite/React 專案。
