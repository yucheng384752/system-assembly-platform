import { useCallback, useEffect, useMemo, useState } from 'react'
import { getApiKeyHeaderName, getApiKeyValue } from '../../services/auth'
import { useToast } from '../common/ToastContext'

type RuleType = 'required' | 'regex' | 'range' | 'enum'

interface StationRow {
  id: string
  code: string
  name: string
}

interface ValidationRuleRow {
  id: string
  tenant_id: string
  station_id: string | null
  field_name: string
  rule_type: RuleType | string
  rule_config: Record<string, unknown> | null
  is_active: boolean
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

function prettyJson(value: unknown) {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return String(value ?? '')
  }
}

export function ValidationRuleManager({ showToast: _showToast }: { showToast?: (m: string, t?: string) => void } = {}) {
  const { addToast } = useToast()
  const toast = (msg: string, type = 'info') => { _showToast?.(msg, type); addToast(msg, type) }

  const [stations, setStations] = useState<StationRow[]>([])
  const [rules, setRules] = useState<ValidationRuleRow[]>([])
  const [selectedStationId, setSelectedStationId] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const [newStationId, setNewStationId] = useState('')
  const [newFieldName, setNewFieldName] = useState('')
  const [newRuleType, setNewRuleType] = useState<RuleType>('required')
  const [newRuleConfig, setNewRuleConfig] = useState('{}')

  const stationById = useMemo(() => {
    const map = new Map<string, StationRow>()
    stations.forEach(st => map.set(st.id, st))
    return map
  }, [stations])

  const loadStations = useCallback(async () => {
    try {
      const data: StationRow[] = await apiFetch('/api/forms')
      setStations(data)
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }, [])

  const loadRules = useCallback(async () => {
    setLoading(true)
    try {
      const qs = selectedStationId ? `?station_id=${encodeURIComponent(selectedStationId)}` : ''
      const data: ValidationRuleRow[] = await apiFetch(`/api/rules${qs}`)
      setRules(data)
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [selectedStationId])

  useEffect(() => { void loadStations() }, [loadStations])
  useEffect(() => { void loadRules() }, [loadRules])

  async function handleCreate() {
    const fieldName = newFieldName.trim()
    if (!fieldName) { toast('field_name is required', 'error'); return }

    let ruleConfig: Record<string, unknown>
    try {
      ruleConfig = JSON.parse(newRuleConfig || '{}')
      if (ruleConfig === null || Array.isArray(ruleConfig) || typeof ruleConfig !== 'object') {
        toast('rule_config must be a JSON object', 'error')
        return
      }
    } catch {
      toast('rule_config must be valid JSON', 'error')
      return
    }

    setSaving(true)
    try {
      await apiFetch('/api/rules', {
        method: 'POST',
        body: JSON.stringify({
          station_id: newStationId || undefined,
          field_name: fieldName,
          rule_type: newRuleType,
          rule_config: ruleConfig,
          is_active: true,
        }),
      })
      toast('Validation rule created', 'success')
      setNewFieldName('')
      setNewRuleType('required')
      setNewRuleConfig('{}')
      await loadRules()
    } catch (e: any) {
      toast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle(id: string) {
    try {
      await apiFetch(`/api/rules/${id}/toggle`, { method: 'PUT' })
      toast('Validation rule updated', 'success')
      await loadRules()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this validation rule?')) return
    try {
      await apiFetch(`/api/rules/${id}`, { method: 'DELETE' })
      toast('Validation rule deleted', 'success')
      await loadRules()
    } catch (e: any) {
      toast(e.message, 'error')
    }
  }

  return (
    <div style={{ padding: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, marginBottom: 12 }}>
        <div>
          <strong style={{ fontSize: 15 }}>Validation Rules</strong>
          <div style={{ fontSize: 12, color: '#777', marginTop: 2 }}>Manage field validation rules by station.</div>
        </div>
        <div style={{ minWidth: 220 }}>
          <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Station filter</label>
          <select className="form-control form-control-sm" value={selectedStationId}
            onChange={e => setSelectedStationId(e.target.value)}>
            <option value="">All stations</option>
            {stations.map(st => (
              <option key={st.id} value={st.id}>{st.code} - {st.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 12, marginBottom: 12, background: '#f9f9f9' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1fr) minmax(160px, 1fr) 140px', gap: 8, marginBottom: 8 }}>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Station</label>
            <select className="form-control form-control-sm" value={newStationId}
              onChange={e => setNewStationId(e.target.value)}>
              <option value="">No station</option>
              {stations.map(st => (
                <option key={st.id} value={st.id}>{st.code} - {st.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>field_name</label>
            <input className="form-control form-control-sm" value={newFieldName}
              onChange={e => setNewFieldName(e.target.value)} placeholder="field_name" />
          </div>
          <div>
            <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>rule_type</label>
            <select className="form-control form-control-sm" value={newRuleType}
              onChange={e => setNewRuleType(e.target.value as RuleType)}>
              <option value="required">required</option>
              <option value="regex">regex</option>
              <option value="range">range</option>
              <option value="enum">enum</option>
            </select>
          </div>
        </div>
        <div style={{ marginBottom: 8 }}>
          <label style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>rule_config</label>
          <textarea className="form-control form-control-sm" rows={3} value={newRuleConfig}
            onChange={e => setNewRuleConfig(e.target.value)} style={{ fontFamily: 'monospace', fontSize: 12 }} />
        </div>
        <button className="btn btn-sm btn-primary" disabled={saving} onClick={handleCreate}>
          {saving ? 'Saving...' : '+ Add rule'}
        </button>
      </div>

      {loading ? (
        <div style={{ color: '#888', fontSize: 13 }}>Loading...</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f0f0f0' }}>
              {['station code', 'field_name', 'rule_type', 'rule_config', 'is_active', 'actions'].map(h => (
                <th key={h} style={{ padding: '6px 8px', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rules.map(rule => (
              <tr key={rule.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  {rule.station_id ? stationById.get(rule.station_id)?.code ?? rule.station_id : '-'}
                </td>
                <td style={{ padding: '6px 8px' }}>{rule.field_name}</td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{rule.rule_type}</td>
                <td style={{ padding: '6px 8px' }}>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 11 }}>{prettyJson(rule.rule_config)}</pre>
                </td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  <span style={{
                    display: 'inline-block', padding: '2px 8px', borderRadius: 12, fontSize: 11,
                    color: '#fff', background: rule.is_active ? '#188038' : '#c5221f',
                  }}>
                    {rule.is_active ? 'active' : 'inactive'}
                  </span>
                </td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  <button className="btn btn-sm btn-secondary" onClick={() => void handleToggle(rule.id)}
                    style={{ marginRight: 6 }}>
                    Toggle
                  </button>
                  <button className="btn btn-sm btn-danger" onClick={() => void handleDelete(rule.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: '#999', fontSize: 12, padding: '10px 8px' }}>No validation rules found.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
