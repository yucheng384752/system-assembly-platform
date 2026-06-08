你是這個專案的 Git 工作流程執行者。當使用者說「git push」、「推送」、「commit 並推送」、「commit/push」或呼叫 `/git-push` 時，執行以下完整流程。

---

## 規則總覽

| # | 規則 |
|---|------|
| 1 | **約定式提交**：commit 標題必須符合 Conventional Commits 格式 |
| 2 | **新功能開分支**：feature 類型的改動必須在非 master/main 的分支上進行 |
| 3 | **Merge 前人工確認**：建立 PR 前暫停，提醒使用者確認測試結果 |
| 4 | **中文撰寫**：commit 訊息與 PR 說明一律用繁體中文 |
| 5 | **不加共同協作者**：commit 只保留 `gslab`，不加 `Co-Authored-By` 行 |

---

## 執行步驟

### Step 1 — 讀取現況

執行以下指令（可並行）：
- `git status --short`
- `git diff HEAD`
- `git branch --show-current`
- `git log --oneline -5`

### Step 2 — 分析變更類型

根據變更內容判斷 commit 類型：

| 類型 | 適用情境 |
|------|---------|
| `feat` | 新功能、新頁面、新 API |
| `fix` | 修正 bug、錯誤行為 |
| `docs` | 文件、README、Obsidian 筆記 |
| `refactor` | 重構（不影響行為） |
| `build` | 打包腳本、PyInstaller、PowerShell 工具 |
| `test` | 測試腳本 |
| `chore` | 設定檔、.gitignore、雜項維護 |
| `style` | 純格式、CSS、排版（不影響邏輯） |

### Step 3 — 分支檢查（新功能規則）

- 若目前在 `master` 或 `main`，**且** 變更類型為 `feat`：
  - 詢問使用者要用什麼分支名稱，或建議 `feat/<簡短說明>` 格式
  - 執行 `git checkout -b <branch-name>` 後再繼續
- 其他類型（fix、docs、build 等）可直接在 master 上操作

### Step 4 — 撰寫 commit 訊息（繁體中文）

格式：
```
<類型>(<範圍>): <簡短說明>

<選填：詳細說明，每行不超過 72 字>
```

規則：
- **標題行**：`<類型>(<範圍>): <繁體中文說明>`，不超過 72 字
- **範圍**：填寫最主要影響的模組，例如 `wizard`、`deploy`、`gui`、`license`
- **說明**：用繁體中文描述「做了什麼」和「為什麼」
- **不加** `Co-Authored-By` 行

範例：
```
feat(wizard): 安裝精靈新增系統目錄可編輯功能

Step 0 的系統目錄從唯讀文字改為可編輯 input，
搭配「驗證」按鈕呼叫 GET /api/sys-root?path= 確認路徑有效。
```

### Step 5 — 執行 commit 與 push

```bash
git add <相關檔案>   # 不使用 git add -A，避免意外包含 .env 等敏感檔案
git commit -m "..."  # 使用 HEREDOC 確保格式正確
git push
```

### Step 6 — Merge 前人工確認（PR 流程）

若使用者要求建立 PR，**在執行 `gh pr create` 之前**暫停並顯示以下提醒：

```
⚠️  Merge 前確認清單

請手動確認以下項目後，再告知我繼續建立 PR：

□ 功能測試通過（主要流程走過一遍）
□ 沒有明顯的 console error / 例外
□ 相關文件（README / Obsidian）已更新
□ 敏感資料（密碼、金鑰）未包含在 commit 中

確認完成後請回覆「確認」或「可以建立 PR」。
```

等待使用者確認後，才執行 `gh pr create`。

### Step 7 — 建立 PR（繁體中文）

```bash
gh pr create --title "<繁體中文標題>" --body "$(cat <<'EOF'
## 摘要
- <改動要點 1>
- <改動要點 2>

## 測試計畫
- [ ] <測試項目 1>
- [ ] <測試項目 2>
EOF
)"
```

- 標題與內文全部使用繁體中文
- 不加 Claude Code 的 attribution 連結

---

## 注意事項

- `dist/` 目錄下的產出物（zip、staged system）通常不需要 commit，除非使用者明確指定
- `.env`、`*.pem`、`signing-private-key.pem` 永遠不 commit
- 若有 pre-commit hook 失敗，先修正問題再重新 commit，不使用 `--no-verify`
