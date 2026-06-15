import { useCallback, useEffect, useState } from 'react'
import { getApiKeyHeaderName, getApiKeyValue } from '../../services/auth'
import { useToast } from '../common/ToastContext'

type DataType = 'string' | 'integer' | 'decimal' | 'date'

interface StationRow {
  id: string
  code: string
  name: string
}

interface AnalyticsMappingRow {
  id: string
  station_id: string
  source_path: string
  output_column: string
  output_order: number
  data_type: DataType | string | null
  null_if_missing: boolean
}

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

export function AnalyticsMappingManager({ showToast: _showToast }: { showToast?: (m: string, t?: string) => void } = {}) {
  const { addToast } = useToast()
  const toast = (msg: string, type = 'info') => { _showToast?.(msg, type); addToast(msg, type) }

  const [stations, setStations] = useState<StationRow[]>([])
  const [mappings, setMappings] = useState<AnalyticsMappingRow[]>([])
  const [selectedStationId, setSelectedStationId] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const [newSourcePath, setNewSourcePath] = useState('')
  const [newOutputColumn, setNewOutputColumn] = useState('')
  const [newOutputOrder, setNewOutputOrder] = useState(0)
  const [newDataType, setNewDataType] = useState<DataType>('string')

  const loadStations = useCallback(async () => {
    try {
      const data: StationRow[] = await apiFetch('/api/forms')
      setStations(data)
      setSelectedStationId(prev => prev || data[0]?.id || '')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }, [])

  const loadMappings = useCallback(async () => {
    if (!selectedStationId) {
      setMappings([])
      return
    }

    setLoading(true)
    try {
      const data: AnalyticsMappingRow[] = await apiFetch(`/api/analytics-mappings?station_id=${encodeURIComponent(selectedStationId)}`)
      setMappings(data)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [selectedStationId])

  useEffect(() => { void loadStations() }, [loadStations])
  useEffect(() => { void loadMappings() }, [loadMappings])

  async function handleCreate() {
    const sourcePath = newSourcePath.trim()
    const outputColumn = newOutputColumn.trim()
    if (!selectedStationId) { toast('Station is required', 'error'); return }
    if (!sourcePath) { toast('source_path is required', 'error'); return }
    if (!outputColumn) { toast('output_column is required', 'error'); return }

    setSaving(true)
    try {
      await apiFetch('/api/analytics-mappings', {
        method: 'POST',
        body: JSON.stringify({
          station_id: selectedStationId,
          source_path: sourcePath,
          output_column: outputColumn,
          output_order: newOutputOrder,
          data_type: newDataType,
          null_if_missing: true,
        }),
      })
      toast('Analytics mapping created', 'success')
      setNewSourcePath('')
      setNewOutputColumn('')
      setNewOutputOrder(0)
      setNewDataType('string')
      await loadMappings()
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleUpdate(id: string, patch: Partial<Pick<AnalyticsMappingRow, 'output_order' | 'data_type' | 'null_if_missing'>>) {
    try {
      await apiFetch(`/api/analytics-mappings/${id}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      toast('Analytics mapping updated', 'success')
      await loadMappings()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this analytics mapping?')) return
    try {
      await apiFetch(`/api/analytics-mappings/${id}`, { method: 'DELETE' })
      toast('Analytics mapping deleted', 'success')
      await loadMappings()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <div style={{ padding: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, marginBottom: 12 }}>
        <div>
          <strong style={{ fontSize: 15 }}>Analytics Mappings</strong>
          <div style={{ fontSize: 12, color: '#777', marginTop: 2 }}>Map station fields into analytics output columns.</div>
        </div>
        <div style={{ minWidth: 260 }}>
          <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Station</label>
          <select className="form-control form-control-sm" value={selectedStationId}
            onChange={e => setSelectedStationId(e.target.value)}>
            <option value="">Select station</option>
            {stations.map(st => (
              <option key={st.id} value={st.id}>{st.code} - {st.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 12, marginBottom: 12, background: '#f9f9f9' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1fr) minmax(160px, 1fr) 120px 140px', gap: 8, marginBottom: 8 }}>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>source_path</label>
            <input className="form-control form-control-sm" value={newSourcePath}
              onChange={e => setNewSourcePath(e.target.value)} placeholder="payload.field" />
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>output_column</label>
            <input className="form-control form-control-sm" value={newOutputColumn}
              onChange={e => setNewOutputColumn(e.target.value)} placeholder="column_name" />
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>output_order</label>
            <input className="form-control form-control-sm" type="number" value={newOutputOrder}
              onChange={e => setNewOutputOrder(Number(e.target.value))} />
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>data_type</label>
            <select className="form-control form-control-sm" value={newDataType}
              onChange={e => setNewDataType(e.target.value as DataType)}>
              <option value="string">string</option>
              <option value="integer">integer</option>
              <option value="decimal">decimal</option>
              <option value="date">date</option>
            </select>
          </div>
        </div>
        <button className="btn btn-sm btn-primary" disabled={saving || !selectedStationId} onClick={handleCreate}>
          {saving ? 'Saving...' : '+ Add mapping'}
        </button>
      </div>

      {loading ? (
        <div style={{ color: '#888', fontSize: 13 }}>Loading...</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              {['source_path', 'output_column', 'output_order', 'data_type', 'null_if_missing', ''].map(h => (
                <th key={h} style={{ padding: '6px 8px', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mappings.map(mapping => (
              <tr key={mapping.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '6px 8px' }}>{mapping.source_path}</td>
                <td style={{ padding: '6px 8px' }}>{mapping.output_column}</td>
                <td style={{ padding: '6px 8px', width: 120 }}>
                  <input type="number" value={mapping.output_order}
                    onChange={e => void handleUpdate(mapping.id, { output_order: Number(e.target.value) })}
                    style={{ width: 90, fontSize: 12, padding: '3px 5px', border: '1px solid #ccc', borderRadius: 3 }} />
                </td>
                <td style={{ padding: '6px 8px', width: 140 }}>
                  <select value={mapping.data_type ?? 'string'}
                    onChange={e => void handleUpdate(mapping.id, { data_type: e.target.value })}
                    style={{ fontSize: 12, padding: '3px 5px', border: '1px solid #ccc', borderRadius: 3 }}>
                    <option value="string">string</option>
                    <option value="integer">integer</option>
                    <option value="decimal">decimal</option>
                    <option value="date">date</option>
                  </select>
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'center', width: 130 }}>
                  <input type="checkbox" checked={mapping.null_if_missing}
                    onChange={e => void handleUpdate(mapping.id, { null_if_missing: e.target.checked })} />
                </td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  <button className="btn btn-sm btn-danger" onClick={() => void handleDelete(mapping.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {mappings.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: '#999', fontSize: 12, padding: '10px 8px' }}>No analytics mappings found.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
