# AI Agent 專案修改與上下文同步文件

> **系統提示 (System Note for AI):** 
> 讀取此文件時，請優先確認「已知問題與未修正 Bug」，避免在後續的程式碼生成中重複觸發相同的錯誤。基於「修改前後差異」與「測試結果」來理解目前的專案邏輯狀態。

## 1. 已知問題與未修正 Bug (Known Bugs)

* **[2026-05-21]** `app/config/constants.py`：`VALID_MATERIALS` 與 `VALID_SLITTING_MACHINES` 預設為空清單。
  * **觸發條件**：環境變數 `VALID_MATERIALS_CSV` / `VALID_SLITTING_MACHINES_CSV` 未設定時，getter 回傳 `[]`。
  * **目前影響**：材料與裁切機編號驗證邏輯跳過驗證（空清單 guard 已加入，不會全部報錯）。
  * **暫時解法/迴避方式 (Workaround)**：在 `.env` 加入 `VALID_MATERIALS_CSV=PE,PP,...` 啟用驗證；未設定則跳過，測試環境可接受。

* **[2026-05-21]** `app/models/core/audit_event.py`：`tenant_id` 欄位為 `nullable=True`。
  * **觸發條件**：`main.py` 在系統請求（無 tenant 上下文）時傳入 `None`。
  * **目前影響**：允許 `tenant_id` 為 Null 的稽核事件，與原始設計意圖略有偏差。
  * **暫時解法/迴避方式 (Workaround)**：保持 `nullable=True`；後續可在應用層強制過濾非 tenant 請求。

---

## 2. 修改範圍與摘要 (Modified Scope)

* **變更時間**：2026-05-21
* **涉及檔案**：
  * `dist/generated-system/backend/app/schemas/__init__.py`（新建）
  * `dist/generated-system/backend/app/schemas/upload.py`（新建）
  * `dist/generated-system/backend/app/schemas/validate.py`（新建）
  * `dist/generated-system/backend/app/schemas/import_data.py`（新建）
  * `dist/generated-system/backend/app/schemas/audit.py`（新建）
  * `dist/generated-system/backend/app/schemas/import_job.py`（新建）
  * `dist/generated-system/backend/app/schemas/pdf_conversion.py`（新建）
  * `dist/generated-system/backend/app/models/audit.py`（新建）
  * `dist/generated-system/backend/app/models/record.py`（新建）
  * `dist/generated-system/backend/app/models/p2_item.py`（新建）
  * `dist/generated-system/backend/app/models/p3_item.py`（新建）
  * `dist/generated-system/backend/app/models/__init__.py`（更新）
  * `dist/generated-system/backend/app/models/core/audit_event.py`（更新）
  * `dist/generated-system/backend/app/config/__init__.py`（新建）
  * `dist/generated-system/backend/app/config/constants.py`（更新：env var 動態載入 + 空清單 guard）
  * `dist/generated-system/backend/app/services/validation.py`（更新：空清單 guard）
  * `dist/generated-system/backend/app/services/csv_field_mapper.py`（更新：移除 StrEnum shim）
  * `dist/generated-system/backend/app/models/import_job.py`（更新：移除 StrEnum shim）
  * `dist/generated-system/backend/app/models/pdf_conversion_job.py`（更新：移除 StrEnum shim）
  * `dist/generated-system/backend/app/models/upload_job.py`（更新：移除 StrEnum shim）
  * `tools/_upload_vm.py`（新建）
  * `tools/_vm_deploy.py`（新建）
  * `tools/_vm_check_log.py`（新建）
  * `tools/_vm_patch.py`（新建）
  * `tools/_vm_setup_db.py`（新建）
  * `tools/_vm_start2.py`（新建）
  * `tools/_vm_migrate.py`（新建）
  * `tools/_vm_e2e_test.py`（新建）
  * `tools/_vm_full_test.py`（新建）
* **修改核心目的**：補齊所有缺失的 `app.schemas.*` 與 `app.models.*` Stub 模組、修正 Python 3.10 相容性問題、在 VM（Ubuntu 22.04）上完成 PostgreSQL 安裝與 `formdb` 建立，使 `bash deploy.sh --background` 能夠成功啟動後端並通過完整 E2E 測試。

---

## 3. 修改前後差異 (Before & After)

### 變更點 A：補全 `app.schemas` 套件

* **修改前 (Before)**：
  * `app/schemas/` 目錄不存在，`routes_upload.py`、`routes_validate.py`、`routes_import.py`、`routes_import_v2.py` 等路由在啟動時拋出 `ModuleNotFoundError: No module named 'app.schemas'`，後端無法啟動。
* **修改後 (After)**：
  * 新建 `app/schemas/__init__.py` 及 6 個 Schema 檔案（`upload.py`、`validate.py`、`import_data.py`、`audit.py`、`import_job.py`、`pdf_conversion.py`），皆為 Pydantic v2 `BaseModel`，搭配 `ConfigDict(from_attributes=True)` 支援 ORM 模式。
* **設計考量 (Reasoning)**：Schema 模組為 routes 的靜態依賴，採用 Stub 方式快速解除封鎖；Stub 欄位與 routes 的回傳型別宣告保持一致，避免型別錯誤。

### 變更點 B：補全 `app.models` 缺失模型

* **修改前 (Before)**：
  * `app/models/` 缺少 `audit.py`（`RowEdit`）、`record.py`（`Record`、`DataType`）、`p2_item.py`（`P2Item`）、`p3_item.py`（`P3Item`），導致路由或 service 啟動時拋出 `ModuleNotFoundError`。
* **修改後 (After)**：
  * 四個 SQLAlchemy ORM 模型補齊，`models/__init__.py` 同步匯出所有新類別。
  * `p3_item.py` 包含 `UniqueConstraint("record_id", "product_id")`。
* **設計考量 (Reasoning)**：Python 3.10 環境，不能使用 `datetime.UTC`（3.11+），改用 `timezone.utc`；不能使用內建 `StrEnum`，改繼承 `(str, Enum)`。

### 變更點 C：擴充 `AuditEvent` 模型欄位

* **修改前 (Before)**：
  * `app/models/core/audit_event.py` 只有 8 個基礎欄位，`main.py` 建立 `AuditEvent` 時傳入額外欄位導致 `TypeError`。
* **修改後 (After)**：
  * 補入 `actor_api_key_id`、`actor_label_snapshot`、`request_id`、`method`、`path`、`status_code`、`client_host`、`user_agent`、`metadata_json`，`tenant_id` 改為 `nullable=True`。
* **設計考量 (Reasoning)**：最小化改動，只補缺失欄位；不移除舊欄位，保持向下相容。

### 變更點 D：`app.config.constants` 從 Stub 升級為 env var 驅動

* **修改前 (Before)**：
  * `VALID_MATERIALS = []` 硬編碼空清單，當有任何值需要驗證時，`not in []` 恆為 True，導致全部拒絕。
* **修改後 (After)**：
  * 從 `VALID_MATERIALS_CSV` / `VALID_SLITTING_MACHINES_CSV` 環境變數讀取（逗號分隔）；未設定 → `[]`。
  * `validation.py` 加入空清單 guard：`if not VALID_MATERIALS: return True`，語意改為「未設定 = 跳過驗證」。
* **設計考量 (Reasoning)**：空清單應代表「尚未設定，跳過驗證」而非「無效值全部拒絕」。Guard 確保語意正確。

### 變更點 E：VM PostgreSQL 安裝與資料庫建立

* **修改前 (Before)**：
  * VM（192.168.200.33）未安裝 PostgreSQL，後端啟動後嘗試連線時拋出 `ConnectionRefusedError: [Errno 111] Connection refused`。
* **修改後 (After)**：
  * 透過 `tools/_vm_setup_db.py` 安裝 PostgreSQL，建立 role `gslab` 及資料庫 `formdb`。
  * 透過 `tools/_vm_migrate.py` 執行 `generated_db_bootstrap.py`，建立全部 29 張資料表。
* **設計考量 (Reasoning)**：全程透過 Paramiko SSH 自動化操作，可重複執行（`IF NOT EXISTS` 保護）。

### 變更點 F：Python 3.10 相容性清理（StrEnum）

* **修改前 (Before)**：
  * `csv_field_mapper.py`、`import_job.py`、`pdf_conversion_job.py`、`upload_job.py` 各自有重複的 `try/except ImportError` StrEnum shim。
* **修改後 (After)**：
  * 移除所有 shim，直接改為 `class X(str, Enum)`，行為等價且語法更簡潔。
* **設計考量 (Reasoning)**：Python 3.10 支援 `(str, Enum)` 繼承達到與 `StrEnum` 相同效果，無需條件導入。

---

## 4. 測試內容與結果 (Testing)

* **測試環境**：Ubuntu 22.04 VM (192.168.200.33) / Python 3.10 / FastAPI + asyncpg / PostgreSQL 14

* **已執行測試與結果**：
  * [x] **[任務1] 常數模組** `VALID_MATERIALS_CSV` 未設定時，`validate_material_code()` 回傳 True（跳過驗證）-> **Pass**
  * [x] **[任務2] DB Migration** `generated_db_bootstrap.py` 成功建立 29 張資料表，`psql \dt` 與 ORM 定義完全一致 -> **Pass**（tableCount=29）
  * [x] **[任務3] E2E Upload** `POST /api/upload`（P1_2507173_01.csv，3 列）-> **Pass**（HTTP 200，total_rows=3，valid_rows=3，invalid_rows=0）
  * [x] **[任務3] E2E Status** `GET /api/upload/{process_id}/status` -> **Pass**（HTTP 200，status=VALIDATED）
  * [x] **[任務3] API Key 認證** `X-API-Key` header 驗證機制正常，tenant 解析正確 -> **Pass**
  * [x] **[任務4] Python 3.10 掃描** `datetime.UTC`、裸露 `StrEnum`、`typing.Self`、`tomllib`、`ExceptionGroup` 均未出現 -> **Pass**
  * [x] **[任務4] StrEnum 清理** 4 個檔案移除 try/except shim，改為 `(str, Enum)` -> **Pass**（grep StrEnum 無結果）
  * [ ] **[材料驗證]** 使用非空白的 `VALID_MATERIALS` 清單驗證 CSV 欄位 -> **未測試**（需在 `.env` 設定 `VALID_MATERIALS_CSV`）

---

## 5. AI Agent 接下來的任務 (Next Steps for AI)

1. **重新封裝並上傳 ZIP**：將本次所有本地修改（`dist/generated-system/backend/` 下的 6 個更新檔案）打包成新版 ZIP 上傳至 VM，取代舊版 `client-deploy-mvp-import-flow-v12.zip`，使完整安裝測試基於最新程式碼。
2. **填入真實業務常數**：在 VM `.env` 設定 `VALID_MATERIALS_CSV` 與 `VALID_SLITTING_MACHINES_CSV`，執行含無效材料代號的 CSV 上傳，確認驗證邏輯正確拒絕。
3. **Import Job 流程測試**：建立 `TableRegistry` 資料後，測試 `POST /api/v2/import/jobs`（上傳 CSV 建立匯入 Job）→ `POST /api/v2/import/jobs/{job_id}/commit`（提交匯入）完整流程。
4. **前端連線測試**：確認前端（若已部署）能正確呼叫後端 API，CORS 設定無誤。
