import { useCallback, useEffect, useState } from 'react'
import { getApiKeyHeaderName, getApiKeyValue } from '../services/auth'

// ── types ────────────────────────────────────────────────────────────────────

interface FieldDef { name: string; type: string; label: string }

interface StationRow {
  id: string; code: string; name: string
  schema_version: number | null; fields: FieldDef[] | null
}

interface RecordRow {
  id: string; lot_no_raw: string; data: Record<string, unknown>; created_at: string | null
}

interface RecordsResp { total: number; page: number; page_size: number; records: RecordRow[] }

// ── API helpers ───────────────────────────────────────────────────────────────

function apiHeaders() {
  return { [getApiKeyHeaderName()]: getApiKeyValue() }
}

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: apiHeaders() })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as any)?.detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}

// ── component ─────────────────────────────────────────────────────────────────

const PAGE_SIZES = [20, 50, 100]

export function QueryPage() {
  const [stations, setStations] = useState<StationRow[]>([])
  const [stationsLoading, setStationsLoading] = useState(true)
  const [stationErr, setStationErr] = useState('')

  const [selectedCode, setSelectedCode] = useState('')
  const [lotFilter, setLotFilter] = useState('')
  const [pageSize, setPageSize] = useState(50)
  const [page, setPage] = useState(1)

  const [resp, setResp] = useState<RecordsResp | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  // fetch station list on mount
  useEffect(() => {
    apiFetch<StationRow[]>('/api/forms')
      .then(data => { setStations(data); if (data.length > 0) setSelectedCode(data[0].code) })
      .catch(e => setStationErr(e.message))
      .finally(() => setStationsLoading(false))
  }, [])

  const selectedStation = stations.find(s => s.code === selectedCode)

  const fetchRecords = useCallback(async (code: string, pg: number, ps: number) => {
    if (!code) return
    setLoading(true); setErr('')
    try {
      const data = await apiFetch<RecordsResp>(`/api/forms/${code}/records?page=${pg}&page_size=${ps}`)
      setResp(data)
    } catch (e: any) {
      setErr(e.message); setResp(null)
    } finally {
      setLoading(false)
    }
  }, [])

  // re-fetch when station / page / size changes
  useEffect(() => {
    if (selectedCode) { setPage(1); void fetchRecords(selectedCode, 1, pageSize) }
  }, [selectedCode, pageSize])

  useEffect(() => {
    if (selectedCode) void fetchRecords(selectedCode, page, pageSize)
  }, [page])

  const columns: FieldDef[] = selectedStation?.fields ?? []

  const filteredRecords = (resp?.records ?? []).filter(r =>
    !lotFilter.trim() || r.lot_no_raw.toLowerCase().includes(lotFilter.trim().toLowerCase())
  )

  const totalPages = resp ? Math.max(1, Math.ceil(resp.total / pageSize)) : 1

  function handleStationChange(code: string) {
    setSelectedCode(code); setPage(1); setLotFilter(''); setResp(null)
  }

  // ── CSV export ────────────────────────────────────────────────────────────
  function exportCsv() {
    if (!resp) return
    const headers = ['lot_no_raw', ...columns.map(c => c.name), 'created_at']
    const rows = filteredRecords.map(r => [
      r.lot_no_raw,
      ...columns.map(c => String((r.data as any)[c.name] ?? '')),
      r.created_at ?? '',
    ])
    const csv = [headers, ...rows].map(row =>
      row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')
    ).join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${selectedCode}_records_p${page}.csv`
    a.click()
  }

  // ── render ────────────────────────────────────────────────────────────────
  if (stationsLoading) return <div style={{ padding: 24, color: '#888' }}>載入表單列表中…</div>
  if (stationErr) return <div style={{ padding: 24, color: '#c00' }}>載入失敗：{stationErr}</div>
  if (stations.length === 0) return (
    <div style={{ padding: 24, color: '#888' }}>
      尚無表單類型。請先到「管理 → 表單管理」建立表單並定義 Schema。
    </div>
  )

  return (
    <div style={{ padding: '16px 20px' }}>

      {/* toolbar */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 13, whiteSpace: 'nowrap' }}>表單：</label>
          <select value={selectedCode} onChange={e => handleStationChange(e.target.value)}
            style={{ fontSize: 13, padding: '4px 8px', border: '1px solid #ccc', borderRadius: 4 }}>
            {stations.map(s => (
              <option key={s.code} value={s.code}>{s.code} — {s.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 13, whiteSpace: 'nowrap' }}>Lot No：</label>
          <input value={lotFilter} onChange={e => setLotFilter(e.target.value)}
            placeholder="篩選 lot no…"
            style={{ fontSize: 13, padding: '4px 8px', border: '1px solid #ccc', borderRadius: 4, width: 160 }} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 13, whiteSpace: 'nowrap' }}>每頁：</label>
          <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
            style={{ fontSize: 13, padding: '4px 6px', border: '1px solid #ccc', borderRadius: 4 }}>
            {PAGE_SIZES.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

        <button onClick={exportCsv} disabled={!resp || filteredRecords.length === 0}
          style={{
            fontSize: 13, padding: '4px 12px', border: '1px solid #4285f4', borderRadius: 4,
            background: '#fff', color: '#4285f4', cursor: 'pointer'
          }}>
          ↓ 匯出 CSV
        </button>

        <div style={{ marginLeft: 'auto', fontSize: 12, color: '#666' }}>
          {resp != null && `共 ${resp.total} 筆`}
        </div>
      </div>

      {/* schema info */}
      {selectedStation && !selectedStation.fields && (
        <div style={{ color: '#c60', fontSize: 12, marginBottom: 8 }}>
          ⚠ 此表單尚未設定 Schema，欄位顯示可能不完整。
        </div>
      )}

      {/* table */}
      {loading ? (
        <div style={{ color: '#888', padding: '24px 0', textAlign: 'center' }}>載入中…</div>
      ) : err ? (
        <div style={{ color: '#c00', padding: '24px 0' }}>查詢失敗：{err}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#f0f0f0', position: 'sticky', top: 0 }}>
                <th style={thStyle}>Lot No</th>
                {columns.map(c => (
                  <th key={c.name} style={thStyle}>{c.label || c.name}</th>
                ))}
                {columns.length === 0 && <th style={thStyle}>Data</th>}
                <th style={thStyle}>建立時間</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.length === 0 ? (
                <tr><td colSpan={columns.length + 2}
                  style={{ padding: '24px', textAlign: 'center', color: '#999' }}>
                  無資料
                </td></tr>
              ) : filteredRecords.map(r => (
                <tr key={r.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={tdStyle}>{r.lot_no_raw}</td>
                  {columns.length > 0
                    ? columns.map(c => (
                        <td key={c.name} style={tdStyle}>
                          {String((r.data as any)[c.name] ?? '')}
                        </td>
                      ))
                    : <td style={tdStyle}>{JSON.stringify(r.data)}</td>
                  }
                  <td style={{ ...tdStyle, color: '#888', whiteSpace: 'nowrap' }}>
                    {r.created_at ? r.created_at.slice(0, 16).replace('T', ' ') : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* pagination */}
      {resp && resp.total > pageSize && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, fontSize: 13 }}>
          <button onClick={() => setPage(1)} disabled={page === 1} style={pageBtnStyle}>《</button>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} style={pageBtnStyle}>‹</button>
          <span style={{ color: '#555' }}>第 {page} / {totalPages} 頁</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={pageBtnStyle}>›</button>
          <button onClick={() => setPage(totalPages)} disabled={page === totalPages} style={pageBtnStyle}>》</button>
        </div>
      )}
    </div>
  )
}

const thStyle: React.CSSProperties = {
  padding: '7px 10px', textAlign: 'left', fontWeight: 500,
  borderBottom: '2px solid #ddd', whiteSpace: 'nowrap',
}
const tdStyle: React.CSSProperties = {
  padding: '5px 10px', maxWidth: 200, overflow: 'hidden',
  textOverflow: 'ellipsis', whiteSpace: 'nowrap',
}
const pageBtnStyle: React.CSSProperties = {
  padding: '3px 10px', border: '1px solid #ccc', borderRadius: 4,
  background: '#fff', cursor: 'pointer',
}
