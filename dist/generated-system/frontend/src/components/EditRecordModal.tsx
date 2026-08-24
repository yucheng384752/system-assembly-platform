import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useToast } from "../components/common/ToastContext";
import { getApiKeyHeaderName, getApiKeyValue } from "../services/auth";
import { TENANT_STORAGE_KEY } from "../services/tenant";
import type { FieldDef, RecordRow } from "../pages/FormsPage";

type Scalar = string | number | boolean | null;
type EditReason = { id: string; code: string; label: string; is_active: boolean };

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

function inputValue(field: FieldDef, value: unknown): string | boolean {
  if (field.type === "boolean") return typeof value === "boolean" ? value : false;
  if (value === null || value === undefined) return "";
  return field.type === "date" ? String(value).slice(0, 10) : String(value);
}

function scalarValue(field: FieldDef, value: string | boolean): Scalar {
  if (field.type === "boolean") return Boolean(value);
  const text = String(value).trim();
  if (!text) return null;
  if (field.type === "integer" || field.type === "decimal") {
    const n = Number(text);
    return Number.isNaN(n) ? text : (field.type === "integer" ? Math.trunc(n) : n);
  }
  return text;
}

const inputStyle: CSSProperties = { padding: "7px 9px", border: "1px solid #d1d5db", borderRadius: 4 };

export function EditRecordModal({
  tableCode,
  fields,
  record,
  onClose,
  onSaved,
}: {
  tableCode: string;
  fields: FieldDef[];
  record: RecordRow;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [values, setValues] = useState<Record<string, string | boolean>>({});
  const [reasons, setReasons] = useState<EditReason[]>([]);
  const [reasonId, setReasonId] = useState("");
  const [loadingReasons, setLoadingReasons] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setValues(Object.fromEntries(fields.map((field) => [field.name, inputValue(field, record.data[field.name])])));
    setReasonId("");
    setError("");
  }, [fields, record]);

  useEffect(() => {
    let cancelled = false;
    setLoadingReasons(true);
    fetch("/api/edit/reasons", { headers: apiHeaders() })
      .then(async (res) => {
        if (!res.ok) throw new Error(await readErrorDetail(res));
        return res.json() as Promise<EditReason[]>;
      })
      .then((body) => { if (!cancelled) setReasons(body.filter((reason) => reason.is_active)); })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "載入編輯原因失敗"); })
      .finally(() => { if (!cancelled) setLoadingReasons(false); });
    return () => { cancelled = true; };
  }, []);

  const changes = useMemo(() => Object.fromEntries(fields.flatMap((field) => {
    const next = scalarValue(field, values[field.name] ?? "");
    const original = scalarValue(field, inputValue(field, record.data[field.name]));
    return Object.is(next, original) ? [] : [[field.name, next]];
  })) as Record<string, Scalar>, [fields, record, values]);

  const requiredMissing = fields.some((field) => field.required && scalarValue(field, values[field.name] ?? "") === null);
  const canSave = !loadingReasons && !saving && reasons.length > 0 && Boolean(reasonId)
    && Object.keys(changes).length > 0 && !requiredMissing;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`/api/edit/records/${encodeURIComponent(tableCode)}/${record.id}`, {
        method: "PATCH",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ reason_id: reasonId, changes }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      await onSaved();
      showToast("success", "紀錄已更新");
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "更新紀錄失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,.45)", display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={(event) => { if (!saving && event.target === event.currentTarget) onClose(); }}>
      <form onSubmit={(event) => { event.preventDefault(); void save(); }}
        style={{ width: "min(620px, 92vw)", maxHeight: "90vh", overflow: "auto", background: "#fff", borderRadius: 8, padding: 24, boxShadow: "0 8px 32px rgba(0,0,0,.18)" }}>
        <h3 style={{ margin: "0 0 16px" }}>編輯紀錄</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {fields.map((field) => (
            <label key={field.name} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
              <span>{field.label || field.name}{field.required ? <span style={{ color: "#dc2626" }}> *</span> : null}</span>
              {field.type === "boolean" ? (
                <input type="checkbox" checked={Boolean(values[field.name])}
                  onChange={(event) => setValues((previous) => ({ ...previous, [field.name]: event.target.checked }))} />
              ) : (
                <input style={inputStyle} type={field.type === "date" ? "date" : field.type === "string" ? "text" : "number"}
                  step={field.type === "decimal" ? "any" : undefined} required={field.required}
                  value={String(values[field.name] ?? "")}
                  onChange={(event) => setValues((previous) => ({ ...previous, [field.name]: event.target.value }))} />
              )}
            </label>
          ))}
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
            編輯原因 <span style={{ color: "#dc2626" }}>*</span>
            <select style={inputStyle} value={reasonId} disabled={loadingReasons || reasons.length === 0}
              onChange={(event) => setReasonId(event.target.value)}>
              <option value="">請選擇</option>
              {reasons.map((reason) => <option key={reason.id} value={reason.id}>{reason.label} ({reason.code})</option>)}
            </select>
          </label>
          {!loadingReasons && reasons.length === 0 ? <div style={{ color: "#d97706", fontSize: 13 }}>尚無可用原因，請先由管理者於「編輯原因管理」建立。</div> : null}
          {requiredMissing ? <div style={{ color: "#dc2626", fontSize: 13 }}>必填欄位不可為空。</div> : null}
          {error ? <div style={{ color: "#dc2626", fontSize: 13 }}>{error}</div> : null}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <button type="button" disabled={saving} onClick={onClose} style={{ ...inputStyle, background: "#fff" }}>取消</button>
          <button type="submit" disabled={!canSave} style={{ ...inputStyle, background: canSave ? "#2563eb" : "#9ca3af", color: "#fff", border: "none" }}>
            {saving ? "儲存中…" : "儲存"}
          </button>
        </div>
      </form>
    </div>
  );
}
