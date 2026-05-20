# Form System Kit Composer 產品需求文件

版本：0.1.0

## 產品定位

Form System Kit Composer 是一套正式環境使用的系統選配與重組工作台。
它的目標不是讓使用者從空白畫布開始做 app，而是將一套已完成系統拆解成
可選配的業務 kit，再透過 GUI 重新組合成可部署系統。

核心價值：

- 將既有完整系統反向拆成可理解、可重組、可維護的業務模組。
- 讓不懂前後端、API、資料庫與部署的使用者用業務語言選配系統。
- 讓每個 kit 都對應前端、後端、API、資料庫、權限、預覽資料與部署設定。
- 讓技術團隊能用 recipe 產生一致的系統組合結果。

## 目標使用者

### 主要使用者

- 傳產企業老闆、營運主管、廠務主管、品保主管。
- 了解業務流程，但不了解系統設計、前後端與資料庫選型。

### 次要使用者

- 系統整合商。
- 內部 IT。
- 軟體開發團隊。
- 需要將既有系統產品化或模組化的技術負責人。

## 第一版目標

第一版以 target system：`Form-analysis-server-specify-kit` 為拆解對象。

第一版需完成：

- 競品定位分析。
- target system kit manifest。
- 原系統 recomposition recipe。
- 可操作 GUI 工作台。
- recipe resolver。
- 第一條 MVP 拆解流程定義。

第一版不做：

- 不直接搬移 target system 原始碼。
- 不產生可部署的新完整系統。
- 不支援任意第三方系統自動拆解。
- 不開放使用者手動設計資料表。
- 不做展示型 landing page。

## 主要流程

### 1. 選配業務功能

使用者在 GUI 中看到的是業務能力，例如：

- 租戶與登入權限
- 檔案上傳與驗證
- 資料匯入流程
- 查詢與追溯
- 分析與報表
- 站點與規則管理

系統需自動處理：

- 必要 kit。
- 相依 kit。
- feature flag。
- 資料庫推薦。
- 預覽模式。
- recipe 輸出。

### 2. 資料庫推薦

GUI 不直接要求使用者選 SQLite、PostgreSQL 或 MySQL。

GUI 需以業務問題推導建議：

- 使用規模。
- 資料重要性。
- 查詢與分析需求。
- 部署方式。
- 是否需要租戶隔離。
- 是否需要背景匯入工作。

第一版推薦規則：

- SQLite：本機 Demo、單人使用、非正式資料。
- PostgreSQL：多人、正式資料、租戶隔離、匯入流程、追溯查詢、分析報表。
- MySQL：保留為未來 adapter，不作為目前 target system 的主推選項。

### 3. 即時預覽

第一版預覽分三類：

- UI 預覽：顯示所選 kit 對應的頁面或操作區塊。
- 流程預覽：顯示上傳、驗證、匯入、查詢、分析等流程。
- 資料模型預覽：用資料關係卡片說明 Tenant、P1、P2、P3、GenericRecord 等資料。

預覽需服務於正式決策，不使用行銷式展示頁。

### 4. Recipe 輸出

Recipe 是後續 assembly engine 的輸入。

Recipe 必須包含：

- enabled kits。
- dependency-resolved kit order。
- database recommendation。
- feature flags。
- frontend navigation。
- preview modes。

後續版本需加入：

- backend router registration。
- frontend route registration。
- database migration list。
- environment variables。
- external service requirements。

## MVP 拆解範圍

第一條實際抽碼流程建議：

```text
tenant-auth-kit
upload-validation-kit
import-pipeline-kit
station-data-link-kit
```

形成閉環：

```text
登入/租戶 -> 上傳檔案 -> 驗證 -> 匯入 -> 寫入正式資料表
```

## 驗收標準

### 文件

- 必要文件使用繁體中文。
- 文件需能讓非技術決策者理解價值與流程。
- 技術文件需明確列出 source ownership、相依關係與後續拆解動作。

### GUI

- GUI 可直接操作。
- GUI 設計維持正式環境工具風格。
- GUI 不改成 landing page。
- GUI 不要求使用者理解底層技術才可操作。
- GUI 可產生 recipe JSON。

### Resolver

- 可讀取 manifest 與 recipe。
- 可解析 kit 相依順序。
- 可輸出 APIs、models、feature flags。
- 可列出 frontend/backend source ownership。
- 可輸出 resolved plan。
