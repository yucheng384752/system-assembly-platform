# Form System Kit Composer Architecture Diagrams

本文件提供兩種架構圖版本：

- 客戶版：用業務語言說明平台如何從網頁操作產生部署套件。
- 開發者版：用工程語言說明 GUI、Recipe、Assembly IR、generator、generated runtime package 之間的資料流與責任邊界。

## 客戶版：系統架構 Breakdown

```mermaid
flowchart TD
    User["客戶使用者"]
    GUI["網頁操作介面<br/>選流程、上傳表單樣本、設定保存需求"]
    Recipe["系統組裝清單<br/>記錄已選功能與設定"]
    Composer["系統組裝引擎<br/>整理功能、資料表、安裝需求"]
    Package["客戶部署 ZIP<br/>只包含已選功能"]
    Runtime["產生後的業務系統<br/>登入、上傳、匯入、查詢、追溯"]
    DB["正式資料保存<br/>PostgreSQL 或測試用 SQLite"]

    User --> GUI
    GUI --> Recipe
    Recipe --> Composer
    Composer --> Package
    Package --> Runtime
    Runtime --> DB
```

### 客戶版重點

- 客戶不用理解前端、後端、SQLAlchemy 或 package.json。
- 客戶在網頁上選擇需要的業務流程，平台產生只包含那些功能的 ZIP。
- 資料庫選擇用「資料保存需求」描述：是否多人使用、是否正式紀錄、是否需要追溯與報表。
- 正式環境建議使用 PostgreSQL；展示或測試可以使用 SQLite。

## 客戶版：各功能間如何溝通

```mermaid
flowchart LR
    Login["登入與權限"]
    Upload["檔案上傳"]
    Validate["資料驗證"]
    Import["匯入工作"]
    Records["正式資料"]
    Query["查詢與追溯"]
    Analytics["分析與報表"]
    Admin["管理設定"]

    Login --> Upload
    Upload --> Validate
    Validate --> Import
    Import --> Records
    Records --> Query
    Query --> Analytics
    Admin --> Validate
    Admin --> Query
```

### 客戶版溝通說明

- 登入與權限決定使用者可以操作哪些功能。
- 上傳功能接收 CSV、Excel 或 PDF 轉換結果。
- 驗證功能檢查欄位、格式、必填值與業務規則。
- 匯入工作把通過驗證的資料寫入正式資料區。
- 查詢與追溯從正式資料中查批號、產品、站點或關聯流程。
- 分析與報表使用查詢結果產生圖表或摘要。
- 管理設定可調整站點、欄位關係、驗證規則與分析 mapping。

## 客戶版：網頁操作 Input & Output

```mermaid
flowchart TD
    Input1["選擇業務流程<br/>例如上傳匯入、追溯、分析"]
    Input2["上傳 CSV/TSV 樣本<br/>用來判斷表格欄位與關係"]
    Input3["回答資料保存問題<br/>使用人數、正式紀錄、追溯需求"]
    Input4["選擇子功能<br/>PDF 轉 CSV、錯誤摘要、批次匯入"]

    GUI["Composer 網頁"]

    Output1["Recipe JSON<br/>功能與設定清單"]
    Output2["架構預覽<br/>已選功能、依賴、資料表關係"]
    Output3["部署 ZIP<br/>客戶可交給 IT 安裝"]
    Output4["安裝說明<br/>檢查環境、設定資料庫、啟動系統"]

    Input1 --> GUI
    Input2 --> GUI
    Input3 --> GUI
    Input4 --> GUI

    GUI --> Output1
    GUI --> Output2
    GUI --> Output3
    GUI --> Output4
```

## 開發者版：Assembly Engine Breakdown

```mermaid
flowchart TD
    Manifest["Kit Manifest<br/>kits/form-analysis.kit-manifest.json"]
    Recipe["Recipe<br/>assembly/*.recipe.json"]
    Resolver["Recipe Resolver<br/>resolve-recipe.ps1"]
    ResolvedPlan["Resolved Plan<br/>assembly/*-resolved-plan.json"]
    AssemblyIR["Assembly IR<br/>assembly/assembly-ir.json"]

    BackendRegistry["Backend Registry Generator<br/>FastAPI router registration"]
    FrontendRegistry["Frontend Registry Generator<br/>tab/navigation contract"]
    DBPlan["DB Plan Generator<br/>models, schema contracts, seed data"]
    DependencyPlan["Dependency Generator<br/>requirements.txt, package.json"]
    EntitlementPlan["Entitlement Generator<br/>feature gates"]
    SystemAssembler["System Assembler<br/>dist/generated-system"]
    ClientPackage["Client Deploy Packager<br/>dist/client-deploy-*.zip"]

    Manifest --> Resolver
    Recipe --> Resolver
    Resolver --> ResolvedPlan
    ResolvedPlan --> AssemblyIR
    Manifest --> AssemblyIR

    AssemblyIR --> BackendRegistry
    AssemblyIR --> FrontendRegistry
    AssemblyIR --> DBPlan
    AssemblyIR --> DependencyPlan
    AssemblyIR --> EntitlementPlan

    BackendRegistry --> SystemAssembler
    FrontendRegistry --> SystemAssembler
    DBPlan --> SystemAssembler
    DependencyPlan --> SystemAssembler
    EntitlementPlan --> SystemAssembler
    SystemAssembler --> ClientPackage
```

### 開發者版責任邊界

- Manifest 是 kit source of truth。
- Recipe 是使用者選擇結果。
- Resolved Plan 解決 kit dependency order。
- Assembly IR 是所有 generator 的共同中介 contract。
- Registry generators 不應自行重新推論 recipe。
- DB generator 負責 schema mode、seed data、relationship metadata。
- Package generator 只包 selected kits 與共用 runtime scripts。

## 開發者版：Function Communication

```mermaid
sequenceDiagram
    participant GUI as GUI Composer
    participant Recipe as Recipe JSON
    participant Resolver as Resolver
    participant IR as Assembly IR
    participant Gen as Artifact Generators
    participant Dist as Generated System
    participant Zip as Client Deploy ZIP

    GUI->>Recipe: export selected kits, subfeatures, table schemas, database intent
    Recipe->>Resolver: validate and resolve dependencies
    Resolver->>IR: emit selected runtime, database, frontend, backend contracts
    IR->>Gen: provide single source for registries, DB plan, dependency plan, entitlements
    Gen->>Dist: write backend, frontend, scripts, manifests, env template
    Dist->>Zip: package selected output for customer deployment
```

## 開發者版：Generated Runtime Package

```mermaid
flowchart TD
    Zip["client-deploy ZIP"]
    Check["check-prerequisites"]
    Env["configure-env"]
    Install["install dependencies"]
    Migrate["migrate / generated_db_bootstrap"]
    Smoke["smoke-start"]
    Start["start backend/frontend"]

    Backend["FastAPI Backend"]
    Frontend["Frontend App"]
    Database["Database"]
    External["External Services<br/>PDF conversion, MOD, etc."]

    Zip --> Check
    Check --> Env
    Env --> Install
    Install --> Migrate
    Migrate --> Smoke
    Smoke --> Start
    Start --> Backend
    Start --> Frontend
    Backend --> Database
    Backend --> External
```

### Runtime Input & Output

| 操作階段 | Input | Output |
| --- | --- | --- |
| GUI 選配 | 業務流程、子功能、資料保存需求、CSV/TSV 樣本 | Recipe JSON、預覽、組裝指令 |
| Assembly | Recipe、Kit Manifest、Schema Baseline、Dependency Baseline | Assembly IR、registry、DB plan、dependency plan |
| Package | Generated system folder | Client deploy ZIP |
| Install | ZIP、`.env`、資料庫連線資訊 | 已安裝 backend/frontend dependencies |
| Migrate | DB plan、SQLAlchemy models、Alembic 或 bootstrap | 可用資料庫 schema 與 seed data |
| Runtime | 使用者登入、檔案上傳、查詢條件、管理設定 | 匯入工作、正式資料、追溯結果、報表 |

## 開發者版：資料保存與 Schema 策略

```mermaid
flowchart LR
    SchemaPack["Domain Schema Pack<br/>表單欄位、樣本、關係"]
    Compiler["Schema Compiler"]
    Physical["Physical Tables<br/>穩定、少量、常查詢資料"]
    Generic["Generic Records<br/>未知或高變動表單"]
    RelMeta["Relationship Metadata<br/>UI 可設定關聯"]
    Bootstrap["DB Bootstrap / Migration"]

    SchemaPack --> Compiler
    Compiler --> Physical
    Compiler --> Generic
    Compiler --> RelMeta
    Physical --> Bootstrap
    Generic --> Bootstrap
    RelMeta --> Bootstrap
```

### Schema 策略說明

- 預設採 hybrid physical-first。
- 穩定且少量的客戶表單可以產生獨立 physical table。
- 不穩定或欄位常變動的資料保留在 generic records。
- 表單間關聯用 metadata 管理，先支援 UI 設定與 traceability query，再視需求升級成硬 FK。
