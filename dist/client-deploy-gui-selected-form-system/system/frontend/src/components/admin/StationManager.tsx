import { useCallback, useEffect, useState } from 'react'
import { getApiKeyHeaderName, getApiKeyValue } from '../../services/auth'
import { useToast } from '../common/ToastContext'

// ── types ────────────────────────────────────────────────────────────────────

type FieldType = 'string' | 'integer' | 'decimal' | 'date' | 'boolean'

interface FieldDef {
  name: string
  type: FieldType
  label: string
  required: boolean
  is_key: boolean
}

interface StationRow {
  id: string
  code: string
  name: string
  sort_order: number
  schema_version: number | null
  fields: FieldDef[] | null
}

// ── API helpers ───────────────────────────────────────────────────────────────

function apiHeaders() {
  return {
    'Content-Type': 'application/json',
    [getApiKeyHeaderName()]: getApiKeyValue(),
  }
}

async function apiFetch(path: string, init?: RequestInit) {
  const res = await fetch(path, { ...init, headers: { ...apiHeaders(), ...(init?.headers ?? {}) } })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as any)?.detail ?? `HTTP ${res.status}`)
  }
  return res.status === 204 ? null : res.json()
}

function blankField(): FieldDef {
  return { name: '', type: 'string', label: '', required: false, is_key: false }
}

// ── component ─────────────────────────────────────────────────────────────────

export function StationManager({ showToast: _showToast }: { showToast?: (m: string, t?: string) => void } = {}) {
  const { addToast } = useToast()
  const toast = (msg: string, type = 'info') => { _showToast?.(msg, type); addToast(msg, type) }

  const [stations, setStations] = useState<StationRow[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  const [creating, setCreating] = useState(false)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [newOrder, setNewOrder] = useState(0)
  const [saving, setSaving] = useState(false)

  const [editFields, setEditFields] = useState<FieldDef[]>([])
  const [schemaSaving, setSchemaSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data: StationRow[] = await apiFetch('/api/forms')
      setStations(data)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  function selectStation(code: string) {
    const st = stations.find(s => s.code === code)
    if (!st) return
    setSelected(code)
    setEditFields(st.fields ? st.fields.map(f => ({ ...f })) : [])
  }

  async function handleCreate() {
    const code = newCode.trim().toUpperCase()
    const name = newName.trim() || code
    if (!code) { toast('請輸入表單代碼', 'error'); return }
    setSaving(true)
    try {
      await apiFetch('/api/forms', {
        method: 'POST',
        body: JSON.stringify({ code, name, sort_order: newOrder }),
      })
      toast(`已建立表單 ${code}`, 'success')
      setCreating(false); setNewCode(''); setNewName(''); setNewOrder(0)
      await load()
      selectStation(code)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleSaveSchema() {
    if (!selected) return
    const invalid = editFields.find(f => !f.name.trim())
    if (invalid !== undefined) { toast('所有欄位名稱不可為空', 'error'); return }
    setSchemaSaving(true)
    try {
      await apiFetch(`/api/forms/${selected}/schema`, {
        method: 'PUT',
        body: JSON.stringify({ fields: editFields.map(f => ({ ...f, name: f.name.trim() })) }),
      })
      toast('Schema 已儲存', 'success')
      await load()
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSchemaSaving(false)
    }
  }

  async function handleDelete(code: string) {
    if (!window.confirm(`確定要刪除表單 ${code}？此操作會刪除所有相關資料。`)) return
    try {
      await apiFetch(`/api/forms/${code}`, { method: 'DELETE' })
      toast(`已刪除 ${code}`, 'success')
      if (selected === code) setSelected(null)
      await load()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  function updateField(idx: number, patch: Partial<FieldDef>) {
    setEditFields(prev => prev.map((f, i) => i === idx ? { ...f, ...patch } : f))
  }

  function moveField(idx: number, dir: -1 | 1) {
    const next = [...editFields]
    const target = idx + dir
    if (target < 0 || target >= next.length) return
    ;[next[idx], next[target]] = [next[target], next[idx]]
    setEditFields(next)
  }

  const selectedStation = stations.find(s => s.code === selected)

  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start', padding: 8 }}>

      {/* station list */}
      <div style={{ minWidth: 220, flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong>表單類型</strong>
          <button className="btn btn-sm btn-primary" onClick={() => setCreating(c => !c)}>
            {creating ? '取消' : '+ 新增'}
          </button>
        </div>

        {creating && (
          <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 12, marginBottom: 8, background: '#f9f9f9' }}>
            <div style={{ marginBottom: 6 }}>
              <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>代碼（英文大寫）</label>
              <input className="form-control form-control-sm" value={newCode}
                onChange={e => setNewCode(e.target.value.toUpperCase())} placeholder="ENTRY" />
            </div>
            <div style={{ marginBottom: 6 }}>
              <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>名稱</label>
              <input className="form-control form-control-sm" value={newName}
                onChange={e => setNewName(e.target.value)} placeholder="入料記錄" />
            </div>
            <div style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>排序</label>
              <input className="form-control form-control-sm" type="number" value={newOrder}
                onChange={e => setNewOrder(Number(e.target.value))} />
            </div>
            <button className="btn btn-sm btn-success" disabled={saving} onClick={handleCreate}
              style={{ width: '100%' }}>
              {saving ? '建立中…' : '建立'}
            </button>
          </div>
        )}

        {loading ? (
          <div style={{ color: '#888', fontSize: 13 }}>載入中…</div>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {stations.map(st => (
              <li key={st.code}
                onClick={() => selectStation(st.code)}
                style={{
                  padding: '8px 10px', borderRadius: 6, cursor: 'pointer', marginBottom: 4,
                  background: selected === st.code ? '#e8f0fe' : '#f5f5f5',
                  border: selected === st.code ? '1px solid #4285f4' : '1px solid transparent',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{st.code}</div>
                  <div style={{ fontSize: 11, color: '#666' }}>{st.name}</div>
                  <div style={{ fontSize: 10, color: '#999' }}>
                    {st.fields ? `${st.fields.length} 個欄位` : '未設定 Schema'}
                    {st.schema_version != null ? ` · v${st.schema_version}` : ''}
                  </div>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); void handleDelete(st.code) }}
                  title="刪除此表單"
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#c00', fontSize: 15, lineHeight: 1 }}>
                  ✕
                </button>
              </li>
            ))}
            {stations.length === 0 && (
              <li style={{ color: '#999', fontSize: 12, padding: '8px 0' }}>尚無表單類型</li>
            )}
          </ul>
        )}
      </div>

      {/* schema editor */}
      <div style={{ flex: 1 }}>
        {!selectedStation ? (
          <div style={{ color: '#999', paddingTop: 40, textAlign: 'center' }}>
            ← 選取左側表單類型以編輯欄位定義
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div>
                <strong style={{ fontSize: 15 }}>{selectedStation.code} — {selectedStation.name}</strong>
                {selectedStation.schema_version != null && (
                  <span style={{ fontSize: 11, color: '#888', marginLeft: 8 }}>
                    Schema v{selectedStation.schema_version}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-sm btn-secondary"
                  onClick={() => setEditFields(f => [...f, blankField()])}>
                  + 欄位
                </button>
                <button className="btn btn-sm btn-primary" disabled={schemaSaving} onClick={handleSaveSchema}>
                  {schemaSaving ? '儲存中…' : '儲存 Schema'}
                </button>
              </div>
            </div>

            {editFields.length === 0 ? (
              <div style={{ color: '#999', fontSize: 13 }}>
                尚無欄位定義，請點「+ 欄位」新增
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: '#f0f0f0' }}>
                    {['排序', '欄位名稱', '類型', '中文標籤', '必填', 'Key', ''].map(h => (
                      <th key={h} style={{ padding: '6px 8px', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 500 }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {editFields.map((f, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '4px 6px', whiteSpace: 'nowrap' }}>
                        <button onClick={() => moveField(idx, -1)} disabled={idx === 0}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#555', padding: '0 2px' }}>▲</button>
                        <button onClick={() => moveField(idx, 1)} disabled={idx === editFields.length - 1}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#555', padding: '0 2px' }}>▼</button>
                      </td>
                      <td style={{ padding: '4px 6px' }}>
                        <input value={f.name}
                          onChange={e => updateField(idx, { name: e.target.value })}
                          placeholder="field_name"
                          style={{ width: 120, fontSize: 12, padding: '3px 5px', border: '1px solid #ccc', borderRadius: 3 }} />
                      </td>
                      <td style={{ padding: '4px 6px' }}>
                        <select value={f.type}
                          onChange={e => updateField(idx, { type: e.target.value as FieldType })}
                          style={{ fontSize: 12, padding: '3px 5px', border: '1px solid #ccc', borderRadius: 3 }}>
                          <option value="string">string</option>
                          <option value="integer">integer</option>
                          <option value="decimal">decimal</option>
                          <option value="date">date</option>
                          <option value="boolean">boolean</option>
                        </select>
                      </td>
                      <td style={{ padding: '4px 6px' }}>
                        <input value={f.label}
                          onChange={e => updateField(idx, { label: e.target.value })}
                          placeholder="中文標籤"
                          style={{ width: 100, fontSize: 12, padding: '3px 5px', border: '1px solid #ccc', borderRadius: 3 }} />
                      </td>
                      <td style={{ padding: '4px 6px', textAlign: 'center' }}>
                        <input type="checkbox" checked={f.required}
                          onChange={e => updateField(idx, { required: e.target.checked })} />
                      </td>
                      <td style={{ padding: '4px 6px', textAlign: 'center' }}>
                        <input type="checkbox" checked={f.is_key}
                          onChange={e => updateField(idx, { is_key: e.target.checked })} />
                      </td>
                      <td style={{ padding: '4px 6px' }}>
                        <button onClick={() => setEditFields(prev => prev.filter((_, i) => i !== idx))}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#c00', fontSize: 14 }}>
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div style={{ marginTop: 12, fontSize: 11, color: '#888' }}>
              💡 Key 欄位用於識別唯一記錄（防重複上傳）。多個 Key 欄位會組合成複合主鍵。
            </div>
          </>
        )}
      </div>
    </div>
  )
}
