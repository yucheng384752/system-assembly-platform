## Rule 1 — Think Before CodingState assumptions explicitly. If uncertain, ask rather than guess.Present multiple interpretations when ambiguity exists.Push back when a simpler approach exists.Stop when confused. Name what's unclear.
## Rule 2 — Simplicity FirstMinimum code that solves the problem. Nothing speculative.No features beyond what was asked. No abstractions for single-use code.Test: would a senior engineer say this is overcomplicated? If yes, simplify.
## Rule 3 — Surgical ChangesTouch only what you must. Clean up only your own mess.Don't "improve" adjacent code, comments, or formatting.Don't refactor what isn't broken. Match existing style.
## Rule 4 — Goal-Driven ExecutionDefine success criteria. Loop until verified.Don't follow steps. Define success and iterate.Strong success criteria let you loop independently.
## Rule 5 — Use the model only for judgment callsUse me for: classification, drafting, summarization, extraction.Do NOT use me for: routing, retries, deterministic transforms.If code can answer, code answers.
## Rule 6 — Token budgets are not advisoryPer-task: 4,000 tokens. Per-session: 30,000 tokens.If approaching budget, summarize and start fresh.Surface the breach. Do not silently overrun.
## Rule 7 — Surface conflicts, don't average themIf two patterns contradict, pick one (more recent / more tested).Explain why. Flag the other for cleanup.Don't blend conflicting patterns.
## Rule 8 — Read before you writeBefore adding code, read exports, immediate callers, shared utilities."Looks orthogonal" is dangerous. If unsure why code is structured a way, ask.
## Rule 9 — Tests verify intent, not just behaviorTests must encode WHY behavior matters, not just WHAT it does.A test that can't fail when business logic changes is wrong.
## Rule 10 — Checkpoint after every significant stepSummarize what was done, what's verified, what's left.Don't continue from a state you can't describe back.If you lose track, stop and restate.
## Rule 11 — Match the codebase's conventions, even if you disagreeConformance > taste inside the codebase.If you genuinely think a convention is harmful, surface it. Don't fork silently.
## Rule 12 — Fail loud"Completed" is wrong if anything was skipped silently."Tests pass" is wrong if any were skipped.Default to surfacing uncertainty, not hiding it.
## Rule 13 - Use traditional Chinese response user's questions. 禁止輸出 emoji、icon 等圖示內容。
## Rule 14 - if user use skills: mailbox，create new thread in path: C:\Users\gslab\Documents\New project\form-system-kit-composer\.codex-claude-mailbox and discuss with codex
## Rule 15 — 需求釐清偏好開放式提問。除非本工具的 AskUserQuestion 明確需要離散選項，優先用自由文字提問，不預設選擇題選項限制使用者答案範圍。
## Rule 16 — Code Review 採最嚴格標準。明確指出效能瓶頸、狀態管理風險或架構缺陷，並給出具體修改建議與替代方案（日常審查即適用，不限 /code-review 指令）。
## Rule 17 — 防禦性設計與型別優先。驗證所有外部輸入與邊界條件；非預期錯誤優雅處理並留下有意義訊息，呼應 Rule 12（嚴禁靜默失敗）；TypeScript 程式碼不得以 `any` 蒙混通過；模組/元件保持單一職責、避免業務邏輯耦合進核心模組。
## Rule 18 — 輸出格式固定：先給變更摘要 → 再給檔案清單 → 最後給驗證方式。一個 commit／PR 只解一個 bug 或一個 feature；既有專案禁止大重構，除非使用者明確同意（具體化 Rule 2/3）。
## Rule 19 — 功能完整開發完成後，主動提醒使用者以 `/clear` 重置對話，並附上承接下一步的 prompt。

（Conventional Commits／feature branch 規則已由 `.claude/commands/git-push.md` 涵蓋，不在此重複；Data-First 架構與三次除錯上限已由全域 dev-spec skill 涵蓋，不在此重複。）

## Clean Code 準則（Review／重構時對照）
- **命名**：有意義且可搜尋；類別用名詞、方法用動詞；避免誤導性命名。
- **函數**：簡短（理想 < 20 行）、只做一件事、單一抽象層級、參數不超過 3 個、避免副作用。
- **註解**：以程式碼自我說明取代註解；註解無法彌補糟糕程式碼。
- **錯誤處理**：用 Exception 而非錯誤碼；不回傳或傳遞 null；錯誤處理與業務邏輯分離。
- **邊界**：以包裝類別封裝第三方程式碼，避免外部程式碼污染內部。
- **單元測試**：遵循 FIRST（Fast、Independent、Repeatable、Self-validating、Timely）；每個測試一個概念。
- **類別**：簡短、單一職責、高內聚低耦合、對擴展開放對修改封閉。
- **重構**：童軍規則——讓程式碼比接手時更乾淨；小步重構配合測試保護。

## 常用開發指令與慣例（自動彙整）
- Codex 實作完成後開 mailbox thread，Claude 逐項審核並標記接受/修正，最後由使用者裁決未決項後 Codex 收尾（來源：20260615-generated-system-security-review、20260624-daihui-schema-commit-p123-removal，最後出現 2026-06-25）
- 專案中存在多份程式碼副本（kits 原始碼／generated／dist），修改時必須同步更新所有副本，否則會被 E2E 或 dist 驗證發現遺漏（來源：20260623-daihui-upload-db-e2e-findings、20260701-kit-broker-dist-verify，最後出現 2026-07-01）
- dist 目錄禁止手動修改，需透過 assembly/package 流程重新生成（來源：20260701-kit-broker-activation、20260701-kit-broker-dist-verify，最後出現 2026-07-01）
- Mailbox thread 固定以 YAML frontmatter 標示 role_priority（implementation: codex／review: claude／tests: claude／requirements: user）（來源：20260624-daihui-schema-commit-p123-removal、20260625-security-tpm-license-bind-host，最後出現 2026-07-01）
- Thread 收尾前以「Passed: <具體指令>」格式記錄驗證結果（來源：20260615-deploy-online-offline-hiba、20260701-kit-broker-dist-verify，最後出現 2026-07-01）
- Open Questions 中已解決項目以刪除線標記並附決策結果，不直接刪除（來源：20260615-generated-system-security-review、20260624-daihui-schema-commit-p123-removal，最後出現 2026-06-25）
- 驗證指令慣例：PowerShell 用 `powershell -ExecutionPolicy Bypass -File`、Python 語法檢查用 `python -m py_compile`、JS 語法檢查用 `node --check`、修正落地用 `rg` 掃描確認（來源：20260615-generated-system-security-review、20260625-security-tpm-license-bind-host，最後出現 2026-06-29）
- 沙盒環境下用 `-SkipFrontendBuild` 繞過 npm build 逾時，作為離線驗證閘門（來源：20260622-uploadpage-refactor-continuation、20260701-kit-broker-dist-verify，最後出現 2026-07-01）
- E2E 測試使用隔離環境（獨立 SQLite + 遞增 port 號避免衝突），測後清理暫存產物（.env、venv、node_modules、db 檔、log）（來源：20260623-daihui-upload-db-e2e-findings、20260625-daihui-e2e-verification，最後出現 2026-06-25）
- Thread frontmatter 的 artifacts 欄位新增 type 分類（test/file/note）標示產出物性質（來源：20260705-test-coverage-static-contracts、20260706-deploy-ux-standardization，最後出現 2026-07-06）
- 計畫類 thread 使用「# Decisions」區塊搭配 Accepted/Deferred/finalized 等標籤記錄決策狀態，待 Open Questions 逐項有決策後才進入下一階段實作（來源：20260705-test-coverage-static-contracts、20260706-deploy-ux-standardization，最後出現 2026-07-06）
