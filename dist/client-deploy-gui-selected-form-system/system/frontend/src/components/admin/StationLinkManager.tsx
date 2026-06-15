import { useCallback, useEffect, useState } from 'react'
import { getApiKeyHeaderName, getApiKeyValue } from '../../services/auth'
import { useToast } from '../common/ToastContext'

interface StationRow {
  id: string
  code: string
  name: string
}

interface StationLinkRow {
  id: string
  from_station_id: string
  to_station_id: string
  link_type: string
  sort_order: number
  from_code?: string | null
  to_code?: string | null
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

export function StationLinkManager({ showToast: _showToast }: { showToast?: (m: string, t?: string) => void } = {}) {
  const { addToast } = useToast()
  const toast = (msg: string, type = 'info') => { _showToast?.(msg, type); addToast(msg, type) }

  const [stations, setStations] = useState<StationRow[]>([])
  const [links, setLinks] = useState<StationLinkRow[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const [fromStationCode, setFromStationCode] = useState('')
  const [toStationCode, setToStationCode] = useState('')
  const [linkType, setLinkType] = useState('sequential')
  const [sortOrder, setSortOrder] = useState(0)

  const loadStations = useCallback(async () => {
    try {
      const data: StationRow[] = await apiFetch('/api/forms')
      setStations(data)
      setFromStationCode(prev => prev || data[0]?.code || '')
      setToStationCode(prev => prev || data[1]?.code || data[0]?.code || '')
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }, [])

  const loadLinks = useCallback(async () => {
    setLoading(true)
    try {
      const data: StationLinkRow[] = await apiFetch('/api/station-links')
      setLinks(data)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadStations() }, [loadStations])
  useEffect(() => { void loadLinks() }, [loadLinks])

  async function handleCreate() {
    const fromCode = fromStationCode.trim()
    const toCode = toStationCode.trim()
    const type = linkType.trim() || 'sequential'
    if (!fromCode) { toast('From station is required', 'error'); return }
    if (!toCode) { toast('To station is required', 'error'); return }

    setSaving(true)
    try {
      await apiFetch('/api/station-links', {
        method: 'POST',
        body: JSON.stringify({
          from_station_code: fromCode,
          to_station_code: toCode,
          link_type: type,
          sort_order: sortOrder,
        }),
      })
      toast('Station link created', 'success')
      setLinkType('sequential')
      setSortOrder(0)
      await loadLinks()
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this station link?')) return
    try {
      await apiFetch(`/api/station-links/${id}`, { method: 'DELETE' })
      toast('Station link deleted', 'success')
      await loadLinks()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <div style={{ padding: 8 }}>
      <div style={{ marginBottom: 12 }}>
        <strong style={{ fontSize: 15 }}>Station Links</strong>
        <div style={{ fontSize: 12, color: '#777', marginTop: 2 }}>Configure station-to-station navigation links.</div>
      </div>

      <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 12, marginBottom: 12, background: '#f9f9f9' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1fr) minmax(160px, 1fr) minmax(140px, 1fr) 120px', gap: 8, marginBottom: 8 }}>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>From station</label>
            <select className="form-control form-control-sm" value={fromStationCode}
              onChange={e => setFromStationCode(e.target.value)}>
              <option value="">Select station</option>
              {stations.map(st => (
                <option key={st.id} value={st.code}>{st.code} - {st.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>To station</label>
            <select className="form-control form-control-sm" value={toStationCode}
              onChange={e => setToStationCode(e.target.value)}>
              <option value="">Select station</option>
              {stations.map(st => (
                <option key={st.id} value={st.code}>{st.code} - {st.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>link_type</label>
            <input className="form-control form-control-sm" value={linkType}
              onChange={e => setLinkType(e.target.value)} placeholder="sequential" />
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>sort_order</label>
            <input className="form-control form-control-sm" type="number" value={sortOrder}
              onChange={e => setSortOrder(Number(e.target.value))} />
          </div>
        </div>
        <button className="btn btn-sm btn-primary" disabled={saving || !fromStationCode || !toStationCode} onClick={handleCreate}>
          {saving ? 'Saving...' : '+ Add link'}
        </button>
      </div>

      {loading ? (
        <div style={{ color: '#888', fontSize: 13 }}>Loading...</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              {['link', 'link_type', 'sort_order', ''].map(h => (
                <th key={h} style={{ padding: '6px 8px', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {links.map(link => (
              <tr key={link.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  {link.from_code ?? link.from_station_id} {'->'} {link.to_code ?? link.to_station_id}
                </td>
                <td style={{ padding: '6px 8px' }}>{link.link_type}</td>
                <td style={{ padding: '6px 8px' }}>{link.sort_order}</td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  <button className="btn btn-sm btn-danger" onClick={() => void handleDelete(link.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {links.length === 0 && (
              <tr>
                <td colSpan={4} style={{ color: '#999', fontSize: 12, padding: '10px 8px' }}>No station links found.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
