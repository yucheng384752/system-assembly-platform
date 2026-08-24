import { useEffect, useState } from "react";
import { useToast } from "../components/common/ToastContext";
import { getApiKeyHeaderName, getApiKeyValue } from "../services/auth";
import { TENANT_STORAGE_KEY } from "../services/tenant";
import "../styles/manager-page.css";

type EditReason = { id: string; code: string; label: string; is_active: boolean; created_at: string | null };
type Draft = { label: string; is_active: boolean };

function apiHeaders(extra: Record<string, string> = {}): HeadersInit {
  const tenantId = window.localStorage.getItem(TENANT_STORAGE_KEY) || "";
  const apiKey = getApiKeyValue();
  const headers: Record<string, string> = { ...extra };
  if (tenantId) headers["X-Tenant-Id"] = tenantId;
  if (apiKey) headers[getApiKeyHeaderName()] = apiKey;
  return headers;
}

async function readErrorDetail(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = (body as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : JSON.stringify(detail || `HTTP ${res.status}`);
}

export function EditReasonsPage() {
  const { showToast } = useToast();
  const [reasons, setReasons] = useState<EditReason[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [newCode, setNewCode] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);

  async function loadReasons() {
    try {
      const res = await fetch("/api/edit/reasons", { headers: apiHeaders() });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      const body = await res.json() as EditReason[];
      setReasons(body);
      setDrafts(Object.fromEntries(body.map((reason) => [reason.id, { label: reason.label, is_active: reason.is_active }])));
    } catch (cause) {
      showToast("error", cause instanceof Error ? cause.message : "載入編輯原因失敗");
      setReasons([]);
    }
  }

  useEffect(() => { void loadReasons(); }, []);

  async function createReason() {
    const code = newCode.trim();
    const label = newLabel.trim();
    if (!code || !label) return;
    setCreating(true);
    try {
      const res = await fetch("/api/edit/reasons", {
        method: "POST",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ code, label }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      setNewCode("");
      setNewLabel("");
      showToast("success", "編輯原因已建立");
      await loadReasons();
    } catch (cause) {
      showToast("error", cause instanceof Error ? cause.message : "建立編輯原因失敗");
    } finally {
      setCreating(false);
    }
  }

  async function saveReason(reason: EditReason) {
    const draft = drafts[reason.id] ?? { label: reason.label, is_active: reason.is_active };
    const patch: { label?: string; is_active?: boolean } = {};
    const label = draft.label.trim();
    if (label !== reason.label) patch.label = label;
    if (draft.is_active !== reason.is_active) patch.is_active = draft.is_active;
    if (!label || Object.keys(patch).length === 0) return;
    setSavingId(reason.id);
    try {
      const res = await fetch(`/api/edit/reasons/${reason.id}`, {
        method: "PATCH",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      showToast("success", "編輯原因已更新");
      await loadReasons();
    } catch (cause) {
      showToast("error", cause instanceof Error ? cause.message : "更新編輯原因失敗");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="manager-page">
      <div className="manager-header">
        <div><h2 className="manager-title">編輯原因管理</h2><div className="manager-subtitle">建立與維護紀錄編輯時可選用的原因。</div></div>
        <button className="btn-secondary" onClick={() => void loadReasons()}>重新整理</button>
      </div>
      <div className="manager-card">
        <div className="manager-row">
          <label className="manager-label">代碼<input className="manager-input" maxLength={100} value={newCode} onChange={(event) => setNewCode(event.target.value)} /></label>
          <label className="manager-label">標籤<input className="manager-input" maxLength={255} value={newLabel} onChange={(event) => setNewLabel(event.target.value)} /></label>
          <div className="manager-row-actions"><button className="btn-secondary" disabled={creating || !newCode.trim() || !newLabel.trim()} onClick={() => void createReason()}>{creating ? "建立中…" : "建立"}</button></div>
        </div>
      </div>
      <div className="manager-card">
        {reasons === null ? <div className="muted">載入中…</div> : reasons.length === 0 ? <div className="muted">尚無編輯原因</div> : (
          <div className="manager-table-wrap"><table className="manager-table">
            <thead><tr><th>代碼</th><th>標籤</th><th>啟用</th><th>建立時間</th><th>操作</th></tr></thead>
            <tbody>{reasons.map((reason) => {
              const draft = drafts[reason.id] ?? { label: reason.label, is_active: reason.is_active };
              const dirty = draft.label.trim() !== reason.label || draft.is_active !== reason.is_active;
              const busy = savingId === reason.id;
              return <tr key={reason.id} className={!reason.is_active ? "is-inactive" : ""}>
                <td><code>{reason.code}</code></td>
                <td><input className="manager-input" maxLength={255} value={draft.label} onChange={(event) => setDrafts((previous) => ({ ...previous, [reason.id]: { ...draft, label: event.target.value } }))} /></td>
                <td><input type="checkbox" checked={draft.is_active} onChange={(event) => setDrafts((previous) => ({ ...previous, [reason.id]: { ...draft, is_active: event.target.checked } }))} /></td>
                <td><span className="small">{reason.created_at || "—"}</span></td>
                <td><button className="btn-secondary" disabled={!dirty || busy || !draft.label.trim()} onClick={() => void saveReason(reason)}>{busy ? "儲存中…" : "儲存"}</button></td>
              </tr>;
            })}</tbody>
          </table></div>
        )}
      </div>
    </div>
  );
}
