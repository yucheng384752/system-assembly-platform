import { useState, useEffect, useRef, type CSSProperties } from "react";
import { getApiKeyValue, getApiKeyHeaderName } from "../services/auth";
import { TENANT_STORAGE_KEY } from "../services/tenant";
import { EditRecordModal } from "../components/EditRecordModal";

export type FieldType = "string" | "integer" | "decimal" | "date" | "boolean";

export interface FieldDef {
  name: string;
  type: FieldType;
  label: string;
  required: boolean;
  is_key: boolean;
}

interface FormType {
  id: string;
  code: string;
  name: string;
  sort_order: number;
  schema_version: number | null;
  fields: FieldDef[] | null;
}

export interface RecordRow {
  id: string;
  lot_no_raw: string;
  data: Record<string, unknown>;
  created_at: string;
}

type SubTab = "schema" | "upload" | "records";
type EditReason = { id: string; code: string; label: string; is_active: boolean };

const FIELD_TYPES: FieldType[] = ["string", "integer", "decimal", "date", "boolean"];
const EMPTY_FIELDS: FieldDef[] = [];

function apiHeaders(extra: Record<string, string> = {}): HeadersInit {
  const tenantId = window.localStorage.getItem(TENANT_STORAGE_KEY) || "";
  const apiKey = getApiKeyValue();
  const h: Record<string, string> = { ...extra };
  if (tenantId) h["X-Tenant-Id"] = tenantId;
  if (apiKey) h[getApiKeyHeaderName()] = apiKey;
  return h;
}

const cell: CSSProperties = { padding: "6px 8px", border: "1px solid #ddd" };
const btn = (color = "#2563eb"): CSSProperties => ({
  padding: "5px 12px", background: color, color: "#fff", border: "none",
  borderRadius: 4, cursor: "pointer", fontSize: 13,
});

export function FormsPage() {
  const [forms, setForms] = useState<FormType[]>([]);
  const [selected, setSelected] = useState<FormType | null>(null);
  const [subTab, setSubTab] = useState<SubTab>("schema");
  const [loading, setLoading] = useState(false);

  // create dialog
  const [creating, setCreating] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");

  // schema editor
  const [editFields, setEditFields] = useState<FieldDef[]>([]);
  const [schemaSaving, setSchemaSaving] = useState(false);
  const [schemaErrors, setSchemaErrors] = useState<string[]>([]);
  const [editReasons, setEditReasons] = useState<EditReason[]>([]);
  const [loadingReasons, setLoadingReasons] = useState(true);
  const [reasonLoadFailed, setReasonLoadFailed] = useState(false);
  const [schemaReasonId, setSchemaReasonId] = useState("");

  // upload
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [allowDup, setAllowDup] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ imported: number; skipped: number; errors: { row: number; errors: string[] }[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  // records
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [editingRecord, setEditingRecord] = useState<RecordRow | null>(null);
  const PAGE_SIZE = 50;

  async function loadForms() {
    setLoading(true);
    try {
      const res = await fetch("/api/forms", { headers: apiHeaders() });
      if (res.ok) setForms(await res.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadForms(); }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/edit/reasons", { headers: apiHeaders() })
      .then(res => (res.ok ? (res.json() as Promise<EditReason[]>) : Promise.reject(res.status)))
      .then(body => { if (!cancelled) setEditReasons(body.filter(r => r.is_active)); })
      .catch(() => { if (!cancelled) { setEditReasons([]); setReasonLoadFailed(true); } })
      .finally(() => { if (!cancelled) setLoadingReasons(false); });
    return () => { cancelled = true; };
  }, []);

  function selectForm(f: FormType) {
    setSelected(f);
    setSubTab("schema");
    setEditFields(f.fields ? f.fields.map(fd => ({ ...fd })) : []);
    setSchemaReasonId("");
    setUploadResult(null);
    setUploadFile(null);
    setRecords([]);
    setPage(1);
    setTotal(0);
  }

  async function createForm() {
    if (!newCode.trim()) return;
    const res = await fetch("/api/forms", {
      method: "POST",
      headers: apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ code: newCode.trim().toUpperCase(), name: newName.trim() || newCode.trim(), sort_order: 0 }),
    });
    if (res.ok) {
      const created: FormType = await res.json();
      setCreating(false);
      setNewCode(""); setNewName("");
      await loadForms();
      selectForm(created);
    }
  }

  async function deleteForm(code: string) {
    if (!confirm(`確定刪除表單 ${code} 及其所有紀錄？`)) return;
    await fetch(`/api/forms/${code}`, { method: "DELETE", headers: apiHeaders() });
    if (selected?.code === code) setSelected(null);
    loadForms();
  }

  function validateSchema(fields: FieldDef[]): string[] {
    const errs: string[] = [];
    if (fields.length === 0) errs.push("Schema 至少需要一個欄位");
    const names = fields.map(f => f.name.trim());
    names.forEach((n, i) => {
      if (!n) errs.push(`第 ${i + 1} 個欄位名稱不可為空`);
      else if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(n)) errs.push(`欄位名稱 "${n}" 只能包含英文字母、數字與底線，且不可以數字開頭`);
    });
    const dupes = names.filter((n, i) => n && names.indexOf(n) !== i);
    if (dupes.length > 0) errs.push(`欄位名稱重複：${[...new Set(dupes)].join("、")}`);
    const keyFields = fields.filter(f => f.is_key);
    if (keyFields.length === 0) errs.push("至少需要一個識別鍵欄位（is_key）");
    return errs;
  }

  async function saveSchema() {
    if (!selected) return;
    const errs = validateSchema(editFields);
    if (!schemaReasonId) errs.push("請選擇編輯原因");
    if (errs.length > 0) { setSchemaErrors(errs); return; }
    setSchemaErrors([]);
    setSchemaSaving(true);
    try {
      const res = await fetch(`/api/forms/${selected.code}/schema`, {
        method: "PUT",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ fields: editFields, reason_id: schemaReasonId }),
      });
      if (res.ok) {
        const updated: FormType = await res.json();
        setForms(prev => prev.map(f => f.code === updated.code ? updated : f));
        setSelected(updated);
        setEditFields(updated.fields ? updated.fields.map(fd => ({ ...fd })) : []);
        setSchemaReasonId("");
      } else {
        const err = await res.json().catch(() => ({}));
        setSchemaErrors([err.detail || `儲存失敗 ${res.status}`]);
      }
    } finally {
      setSchemaSaving(false);
    }
  }

  function updateField(idx: number, key: keyof FieldDef, value: unknown) {
    setEditFields(prev => prev.map((f, i) => i === idx ? { ...f, [key]: value } : f));
  }

  function addField() {
    setEditFields(prev => [...prev, { name: "", type: "string", label: "", required: false, is_key: false }]);
  }

  async function uploadCsv() {
    if (!selected || !uploadFile) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      fd.append("allow_duplicate", String(allowDup));
      const res = await fetch(`/api/forms/${selected.code}/upload`, { method: "POST", headers: apiHeaders(), body: fd });
      if (res.ok) setUploadResult(await res.json());
      else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || `上傳失敗 ${res.status}`);
      }
    } finally {
      setUploading(false);
    }
  }

  async function loadRecords(p = page) {
    if (!selected) return;
    const res = await fetch(`/api/forms/${selected.code}/records?page=${p}&page_size=${PAGE_SIZE}`, { headers: apiHeaders() });
    if (res.ok) {
      const data = await res.json();
      setRecords(data.records);
      setTotal(data.total);
    }
  }

  useEffect(() => {
    if (subTab === "records" && selected) loadRecords(page);
  }, [subTab, selected, page]);

  async function deleteRecord(id: string) {
    if (!selected) return;
    await fetch(`/api/forms/${selected.code}/records/${id}`, { method: "DELETE", headers: apiHeaders() });
    loadRecords(page);
  }

  // drag-drop
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) setUploadFile(f);
  }

  const columns = selected?.fields?.map(f => f.name) ?? [];

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 0 }}>
      {/* Left panel */}
      <div style={{ width: 220, borderRight: "1px solid #e5e7eb", padding: "12px 8px", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>表單類型</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button style={btn("#6b7280")} onClick={loadForms} title="重新整理">↻</button>
            <button style={btn()} onClick={() => setCreating(true)}>＋</button>
          </div>
        </div>

        {creating && (
          <div style={{ background: "#f9fafb", border: "1px solid #d1d5db", borderRadius: 6, padding: 8, display: "flex", flexDirection: "column", gap: 6 }}>
            <input placeholder="代號 (英文大寫)" value={newCode} onChange={e => setNewCode(e.target.value)}
              style={{ padding: "4px 6px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            <input placeholder="名稱" value={newName} onChange={e => setNewName(e.target.value)}
              style={{ padding: "4px 6px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            <div style={{ display: "flex", gap: 4 }}>
              <button style={btn()} onClick={createForm}>建立</button>
              <button style={btn("#6b7280")} onClick={() => { setCreating(false); setNewCode(""); setNewName(""); }}>取消</button>
            </div>
          </div>
        )}

        {loading ? <span style={{ fontSize: 13, color: "#6b7280" }}>載入中…</span> : null}

        {forms.map(f => (
          <div key={f.code}
            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", borderRadius: 6, cursor: "pointer", background: selected?.code === f.code ? "#eff6ff" : "transparent", border: selected?.code === f.code ? "1px solid #bfdbfe" : "1px solid transparent" }}
            onClick={() => selectForm(f)}
          >
            <div>
              <div style={{ fontWeight: 500, fontSize: 13 }}>{f.name}</div>
              <div style={{ fontSize: 11, color: "#6b7280" }}>{f.code}{f.schema_version ? ` v${f.schema_version}` : ""}</div>
            </div>
            <button style={{ background: "none", border: "none", cursor: "pointer", color: "#ef4444", fontSize: 14 }}
              onClick={e => { e.stopPropagation(); deleteForm(f.code); }}>✕</button>
          </div>
        ))}
      </div>

      {/* Right panel */}
      <div style={{ flex: 1, padding: 16, display: "flex", flexDirection: "column", gap: 12, minWidth: 0, overflow: "auto" }}>
        {!selected ? (
          <div style={{ color: "#6b7280", margin: "auto" }}>請從左側選擇表單類型</div>
        ) : (
          <>
            <div>
              <div style={{ fontWeight: 700, fontSize: 18 }}>{selected.name} <span style={{ fontWeight: 400, fontSize: 13, color: "#6b7280" }}>({selected.code})</span></div>
            </div>

            {/* Sub-tabs */}
            <div style={{ display: "flex", gap: 4, borderBottom: "1px solid #e5e7eb" }}>
              {(["schema", "upload", "records"] as SubTab[]).map(t => (
                <button key={t}
                  style={{ padding: "6px 14px", border: "none", borderBottom: subTab === t ? "2px solid #2563eb" : "2px solid transparent", background: "none", cursor: "pointer", fontWeight: subTab === t ? 600 : 400, color: subTab === t ? "#2563eb" : "#374151", fontSize: 14 }}
                  onClick={() => setSubTab(t)}
                >
                  {{ schema: "欄位定義", upload: "上傳資料", records: "紀錄查詢" }[t]}
                </button>
              ))}
            </div>

            {/* Schema tab */}
            {subTab === "schema" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {schemaErrors.length > 0 && (
                  <div style={{ background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 6, padding: "10px 14px" }}>
                    {schemaErrors.map((e, i) => (
                      <div key={i} style={{ color: "#dc2626", fontSize: 13 }}>✕ {e}</div>
                    ))}
                  </div>
                )}
                <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#f9fafb" }}>
                      <th style={cell}>欄位名稱 <span style={{ color: "#6b7280", fontWeight: 400, fontSize: 11 }}>(英文/底線)</span></th>
                      <th style={cell}>型別</th>
                      <th style={{ ...cell, textAlign: "center" }}>必填 *</th>
                      <th style={{ ...cell, textAlign: "center" }}>識別鍵 🔑</th>
                      <th style={cell}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {editFields.map((f, i) => {
                      const nameInvalid = !f.name.trim() || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(f.name.trim());
                      const nameDupe = editFields.some((o, j) => j !== i && o.name.trim() === f.name.trim() && f.name.trim());
                      const inputBorder = (nameInvalid || nameDupe) ? "1px solid #f87171" : "1px solid #d1d5db";
                      return (
                        <tr key={i} style={{ background: (nameInvalid || nameDupe) ? "#fff5f5" : undefined }}>
                          <td style={cell}>
                            <input value={f.name} onChange={e => { updateField(i, "name", e.target.value); setSchemaErrors([]); }}
                              style={{ width: "100%", padding: "3px 6px", border: inputBorder, borderRadius: 4 }}
                              placeholder="field_name" />
                          </td>
                          <td style={cell}>
                            <select value={f.type} onChange={e => updateField(i, "type", e.target.value)}
                              style={{ padding: "3px 6px", border: "1px solid #d1d5db", borderRadius: 4 }}>
                              {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                            </select>
                          </td>
                          <td style={{ ...cell, textAlign: "center" }}>
                            <input type="checkbox" checked={f.required} onChange={e => updateField(i, "required", e.target.checked)} />
                          </td>
                          <td style={{ ...cell, textAlign: "center" }}>
                            <input type="checkbox" checked={f.is_key} onChange={e => updateField(i, "is_key", e.target.checked)} />
                          </td>
                          <td style={cell}>
                            <button style={btn("#ef4444")} onClick={() => setEditFields(prev => prev.filter((_, j) => j !== i))}>移除</button>
                          </td>
                        </tr>
                      );
                    })}
                    {editFields.length === 0 && (
                      <tr><td colSpan={5} style={{ ...cell, textAlign: "center", color: "#9ca3af" }}>尚未定義欄位，請點擊「新增欄位」</td></tr>
                    )}
                  </tbody>
                </table>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <button style={btn("#6b7280")} onClick={addField}>＋ 新增欄位</button>
                  <select value={schemaReasonId} disabled={loadingReasons || editReasons.length === 0}
                    onChange={e => { setSchemaReasonId(e.target.value); setSchemaErrors([]); }}
                    style={{ padding: "5px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                    <option value="">選擇編輯原因</option>
                    {editReasons.map(r => <option key={r.id} value={r.id}>{r.label} ({r.code})</option>)}
                  </select>
                  <button style={btn()} onClick={saveSchema} disabled={schemaSaving}>
                    {schemaSaving ? "儲存中…" : "儲存 Schema"}
                  </button>
                  <span style={{ fontSize: 12, color: "#6b7280" }}>* 必填欄位在 CSV 上傳時若缺少值將報錯；🔑 識別鍵用於去重</span>
                </div>
                {!loadingReasons && editReasons.length === 0 && (
                  <div style={{ fontSize: 12, color: "#d97706" }}>
                    {reasonLoadFailed
                      ? "無法載入編輯原因清單，請稍後再試或聯絡管理者。"
                      : "尚無可用編輯原因，請先由管理者於「編輯原因管理」建立後再儲存 Schema。"}
                  </div>
                )}
              </div>
            )}

            {/* Upload tab */}
            {subTab === "upload" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {(!selected.fields || selected.fields.length === 0) ? (
                  <div style={{ background: "#fffbeb", border: "1px solid #fbbf24", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#92400e" }}>
                    ⚠ 尚未定義欄位 Schema。請先至「欄位定義」tab 建立 Schema 再上傳 CSV。
                  </div>
                ) : (
                  <div>
                    <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 6 }}>
                      CSV 欄位對應（<span style={{ color: "#dc2626" }}>*</span> 必填，🔑 識別鍵）：
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {selected.fields.map(f => {
                        const isRequired = f.required;
                        const isKey = f.is_key;
                        const bg = isKey ? "#dbeafe" : isRequired ? "#fef2f2" : "#f3f4f6";
                        const border = isKey ? "#93c5fd" : isRequired ? "#fca5a5" : "#d1d5db";
                        return (
                          <span key={f.name} style={{ padding: "2px 8px", background: bg, border: `1px solid ${border}`, borderRadius: 12, fontSize: 12 }}>
                            {isRequired && <span style={{ color: "#dc2626", marginRight: 2 }}>*</span>}
                            {f.name}
                            {isKey ? " 🔑" : ""}
                            <span style={{ marginLeft: 4, color: "#9ca3af", fontSize: 10 }}>{f.type}</span>
                          </span>
                        );
                      })}
                    </div>
                    {selected.fields.some(f => f.required) && (
                      <div style={{ marginTop: 6, fontSize: 12, color: "#dc2626" }}>
                        <span style={{ color: "#dc2626" }}>*</span> 標示欄位為必填，CSV 中對應欄若為空值將計為錯誤
                      </div>
                    )}
                  </div>
                )}

                <div ref={dropRef}
                  onDrop={onDrop} onDragOver={e => e.preventDefault()}
                  onClick={() => fileInputRef.current?.click()}
                  style={{ border: "2px dashed #d1d5db", borderRadius: 8, padding: "32px 16px", textAlign: "center", cursor: "pointer", background: uploadFile ? "#f0fdf4" : "#fafafa" }}
                >
                  <input ref={fileInputRef} type="file" accept=".csv" style={{ display: "none" }}
                    onChange={e => setUploadFile(e.target.files?.[0] ?? null)} />
                  {uploadFile
                    ? <div style={{ color: "#16a34a", fontWeight: 500 }}>📄 {uploadFile.name}</div>
                    : <div style={{ color: "#6b7280" }}>拖放 CSV 或點擊選擇檔案</div>
                  }
                </div>

                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
                  <input type="checkbox" checked={allowDup} onChange={e => setAllowDup(e.target.checked)} />
                  允許重複匯入（相同識別鍵）
                </label>

                <button style={btn()} onClick={uploadCsv}
                  disabled={!uploadFile || uploading || !selected.fields || selected.fields.length === 0}>
                  {uploading ? "上傳中…" : "開始上傳"}
                </button>

                {uploadResult && (
                  <div style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 6, padding: 12 }}>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>上傳結果</div>
                    <div style={{ fontSize: 14, display: "flex", gap: 16 }}>
                      <span style={{ color: "#16a34a" }}>✔ 匯入：{uploadResult.imported}</span>
                      <span style={{ color: "#d97706" }}>⊘ 跳過：{uploadResult.skipped}</span>
                      <span style={{ color: uploadResult.errors.length > 0 ? "#dc2626" : "#6b7280" }}>✕ 錯誤：{uploadResult.errors.length}</span>
                    </div>
                    {uploadResult.errors.length > 0 && (
                      <ul style={{ marginTop: 8, fontSize: 12, color: "#dc2626" }}>
                        {uploadResult.errors.map(e => (
                          <li key={e.row}>第 {e.row} 列：{e.errors.join("、")}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Records tab */}
            {subTab === "records" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, color: "#6b7280" }}>共 {total} 筆</span>
                  <button style={btn("#6b7280")} onClick={() => loadRecords(page)}>重新整理</button>
                </div>

                <div style={{ overflowX: "auto" }}>
                  <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                    <thead>
                      <tr style={{ background: "#f9fafb" }}>
                        <th style={cell}>識別鍵</th>
                        {columns.map(c => <th key={c} style={cell}>{c}</th>)}
                        <th style={cell}>建立時間</th>
                        <th style={cell}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.map(r => (
                        <tr key={r.id}>
                          <td style={cell}>{r.lot_no_raw}</td>
                          {columns.map(c => <td key={c} style={cell}>{String(r.data[c] ?? "")}</td>)}
                          <td style={cell}>{r.created_at?.slice(0, 19).replace("T", " ")}</td>
                          <td style={cell}>
                            <div style={{ display: "flex", gap: 6 }}>
                              <button style={btn()} onClick={() => setEditingRecord(r)}>編輯</button>
                              <button style={btn("#ef4444")} onClick={() => deleteRecord(r.id)}>刪除</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {records.length === 0 && (
                        <tr><td colSpan={columns.length + 3} style={{ ...cell, textAlign: "center", color: "#6b7280" }}>無紀錄</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {total > PAGE_SIZE && (
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <button style={btn("#6b7280")} disabled={page === 1} onClick={() => setPage(p => p - 1)}>上一頁</button>
                    <span style={{ fontSize: 13 }}>{page} / {Math.ceil(total / PAGE_SIZE)}</span>
                    <button style={btn("#6b7280")} disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => setPage(p => p + 1)}>下一頁</button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
      {selected && editingRecord ? (
        <EditRecordModal
          tableCode={selected.code}
          fields={selected.fields ?? EMPTY_FIELDS}
          record={editingRecord}
          onClose={() => setEditingRecord(null)}
          onSaved={() => loadRecords(page)}
        />
      ) : null}
    </div>
  );
}
