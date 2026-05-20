import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../components/common/ToastContext'
import './../styles/manager-page.css'

type WhoAmI = {
  is_admin: boolean
  tenant_id?: string | null
  actor_user_id?: string | null
  actor_role?: string | null
  api_key_label?: string | null
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

async function readErrorDetail(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}))
  const detail = (body as any)?.detail
  return typeof detail === 'string' ? detail : ''
}

export function ManagerPage() {
  const { t } = useTranslation()
  const { showToast } = useToast()

  const [whoami, setWhoami] = useState<WhoAmI | null>(null)
  const [loadingWhoami, setLoadingWhoami] = useState(false)

  const [users, setUsers] = useState<TenantUserRow[] | null>(null)
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [includeInactive, setIncludeInactive] = useState(false)

  const [createUsername, setCreateUsername] = useState('')
  const [createPassword, setCreatePassword] = useState('')
  const [createRole, setCreateRole] = useState<'user' | 'manager'>('user')
  const [creating, setCreating] = useState(false)

  const [pendingRoleById, setPendingRoleById] = useState<Record<string, string>>({})
  const [pendingActiveById, setPendingActiveById] = useState<Record<string, boolean>>({})
  const [savingUserId, setSavingUserId] = useState<string | null>(null)

  const canManage = useMemo(() => {
    const r = String(whoami?.actor_role || '').trim()
    return r === 'manager'
  }, [whoami?.actor_role])

  const refreshWhoami = async () => {
    setLoadingWhoami(true)
    try {
      const res = await fetch('/api/auth/whoami')
      if (!res.ok) {
        const detail = await readErrorDetail(res)
        showToast('error', detail || t('manager.toast.whoamiFailed'))
        setWhoami(null)
        return
      }
      const body = (await res.json().catch(() => ({}))) as WhoAmI
      setWhoami(body)
    } catch {
      showToast('error', t('manager.toast.whoamiFailedNetwork'))
      setWhoami(null)
    } finally {
      setLoadingWhoami(false)
    }
  }

  const refreshUsers = async () => {
    setLoadingUsers(true)
    try {
      const params = new URLSearchParams()
      if (includeInactive) params.set('include_inactive', 'true')
      const res = await fetch(`/api/auth/users?${params.toString()}`)
      if (!res.ok) {
        const detail = await readErrorDetail(res)
        showToast(
          'error',
          detail || t('manager.toast.fetchUsersFailedHttp', { status: res.status }),
        )
        setUsers(null)
        return
      }
      const body = (await res.json().catch(() => ([]))) as TenantUserRow[]
      const list = Array.isArray(body) ? body : []
      setUsers(list)

      const nextRole: Record<string, string> = {}
      const nextActive: Record<string, boolean> = {}
      for (const u of list) {
        nextRole[u.id] = u.role
        nextActive[u.id] = Boolean(u.is_active)
      }
      setPendingRoleById(nextRole)
      setPendingActiveById(nextActive)
    } catch {
      showToast('error', t('manager.toast.fetchUsersFailedNetwork'))
      setUsers(null)
    } finally {
      setLoadingUsers(false)
    }
  }

  useEffect(() => {
    void refreshWhoami()
  }, [])

  useEffect(() => {
    if (!canManage) return
    void refreshUsers()
  }, [includeInactive, canManage])

  const handleCreateUser = async () => {
    const username = createUsername.trim()
    const password = createPassword

    if (!username) {
      showToast('error', t('manager.toast.usernameRequired'))
      return
    }
    if (!password || password.length < 8) {
      showToast('error', t('manager.toast.passwordMin'))
      return
    }

    setCreating(true)
    try {
      const res = await fetch('/api/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, role: createRole }),
      })
      if (!res.ok) {
        const detail = await readErrorDetail(res)
        showToast(
          'error',
          detail || t('manager.toast.createUserFailedHttp', { status: res.status }),
        )
        return
      }
      showToast('success', t('manager.toast.createUserSuccess'))
      setCreateUsername('')
      setCreatePassword('')
      setCreateRole('user')
      await refreshUsers()
    } catch {
      showToast('error', t('manager.toast.createUserFailedNetwork'))
    } finally {
      setCreating(false)
    }
  }

  const handleSaveUser = async (u: TenantUserRow) => {
    const nextRole = String(pendingRoleById[u.id] ?? u.role).trim() || 'user'
    const nextActive = Boolean(pendingActiveById[u.id] ?? u.is_active)

    const patch: Record<string, any> = {}
    if (nextRole !== u.role) patch.role = nextRole
    if (nextActive !== Boolean(u.is_active)) patch.is_active = nextActive

    if (Object.keys(patch).length === 0) return

    setSavingUserId(u.id)
    try {
      const res = await fetch(`/api/auth/users/${u.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!res.ok) {
        const detail = await readErrorDetail(res)
        showToast(
          'error',
          detail || t('manager.toast.updateUserFailedHttp', { status: res.status }),
        )
        return
      }
      showToast('success', t('manager.toast.updateUserSuccess'))
      await refreshUsers()
    } catch {
      showToast('error', t('manager.toast.updateUserFailedNetwork'))
    } finally {
      setSavingUserId(null)
    }
  }

  const handleDeactivateUser = async (u: TenantUserRow) => {
    if (
      !confirm(
        t('manager.confirm.deactivateUser', { username: u.username }),
      )
    )
      return

    setSavingUserId(u.id)
    try {
      const res = await fetch(`/api/auth/users/${u.id}`, { method: 'DELETE' })
      if (!res.ok) {
        const detail = await readErrorDetail(res)
        showToast(
          'error',
          detail || t('manager.toast.deactivateUserFailedHttp', { status: res.status }),
        )
        return
      }
      showToast('success', t('manager.toast.deactivateUserSuccess'))
      await refreshUsers()
    } catch {
      showToast('error', t('manager.toast.deactivateUserFailedNetwork'))
    } finally {
      setSavingUserId(null)
    }
  }

  return (
    <div className="manager-page">
      <div className="manager-header">
        <div>
          <h2 className="manager-title">{t('manager.title')}</h2>
          <div className="manager-subtitle">{t('manager.subtitle')}</div>
        </div>
        <div className="manager-actions">
          <button className="btn-secondary" disabled={loadingWhoami} onClick={() => void refreshWhoami()}>
            {loadingWhoami ? t('common.loading') : t('manager.actions.refreshIdentity')}
          </button>
          <button className="btn-secondary" disabled={loadingUsers || !canManage} onClick={() => void refreshUsers()}>
            {loadingUsers ? t('common.loading') : t('manager.actions.refreshUsers')}
          </button>
        </div>
      </div>

      <div className="manager-card">
        <div className="manager-kv">
          <div className="k">{t('fields.tenantId')}</div>
          <div className="v"><code>{whoami?.tenant_id || '—'}</code></div>
        </div>
        <div className="manager-kv">
          <div className="k">{t('fields.actorRole')}</div>
          <div className="v"><code>{whoami?.actor_role || '—'}</code></div>
        </div>
        <div className="manager-kv">
          <div className="k">{t('fields.apiKeyLabel')}</div>
          <div className="v"><code>{whoami?.api_key_label || '—'}</code></div>
        </div>
      </div>

      {!canManage ? (
        <div className="manager-empty">{t('manager.notManager')}</div>
      ) : (
        <>
          <div className="manager-card">
            <div className="manager-row">
              <label className="manager-label">
                {t('manager.labels.username')}
                <input className="manager-input" value={createUsername} onChange={(e) => setCreateUsername(e.target.value)} />
              </label>
              <label className="manager-label">
                {t('manager.labels.password')}
                <input className="manager-input" type="password" value={createPassword} onChange={(e) => setCreatePassword(e.target.value)} />
              </label>
              <label className="manager-label">
                {t('manager.labels.role')}
                <select className="manager-select" value={createRole} onChange={(e) => setCreateRole(e.target.value as any)}>
                  <option value="user">{t('roles.user')}</option>
                  <option value="manager">{t('roles.manager')}</option>
                </select>
              </label>
              <div className="manager-row-actions">
                <button className="btn-secondary" disabled={creating} onClick={() => void handleCreateUser()}>
                  {creating ? t('common.loading') : t('manager.actions.createUser')}
                </button>
              </div>
            </div>
            <div className="manager-hint muted">{t('manager.hint')}</div>
          </div>

          <div className="manager-card">
            <label className="manager-checkbox">
              <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
              {t('manager.labels.includeInactive')}
            </label>
          </div>

          <div className="manager-card">
            {users === null ? (
              <div className="muted">{t('common.loading')}</div>
            ) : users.length === 0 ? (
              <div className="muted">{t('common.noData')}</div>
            ) : (
              <div className="manager-table-wrap">
                <table className="manager-table">
                  <thead>
                    <tr>
                      <th>{t('manager.table.username')}</th>
                      <th>{t('manager.table.role')}</th>
                      <th>{t('manager.table.active')}</th>
                      <th>{t('manager.table.createdAt')}</th>
                      <th>{t('manager.table.lastLoginAt')}</th>
                      <th style={{ width: 220 }}>{t('manager.table.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => {
                      const pendingRole = pendingRoleById[u.id] ?? u.role
                      const pendingActive = pendingActiveById[u.id] ?? Boolean(u.is_active)
                      const dirty = pendingRole !== u.role || Boolean(pendingActive) !== Boolean(u.is_active)
                      const busy = savingUserId === u.id

                      return (
                        <tr key={u.id} className={!u.is_active ? 'is-inactive' : ''}>
                          <td>
                            <div className="username">{u.username}</div>
                            <div className="muted small"><code>{u.id}</code></div>
                          </td>
                          <td>
                            <select
                              className="manager-select"
                              value={pendingRole}
                              onChange={(e) => setPendingRoleById((p) => ({ ...p, [u.id]: e.target.value }))}
                            >
                              <option value="user">{t('roles.user')}</option>
                              <option value="manager">{t('roles.manager')}</option>
                            </select>
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              checked={Boolean(pendingActive)}
                              onChange={(e) => setPendingActiveById((p) => ({ ...p, [u.id]: e.target.checked }))}
                            />
                          </td>
                          <td><span className="small">{u.created_at || '—'}</span></td>
                          <td><span className="small">{u.last_login_at || '—'}</span></td>
                          <td>
                            <div className="row-actions">
                              <button className="btn-secondary" disabled={!dirty || busy} onClick={() => void handleSaveUser(u)}>
                                {busy ? t('common.loading') : t('manager.actions.save')}
                              </button>
                              <button className="btn-danger" disabled={busy || !u.is_active} onClick={() => void handleDeactivateUser(u)}>
                                {busy ? t('common.loading') : t('manager.actions.deactivate')}
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}






