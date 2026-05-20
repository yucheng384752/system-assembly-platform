import { useEffect, useMemo, useState, type KeyboardEventHandler } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../components/common/ToastContext'
import {
  clearAdminApiKeyValue,
  clearAdminUnlockedInSession,
  getAdminApiKeyHeaderName,
  getAdminApiKeyValue,
  isAdminUnlockedInSession,
  setAdminUnlockedInSession,
  setAdminApiKeyValue,
} from '../services/adminAuth'
import { setApiKeyValue } from '../services/auth'
import { clearTenantId, ensureTenantIdWithOptions, getTenantId, setTenantId, TENANT_STORAGE_KEY } from '../services/tenant'
import { getTenantLabelById, writeTenantMap } from '../services/tenantMap'
import { StationManager } from '../components/admin/StationManager'
import { ValidationRuleManager } from '../components/admin/ValidationRuleManager'
import { AnalyticsMappingManager } from '../components/admin/AnalyticsMappingManager'
import { StationLinkManager } from '../components/admin/StationLinkManager'
import './../styles/admin-page.css'

type AdminTab = 'general' | 'stations' | 'validation' | 'analytics' | 'links'

type TenantRow = {
  id: string
  name: string
  code: string
  is_active: boolean
  is_default?: boolean
}

type WhoAmI = {
  is_admin: boolean
  tenant_id?: string | null
  actor_user_id?: string | null
  actor_role?: string | null
  api_key_label?: string | null
}

type BootstrapStatus = {
  auth_mode: string
  auth_api_key_header: string
  auth_protect_prefixes: string[]
  auth_exempt_paths: string[]
  admin_api_key_header: string
  admin_keys_configured: boolean
}

type TenantUserRow = {
  id: string
  tenant_id: string
  tenant_code?: string | null
  username: string
  role: string
  is_active: boolean
  created_at?: string | null
  last_login_at?: string | null
}

function maskKey(raw: string) {
  const v = String(raw || '').trim()
  if (!v) return ''
  if (v.length <= 8) return `${v.slice(0, 2)}…${v.slice(-2)}`
  return `${v.slice(0, 4)}…${v.slice(-4)}`
}

export function AdminPage(props: { onAdminUnlocked?: () => void; onAdminLocked?: () => void } = {}) {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const [activeTab, setActiveTab] = useState<AdminTab>('general')

  const [adminKeyDraft, setAdminKeyDraft] = useState('')
  const [storedAdminKeyMasked, setStoredAdminKeyMasked] = useState(() => maskKey(getAdminApiKeyValue()))
  const [adminKeySaving, setAdminKeySaving] = useState(false)

  const [adminUnlocked, setAdminUnlocked] = useState(() => isAdminUnlockedInSession())

  const hasAdminKey = useMemo(() => Boolean(storedAdminKeyMasked), [storedAdminKeyMasked])

  const [whoami, setWhoami] = useState<WhoAmI | null>(null)
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatus | null>(null)
  const [diagLoading, setDiagLoading] = useState(false)

  const [storedTenantId, setStoredTenantIdState] = useState(() => getTenantId())

  const [tenants, setTenants] = useState<TenantRow[] | null>(null)
  const [loadingTenants, setLoadingTenants] = useState(false)
  const [showInactiveTenants, setShowInactiveTenants] = useState(false)

  const [createTenantName, setCreateTenantName] = useState('')
  const [createTenantCode, setCreateTenantCode] = useState('')
  const [createTenantDefault, setCreateTenantDefault] = useState(false)
  const [createTenantLoading, setCreateTenantLoading] = useState(false)

  const hasAnyActiveTenant = useMemo(() => {
    return (tenants || []).some((t) => Boolean(t?.is_active))
  }, [tenants])

  const storedTenantLabel = useMemo(() => {
    if (!storedTenantId) return ''
    const fromList = tenants?.find((t) => t?.id === storedTenantId)
    if (fromList?.code) return fromList.code
    return getTenantLabelById(storedTenantId)
  }, [storedTenantId, tenants])

  const whoamiTenantLabel = useMemo(() => {
    const id = String(whoami?.tenant_id || '').trim()
    if (!id) return ''
    const fromList = tenants?.find((t) => t?.id === id)
    if (fromList?.code) return fromList.code
    return getTenantLabelById(id)
  }, [whoami?.tenant_id, tenants])

  const handleAdminKeyDraftKeyDown: KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (adminKeySaving) return
    void handleSaveAdminKey()
  }

  const [selectedTenantCode, setSelectedTenantCode] = useState<string>('')
  const [users, setUsers] = useState<TenantUserRow[] | null>(null)
  const [loadingUsers, setLoadingUsers] = useState(false)

  const [moveUserTargets, setMoveUserTargets] = useState<Record<string, string>>({})
  const [movingUserId, setMovingUserId] = useState<string | null>(null)

  const [createUsername, setCreateUsername] = useState('')
  const [createPassword, setCreatePassword] = useState('')
  const [createRole, setCreateRole] = useState<'user' | 'manager'>('user')
  const [creatingUser, setCreatingUser] = useState(false)

  const getAdminHeaders = () => {
    if (!hasAdminKey || !adminUnlocked) return {}
    const k = getAdminApiKeyValue()
    if (!k) return {}
    return { [getAdminApiKeyHeaderName()]: k }
  }

  const handleSaveAdminKey = async () => {
    const trimmed = adminKeyDraft.trim()
    if (!trimmed) {
      showToast('error', t('admin.general.toast.keyRequired'))
      return
    }

    setAdminKeySaving(true)
    try {
      // Verify by calling bootstrap-status (admin-only).
      const res = await fetch('/api/auth/bootstrap-status', {
        headers: {
          [getAdminApiKeyHeaderName()]: trimmed,
        },
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const detail = (body as any)?.detail
        showToast('error', typeof detail === 'string' ? detail : t('admin.general.toast.keyInvalid'))
        clearAdminApiKeyValue()
        clearAdminUnlockedInSession()
        props?.onAdminLocked?.()
        setStoredAdminKeyMasked('')
        return
      }

      setAdminApiKeyValue(trimmed)
      setAdminUnlockedInSession(true)
      setAdminUnlocked(true)
      props?.onAdminUnlocked?.()
      setAdminKeyDraft('')
      setStoredAdminKeyMasked(maskKey(trimmed))
      showToast('success', t('admin.general.toast.keySuccess'))
      void refreshDiagnostics()
    } catch {
      showToast('error', t('admin.general.toast.keyNetworkError'))
    } finally {
      setAdminKeySaving(false)
    }
  }

  const handleClearAdminKey = () => {
    clearAdminApiKeyValue()
    clearAdminUnlockedInSession()
    setAdminUnlocked(false)
    setStoredAdminKeyMasked('')
    props?.onAdminLocked?.()
    showToast('info', t('admin.general.toast.keyCleared'))
  }

  const handleDisableAdminMode = () => {
    // Disable only for this browser tab session. Keep the stored key.
    clearAdminUnlockedInSession()
    setAdminUnlocked(false)
    props?.onAdminLocked?.()
    showToast('info', t('admin.general.toast.disabled'))
  }

  const refreshDiagnostics = async () => {
    setDiagLoading(true)
    try {
      const adminHeaders = getAdminHeaders()
      const [whoRes, bootRes] = await Promise.all([
        fetch('/api/auth/whoami', { headers: adminHeaders }),
        fetch('/api/auth/bootstrap-status', { headers: adminHeaders }),
      ])

      const whoBody = await whoRes.json().catch(() => ({}))
      const bootBody = await bootRes.json().catch(() => ({}))

      if (whoRes.ok) setWhoami(whoBody as WhoAmI)
      if (bootRes.ok) setBootstrapStatus(bootBody as BootstrapStatus)

      if (!whoRes.ok && !bootRes.ok) {
        showToast('error', t('admin.general.toast.diagError'))
        return
      }
      showToast('success', t('admin.general.toast.diagSuccess'))
    } catch {
      showToast('error', t('admin.general.toast.diagNetworkError'))
    } finally {
      setDiagLoading(false)
    }
  }

  const handleBootstrapFirstTenant = async () => {
    try {
      const res = await fetch('/api/tenants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify({}),
      })
      const body = await res.json().catch(() => ({}))
      const detail = (body as any)?.detail
      if (!res.ok) {
        showToast('error', typeof detail === 'string' ? detail : t('admin.tenants.toast.createError', { status: res.status }))
        return
      }

      const id = String((body as any)?.id || '')
      if (id) {
        setTenantId(id)
        setStoredTenantIdState(id)
      }
      showToast('success', t('admin.general.init.toast.bootstrapCreated', { code: String((body as any)?.code || '') || '（已建立）' }))
      await refreshTenants()
    } catch {
      showToast('error', t('admin.general.init.toast.bootstrapError'))
    }
  }

  const handleAutoInitTenant = async () => {
    try {
      const id = await ensureTenantIdWithOptions({ notify: true, reason: 'bootstrap', allowAdminBootstrap: true })
      if (!id) {
        showToast('error', t('admin.general.init.toast.noTenant'))
        return
      }
      setStoredTenantIdState(id)
      showToast('success', t('admin.general.init.toast.tenantReady', { label: getTenantLabelById(id) || t('common.unknown') }))
    } catch {
      showToast('error', t('admin.general.init.toast.initError'))
    }
  }

  const handleClearTenant = () => {
    clearTenantId()
    setStoredTenantIdState('')
    showToast('info', t('admin.general.init.toast.tenantCleared'))
  }

  const handleSetCurrentTenant = async (tenant: TenantRow) => {
    setTenantId(tenant.id)
    setStoredTenantIdState(tenant.id)

    if (!hasAdminKey) {
      showToast('success', t('admin.tenants.toast.switched', { code: tenant.code, name: tenant.name }))
      return
    }

    try {
      const res = await fetch('/api/auth/admin/tenant-api-keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify({ tenant_id: tenant.id }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast(
          'error',
          typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.tenants.toast.switchError', { status: res.status }),
        )
        return
      }

      const apiKey = String((body as any)?.api_key || '').trim()
      if (apiKey) setApiKeyValue(apiKey)

      showToast('success', t('admin.tenants.toast.switchedWithKey', { code: tenant.code, name: tenant.name }))
    } catch {
      showToast('error', t('admin.tenants.toast.switchNetworkError'))
    }
  }

  const refreshTenants = async () => {
    setLoadingTenants(true)
    try {
      const params = new URLSearchParams()
      if (showInactiveTenants) params.set('include_inactive', 'true')
      const suffix = params.toString() ? `?${params.toString()}` : ''
      const res = await fetch(`/api/tenants${suffix}`, { headers: getAdminHeaders() })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.tenants.toast.loadError', { status: res.status }))
        setTenants(null)
        return
      }
      const rows = Array.isArray(body) ? (body as TenantRow[]) : []
      setTenants(rows)
      writeTenantMap(rows)
      if (!selectedTenantCode && rows.length === 1) {
        setSelectedTenantCode(rows[0].code)
      }
    } catch {
      showToast('error', t('admin.tenants.toast.loadNetworkError'))
      setTenants(null)
    } finally {
      setLoadingTenants(false)
    }
  }

  const patchTenant = async (tenantId: string, patch: Partial<Pick<TenantRow, 'name' | 'is_active' | 'is_default'>>) => {
    try {
      const res = await fetch(`/api/tenants/${tenantId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify(patch),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.tenants.toast.updateError', { status: res.status }))
        return
      }
      showToast('success', t('admin.tenants.toast.updated'))
      await refreshTenants()
    } catch {
      showToast('error', t('admin.tenants.toast.updateNetworkError'))
    }
  }

  const createTenant = async () => {
    const name = createTenantName.trim()
    const code = createTenantCode.trim()
    if (!name) {
      showToast('error', t('admin.tenants.requireKey'))
      return
    }
    if (!code) {
      showToast('error', t('admin.tenants.requireCode'))
      return
    }

    setCreateTenantLoading(true)
    try {
      const res = await fetch('/api/tenants/admin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify({ name, code, is_active: true, is_default: createTenantDefault }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.tenants.toast.createError', { status: res.status }))
        return
      }
      showToast('success', t('admin.tenants.toast.created', { code }))
      setCreateTenantName('')
      setCreateTenantCode('')
      setCreateTenantDefault(false)
      await refreshTenants()
    } catch {
      showToast('error', t('admin.tenants.toast.createNetworkError'))
    } finally {
      setCreateTenantLoading(false)
    }
  }

  const deleteTenant = async (tenant: TenantRow) => {
    if (!confirm(t('admin.tenants.confirm.delete', { code: tenant.code }))) return
    try {
      const res = await fetch(`/api/tenants/${tenant.id}`, {
        method: 'DELETE',
        headers: getAdminHeaders(),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.tenants.toast.deleteError', { status: res.status }))
        return
      }
      showToast('success', t('admin.tenants.toast.deleted', { code: tenant.code }))
      await refreshTenants()
    } catch {
      showToast('error', t('admin.tenants.toast.deleteNetworkError'))
    }
  }

  const toggleTenantActive = async (tenant: TenantRow, nextActive: boolean) => {
    await patchTenant(tenant.id, { is_active: nextActive })
  }

  const refreshUsers = async () => {
    const code = selectedTenantCode.trim()
    if (!code) {
      showToast('error', t('admin.users.toast.selectTenantFirst'))
      return
    }

    setLoadingUsers(true)
    try {
      const params = new URLSearchParams({ tenant_code: code, include_inactive: 'true' })
      const res = await fetch(`/api/auth/users?${params.toString()}`, { headers: getAdminHeaders() })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.users.toast.loadError', { status: res.status }))
        setUsers(null)
        return
      }
      setUsers(Array.isArray(body) ? (body as TenantUserRow[]) : [])
    } catch {
      showToast('error', t('admin.users.toast.loadNetworkError'))
      setUsers(null)
    } finally {
      setLoadingUsers(false)
    }
  }

  const patchUser = async (userId: string, patch: Partial<Pick<TenantUserRow, 'username' | 'role' | 'is_active'>>) => {
    try {
      const res = await fetch(`/api/auth/users/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify(patch),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.users.toast.updateError', { status: res.status }))
        return
      }
      showToast('success', t('admin.users.toast.updated'))
      await refreshUsers()
    } catch {
      showToast('error', t('admin.users.toast.updateNetworkError'))
    }
  }

  const moveUserToTenant = async (user: TenantUserRow) => {
    const targetCode = (moveUserTargets[user.id] || '').trim()
    if (!targetCode) {
      showToast('error', t('admin.users.toast.moveSelectFirst'))
      return
    }
    if (targetCode === (user.tenant_code || '')) {
      showToast('info', t('admin.users.toast.moveAlreadyThere'))
      return
    }

    if (!confirm(t('admin.users.confirm.move', { username: user.username, target: targetCode }))) return

    setMovingUserId(user.id)
    try {
      const res = await fetch(`/api/auth/users/${user.id}/tenant`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify({ tenant_code: targetCode, revoke_api_keys: true }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.users.toast.moveError', { status: res.status }))
        return
      }
      showToast('success', t('admin.users.toast.moved', { username: user.username, target: targetCode }))
      setMoveUserTargets((prev) => {
        const next = { ...prev }
        delete next[user.id]
        return next
      })
      await refreshUsers()
    } catch {
      showToast('error', t('admin.users.toast.moveNetworkError'))
    } finally {
      setMovingUserId(null)
    }
  }

  const deleteUser = async (user: TenantUserRow) => {
    if (!confirm(t('admin.users.confirm.delete', { username: user.username }))) return
    try {
      const res = await fetch(`/api/auth/users/${user.id}`, {
        method: 'DELETE',
        headers: getAdminHeaders(),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.users.toast.deleteError', { status: res.status }))
        return
      }
      showToast('success', t('admin.users.toast.deleted'))
      await refreshUsers()
    } catch {
      showToast('error', t('admin.users.toast.deleteNetworkError'))
    }
  }

  const createUser = async () => {
    const code = selectedTenantCode.trim()
    const username = createUsername.trim()
    const password = createPassword

    if (!code) {
      showToast('error', t('admin.users.toast.selectTenantFirst'))
      return
    }
    if (!username) {
      showToast('error', t('admin.users.toast.usernameRequired'))
      return
    }
    if (!password || password.length < 8) {
      showToast('error', t('admin.users.toast.passwordTooShort'))
      return
    }

    setCreatingUser(true)
    try {
      const res = await fetch('/api/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAdminHeaders() },
        body: JSON.stringify({ tenant_code: code, username, password, role: createRole }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', typeof (body as any)?.detail === 'string' ? (body as any).detail : t('admin.users.toast.createError', { status: res.status }))
        return
      }
      showToast('success', t('admin.users.toast.created', { username }))
      setCreateUsername('')
      setCreatePassword('')
      setCreateRole('user')
      await refreshUsers()
    } catch {
      showToast('error', t('admin.users.toast.createNetworkError'))
    } finally {
      setCreatingUser(false)
    }
  }

  useEffect(() => {
    // Best-effort initial load.
    refreshTenants()
  }, [])

  const TABS: { key: AdminTab; label: string }[] = [
    { key: 'general', label: t('admin.tabs.general') },
    { key: 'stations', label: t('admin.tabs.stations') },
    { key: 'validation', label: t('admin.tabs.validation') },
    { key: 'analytics', label: t('admin.tabs.analytics') },
    { key: 'links', label: t('admin.tabs.links') },
  ]

  return (
    <div className="admin-page">
      <nav className="admin-tab-bar" style={{ display: 'flex', gap: 4, marginBottom: 8, borderBottom: '1px solid #e5e7eb', paddingBottom: 4 }}>
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`btn btn-small${activeTab === tab.key ? ' btn-primary' : ''}`}
            onClick={() => setActiveTab(tab.key)}
            style={{ borderRadius: '8px 8px 0 0' }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === 'stations' && <StationManager showToast={showToast} />}
      {activeTab === 'validation' && <ValidationRuleManager showToast={showToast} />}
      {activeTab === 'analytics' && <AnalyticsMappingManager showToast={showToast} />}
      {activeTab === 'links' && <StationLinkManager showToast={showToast} />}

      {activeTab === 'general' && <><section className="register-card">
        <h2 className="register-title">{t('admin.general.title')}</h2>
        <p className="register-hint">{t('admin.general.hint')}</p>

        <div className="register-row">
          <div className="register-kv">
            <div className="register-k">{t('admin.general.keyLabel')}</div>
            <div className="register-v">{storedAdminKeyMasked || t('admin.general.keyNotSet')}</div>
          </div>
          <div className="register-kv">
            <div className="register-k">{t('admin.general.statusLabel')}</div>
            <div className="register-v">{adminUnlocked ? <span className="pill pill-ok">{t('admin.general.statusEnabled')}</span> : <span className="pill pill-off">{t('admin.general.statusDisabled')}</span>}</div>
          </div>
        </div>

        <div className="register-form">
          <label className="register-label">
            {t('admin.general.inputLabel')}
            <input
              className="register-input"
              value={adminKeyDraft}
              onChange={(e) => setAdminKeyDraft(e.target.value)}
              onKeyDown={handleAdminKeyDraftKeyDown}
              placeholder={t('admin.general.inputPlaceholder')}
            />
          </label>

          <div className="register-actions">
            <button className="btn btn-primary" onClick={handleSaveAdminKey} disabled={adminKeySaving}>
              {adminKeySaving ? t('admin.general.btn.saving') : t('admin.general.btn.save')}
            </button>
            <button className="btn" onClick={handleClearAdminKey} disabled={adminKeySaving}>
              {t('admin.general.btn.clear')}
            </button>
            <button className="btn" onClick={handleDisableAdminMode} disabled={adminKeySaving || !adminUnlocked}>
              {t('admin.general.btn.disable')}
            </button>
          </div>

          <details className="register-details" open>
            <summary className="register-summary">{t('admin.general.diag.title')}</summary>
            <div className="register-actions">
              <button className="btn" onClick={refreshDiagnostics} disabled={diagLoading}>
                {diagLoading ? t('admin.general.diag.btnLoading') : t('admin.general.diag.btn')}
              </button>
            </div>

            {whoami && storedTenantId && String(whoami.tenant_id || '') && String(whoami.tenant_id || '') !== storedTenantId ? (
              <p className="register-hint" style={{ color: '#b45309' }}>
                {t('admin.general.diag.tenantMismatch', { local: storedTenantLabel || t('common.unknown'), remote: whoamiTenantLabel || '—' })}
              </p>
            ) : null}

            {whoami && (
              <div className="admin-kv-block">
                <div className="admin-kv">
                  <span className="admin-k">is_admin</span>
                  <span className="admin-v">{String(whoami.is_admin)}</span>
                </div>
                <div className="admin-kv">
                  <span className="admin-k">actor_role</span>
                  <span className="admin-v">{whoami.actor_role || '—'}</span>
                </div>
                <div className="admin-kv">
                  <span className="admin-k">tenant_id</span>
                  <span className="admin-v" title={whoami.tenant_id || ''}>{whoamiTenantLabel || '—'}</span>
                </div>
              </div>
            )}

            {bootstrapStatus && (
              <div className="admin-kv-block">
                <div className="admin-kv">
                  <span className="admin-k">auth_mode</span>
                  <span className="admin-v">{bootstrapStatus.auth_mode}</span>
                </div>
                <div className="admin-kv">
                  <span className="admin-k">admin_header</span>
                  <span className="admin-v">{bootstrapStatus.admin_api_key_header}</span>
                </div>
                <div className="admin-kv">
                  <span className="admin-k">admin_keys_configured</span>
                  <span className="admin-v">{String(bootstrapStatus.admin_keys_configured)}</span>
                </div>
              </div>
            )}
          </details>

          <details className="register-details" open>
            <summary className="register-summary">{t('admin.general.init.title')}</summary>
            <p className="register-hint">
              {t('admin.general.init.hint', { key: TENANT_STORAGE_KEY })}
            </p>

            <div className="register-row">
              <div className="register-kv">
                <div className="register-k">{t('admin.general.init.currentTenant')}</div>
                <div className="register-v">{storedTenantId ? <code title={storedTenantId}>{storedTenantLabel || t('common.unknown')}</code> : <span className="muted">{t('admin.general.init.notSet')}</span>}</div>
              </div>
              <div className="register-actions">
                <button className="btn" onClick={handleAutoInitTenant} disabled={!hasAdminKey} title={!hasAdminKey ? t('admin.general.init.requireKey') : ''}>
                  {t('admin.general.init.btn.autoInit')}
                </button>
                <button className="btn" onClick={handleClearTenant}>{t('admin.general.init.btn.clearTenant')}</button>
              </div>
            </div>

            {!hasAnyActiveTenant ? (
              <div className="register-actions">
                <button className="btn btn-primary" onClick={handleBootstrapFirstTenant} disabled={!hasAdminKey} title={!hasAdminKey ? t('admin.general.init.requireKey') : ''}>
                  {t('admin.general.init.btn.bootstrap')}
                </button>
              </div>
            ) : (
              <p className="register-hint">{t('admin.general.init.hasTenantsHint')}</p>
            )}
          </details>
        </div>
      </section>

      <section className="register-card">
        <div className="admin-header-row">
          <div>
            <h2 className="register-title">{t('admin.tenants.title')}</h2>
            <p className="register-hint">{t('admin.tenants.hint')}</p>
          </div>
          <div className="admin-header-actions">
            <label className="register-hint" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={showInactiveTenants}
                onChange={(e) => setShowInactiveTenants(e.target.checked)}
              />
              {t('admin.tenants.showInactive')}
            </label>
            <button className="btn" onClick={refreshTenants} disabled={loadingTenants}>
              {loadingTenants ? t('admin.tenants.btn.refreshing') : t('admin.tenants.btn.refresh')}
            </button>
          </div>
        </div>

        <details className="register-details">
          <summary className="register-summary">{t('admin.tenants.form.title')}</summary>
          <div className="admin-form-grid">
            <label className="register-label">
              {t('admin.tenants.form.name')}
              <input className="register-input" value={createTenantName} onChange={(e) => setCreateTenantName(e.target.value)} />
            </label>
            <label className="register-label">
              {t('admin.tenants.form.code')}
              <input className="register-input" value={createTenantCode} onChange={(e) => setCreateTenantCode(e.target.value)} />
            </label>
            <label className="register-label">
              {t('admin.tenants.form.default')}
              <select
                className="register-input"
                value={createTenantDefault ? 'yes' : 'no'}
                onChange={(e) => setCreateTenantDefault(e.target.value === 'yes')}
              >
                <option value="no">{t('admin.tenants.form.no')}</option>
                <option value="yes">{t('admin.tenants.form.yes')}</option>
              </select>
            </label>
          </div>
          <div className="register-actions">
            <button className="btn btn-primary" onClick={createTenant} disabled={!hasAdminKey || createTenantLoading}>
              {createTenantLoading ? t('admin.tenants.btn.creating') : t('admin.tenants.btn.create')}
            </button>
          </div>
        </details>

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('admin.tenants.table.colArea')}</th>
                <th>{t('admin.tenants.table.colCode')}</th>
                <th>{t('admin.tenants.table.colName')}</th>
                <th>{t('admin.tenants.table.colDefault')}</th>
                <th>{t('admin.tenants.table.colActive')}</th>
                <th>{t('admin.tenants.table.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {(tenants || []).map((tenant) => (
                <tr key={tenant.id}>
                  <td className="admin-mono"><span title={tenant.id}>{getTenantLabelById(tenant.id) || t('common.unknown')}</span></td>
                  <td>{tenant.code}</td>
                  <td>
                    <input
                      className="admin-inline-input"
                      defaultValue={tenant.name}
                      onBlur={(e) => {
                        const v = e.target.value.trim()
                        if (v && v !== tenant.name) patchTenant(tenant.id, { name: v })
                      }}
                    />
                  </td>
                  <td>
                    <span className={tenant.is_default ? 'pill pill-ok' : 'pill pill-off'}>{tenant.is_default ? t('admin.tenants.table.pillDefault') : '—'}</span>
                  </td>
                  <td>
                    <span className={tenant.is_active ? 'pill pill-ok' : 'pill pill-off'}>{tenant.is_active ? t('admin.tenants.table.pillActive') : t('admin.tenants.table.pillInactive')}</span>
                  </td>
                  <td>
                    <button className="btn btn-small" onClick={() => handleSetCurrentTenant(tenant)}>
                      {t('admin.tenants.btn.applyCurrent')}
                    </button>
                    <button
                      className="btn btn-small"
                      onClick={() => toggleTenantActive(tenant, !tenant.is_active)}
                      disabled={!hasAdminKey}
                      title={!hasAdminKey ? t('admin.general.init.requireKey') : ''}
                      style={{ marginLeft: 8 }}
                    >
                      {tenant.is_active ? t('admin.tenants.btn.disable') : t('admin.tenants.btn.enable')}
                    </button>
                    <button
                      className="btn btn-small"
                      onClick={() => patchTenant(tenant.id, { is_default: true })}
                      disabled={!hasAdminKey}
                      title={!hasAdminKey ? t('admin.general.init.requireKey') : ''}
                      style={{ marginLeft: 8 }}
                    >
                      {t('admin.tenants.btn.setDefault')}
                    </button>
                    <button
                      className="btn btn-small"
                      onClick={() => deleteTenant(tenant)}
                      disabled={!hasAdminKey}
                      title={!hasAdminKey ? t('admin.general.init.requireKey') : ''}
                      style={{ marginLeft: 8 }}
                    >
                      {t('admin.tenants.btn.delete')}
                    </button>
                  </td>
                </tr>
              ))}
              {!tenants?.length && (
                <tr>
                  <td colSpan={6} className="admin-empty">
                    {tenants === null ? t('admin.tenants.table.notLoaded') : t('admin.tenants.table.empty')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="register-card">
        <div className="admin-header-row">
          <div>
            <h2 className="register-title">{t('admin.users.title')}</h2>
            <p className="register-hint">{t('admin.users.hint')}</p>
          </div>
          <div className="admin-header-actions">
            <select
              className="register-input admin-select"
              value={selectedTenantCode}
              onChange={(e) => setSelectedTenantCode(e.target.value)}
            >
              <option value="">{t('admin.users.selectTenantPlaceholder')}</option>
              {(tenants || []).map((tenant) => (
                <option key={tenant.id} value={tenant.code}>
                  {tenant.code} ({tenant.name})
                </option>
              ))}
            </select>
            <button className="btn" onClick={refreshUsers} disabled={loadingUsers}>
              {loadingUsers ? t('admin.users.btn.loading') : t('admin.users.btn.loadUsers')}
            </button>
          </div>
        </div>

        <details className="register-details">
          <summary className="register-summary">{t('admin.users.form.title')}</summary>
          <div className="admin-form-grid">
            <label className="register-label">
              {t('admin.users.form.username')}
              <input className="register-input" value={createUsername} onChange={(e) => setCreateUsername(e.target.value)} />
            </label>
            <label className="register-label">
              {t('admin.users.form.password')}
              <input
                className="register-input"
                type="password"
                value={createPassword}
                onChange={(e) => setCreatePassword(e.target.value)}
                placeholder={t('admin.users.form.passwordPlaceholder')}
              />
            </label>
            <label className="register-label">
              {t('admin.users.form.role')}
              <select className="register-input" value={createRole} onChange={(e) => setCreateRole(e.target.value as any)}>
                <option value="user">{t('admin.users.form.roleUser')}</option>
                <option value="manager">{t('admin.users.form.roleManager')}</option>
              </select>
            </label>
          </div>
          <div className="register-actions">
            <button className="btn btn-primary" onClick={createUser} disabled={creatingUser}>
              {creatingUser ? t('admin.users.form.btn.creating') : t('admin.users.form.btn.create')}
            </button>
          </div>
        </details>

        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>{t('admin.users.table.colUsername')}</th>
                <th>{t('admin.users.table.colTenant')}</th>
                <th>{t('admin.users.table.colRole')}</th>
                <th>{t('admin.users.table.colActive')}</th>
                <th>{t('admin.users.table.colLastLogin')}</th>
                <th>{t('admin.users.table.colActions')}</th>
              </tr>
            </thead>
            <tbody>
              {(users || []).map((u) => (
                <tr key={u.id} className={!u.is_active ? 'is-inactive' : ''}>
                  <td>
                    <input
                      className="admin-inline-input"
                      defaultValue={u.username}
                      onBlur={(e) => {
                        const v = e.target.value.trim()
                        if (v && v !== u.username) patchUser(u.id, { username: v })
                      }}
                    />
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className="admin-mono">{u.tenant_code || '—'}</span>
                      <select
                        className="admin-inline-input"
                        value={moveUserTargets[u.id] || ''}
                        onChange={(e) =>
                          setMoveUserTargets((prev) => ({
                            ...prev,
                            [u.id]: e.target.value,
                          }))
                        }
                      >
                        <option value="">{t('admin.users.table.moveToPlaceholder')}</option>
                        {(tenants || []).map((tenant) => (
                          <option key={tenant.id} value={tenant.code}>
                            {tenant.code} ({tenant.name})
                          </option>
                        ))}
                      </select>
                      <button className="btn btn-small" onClick={() => moveUserToTenant(u)} disabled={movingUserId === u.id}>
                        {movingUserId === u.id ? t('admin.users.table.btn.moving') : t('admin.users.table.btn.move')}
                      </button>
                    </div>
                  </td>
                  <td>
                    <select
                      className="admin-inline-input"
                      defaultValue={u.role}
                      onChange={(e) => {
                        const v = e.target.value
                        if (v !== u.role) patchUser(u.id, { role: v })
                      }}
                    >
                      <option value="user">{t('admin.users.form.roleUser')}</option>
                      <option value="manager">{t('admin.users.form.roleManager')}</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      defaultChecked={u.is_active}
                      onChange={(e) => patchUser(u.id, { is_active: e.target.checked })}
                    />
                  </td>
                  <td className="admin-mono">{u.last_login_at || '—'}</td>
                  <td>
                    <button className="btn btn-small" onClick={() => patchUser(u.id, { is_active: !u.is_active })}>
                      {u.is_active ? t('admin.users.table.btn.disable') : t('admin.users.table.btn.enable')}
                    </button>
                    <button className="btn btn-small" onClick={() => deleteUser(u)} style={{ marginLeft: 8 }}>
                      {t('admin.users.table.btn.disable')}
                    </button>
                  </td>
                </tr>
              ))}
              {!users?.length && (
                <tr>
                  <td colSpan={6} className="admin-empty">
                    {users === null ? t('admin.users.table.notLoaded') : t('admin.users.table.empty')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section></>}
    </div>
  )
}
