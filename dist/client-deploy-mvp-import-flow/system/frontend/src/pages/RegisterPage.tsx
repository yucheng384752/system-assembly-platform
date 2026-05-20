// src/pages/RegisterPage.tsx
import { useEffect, useMemo, useState, type KeyboardEventHandler } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../components/common/ToastContext'
import { clearApiKeyValue, getApiKeyValue, setApiKeyValue } from '../services/auth'
import { clearTenantId, getTenantId, setTenantId } from '../services/tenant'
import { getTenantLabelById, writeTenantMap } from '../services/tenantMap'
import {
  clearAdminApiKeyValue,
  clearAdminUnlockedInSession,
  getAdminApiKeyHeaderName,
  setAdminApiKeyValue,
  setAdminUnlockedInSession,
} from '../services/adminAuth'
import './../styles/register-page.css'

type TenantRow = {
  id: string
  name?: string
  code?: string
  is_active?: boolean
  is_default?: boolean
}

type WhoAmI = {
  is_admin: boolean
  tenant_id?: string | null
  actor_user_id?: string | null
  actor_role?: string | null
  api_key_label?: string | null
  must_change_password?: boolean
}

export function RegisterPage(props: { onAdminUnlocked?: (ok: boolean) => void; onWhoamiChanged?: (whoami: WhoAmI | null) => void }) {
  const { t } = useTranslation()
  const { showToast } = useToast()

  const maskKey = (raw: string) => {
    const v = String(raw || '').trim()
    if (!v) return ''
    if (v.length <= 8) return `${v.slice(0, 2)}…${v.slice(-2)}`
    return `${v.slice(0, 4)}…${v.slice(-4)}`
  }

  const [tenants, setTenants] = useState<TenantRow[] | null>(null)
  const [loadingTenants, setLoadingTenants] = useState(false)

  const [loginTenantCode, setLoginTenantCode] = useState('')
  const [loginUsername, setLoginUsername] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)

  const [pwOld, setPwOld] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwChanging, setPwChanging] = useState(false)

  const [adminKeyDraft, setAdminKeyDraft] = useState('')
  const [adminKeyLoading, setAdminKeyLoading] = useState(false)

  const [whoami, setWhoami] = useState<WhoAmI | null>(null)
  const [diagLoading, setDiagLoading] = useState(false)

  useEffect(() => {
    props?.onWhoamiChanged?.(whoami)
  }, [whoami, props?.onWhoamiChanged])

  const [storedTenantId, setStoredTenantIdState] = useState(() => getTenantId())
  const [storedApiKeyMasked, setStoredApiKeyMasked] = useState(() => maskKey(getApiKeyValue()))
  const [tenantsAuthRequired, setTenantsAuthRequired] = useState<boolean | null>(null)

  const hasApiKey = useMemo(() => Boolean(storedApiKeyMasked), [storedApiKeyMasked])

  const storedTenantLabel = useMemo(() => {
    if (!storedTenantId) return ''

    const fromList = tenants?.find((t) => String(t?.id || '') === storedTenantId)
    if (fromList?.name || fromList?.code) {
      const code = String(fromList?.code || '').trim()
      return code || ''
    }

    return getTenantLabelById(storedTenantId)
  }, [storedTenantId, tenants])

  // Auto refresh whoami when API key exists (for role-based UI)
  useEffect(() => {
    if (!hasApiKey) {
      setWhoami(null)
      return
    }
    if (whoami) return

    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/auth/whoami')
        if (!res.ok) return
        const body = (await res.json().catch(() => ({}))) as WhoAmI
        if (!cancelled) setWhoami(body)
      } catch {
        // ignore
      }
    })()

    return () => {
      cancelled = true
    }
  }, [hasApiKey, whoami])

  const handleFetchDiagnostics = async () => {
    setDiagLoading(true)
    try {
      const res = await fetch('/api/auth/whoami')
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        showToast('error', t('register.toast.diagFailedNeedLogin'))
        return
      }
      setWhoami(body as WhoAmI)
      showToast('success', t('register.toast.diagUpdated'))
    } catch {
      showToast('error', t('register.toast.diagFailedNetwork'))
    } finally {
      setDiagLoading(false)
    }
  }

  const refreshTenants = async () => {
    setLoadingTenants(true)
    try {
      const res = await fetch('/api/tenants')
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const detail = (body as any)?.detail
        if (res.status === 401) {
          showToast('error', t('register.toast.authEnabledNeedLogin'))
          setTenantsAuthRequired(true)
          setTenants(null)
          return
        }
        showToast(
          'error',
          typeof detail === 'string' ? detail : t('register.toast.fetchTenantsFailedHttp', { status: res.status }),
        )
        setTenants(null)
        return
      }
      const data = (await res.json()) as TenantRow[]
      setTenants(Array.isArray(data) ? data : [])
      if (Array.isArray(data)) writeTenantMap(data)
      setTenantsAuthRequired(false)
      showToast('success', t('register.toast.fetchTenantsOk', { count: Array.isArray(data) ? data.length : 0 }))
    } catch {
      showToast('error', t('register.toast.fetchTenantsFailedNetwork'))
      setTenants(null)
    } finally {
      setLoadingTenants(false)
    }
  }

  const handleClearApiKey = () => {
    clearApiKeyValue()
    setStoredApiKeyMasked('')
    setWhoami(null)
    showToast('info', t('register.toast.clearedCredentials'))
  }

  const handleSetTenant = (id: string) => {
    const trimmed = String(id || '').trim()
    if (!trimmed) {
      showToast('error', t('register.toast.tenantIdEmpty'))
      return
    }
    setTenantId(trimmed)
    setStoredTenantIdState(trimmed)
    const label = getTenantLabelById(trimmed)
    showToast('success', t('register.toast.tenantSet', { label: label || t('common.unknown') }))
  }

  const handleClearTenant = () => {
    clearTenantId()
    setStoredTenantIdState('')
    showToast('info', t('register.toast.tenantCleared'))
  }

  const handlePasswordLogin = async () => {
    const username = loginUsername.trim()
    const password = loginPassword
    const tenantCode = loginTenantCode.trim()
    if (!username) {
      showToast('error', t('register.toast.usernameRequired'))
      return
    }
    if (!password) {
      showToast('error', t('register.toast.passwordRequired'))
      return
    }

    setLoginLoading(true)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant_code: tenantCode || undefined, username, password }),
      })
      const body = await res.json().catch(() => ({}))
      const detail = (body as any)?.detail
      if (!res.ok) {
        showToast('error', typeof detail === 'string' ? detail : t('register.toast.loginFailedHttp', { status: res.status }))
        return
      }

      const tenantId = String((body as any)?.tenant_id || '')
      const apiKey = String((body as any)?.api_key || '')
      if (!tenantId || !apiKey) {
        showToast('error', t('register.toast.loginResponseIncomplete'))
        return
      }

      setTenantId(tenantId)
      setStoredTenantIdState(tenantId)

      setApiKeyValue(apiKey)
      setStoredApiKeyMasked(maskKey(apiKey))

      // Force refresh whoami for role-based UI when login changes identity.
      setWhoami(null)

      setLoginPassword('')
      showToast('success', t('register.toast.loginSuccessSaved'))
    } catch {
      showToast('error', t('register.toast.loginFailedNetwork'))
    } finally {
      setLoginLoading(false)
    }
  }

  const handleChangeMyPassword = async () => {
    const old_password = pwOld
    const new_password = pwNew

    if (!old_password) {
      showToast('error', t('register.toast.passwordOldRequired', '請輸入舊密碼'))
      return
    }
    if (!new_password || new_password.length < 8) {
      showToast('error', t('register.toast.passwordNewMin8', '新密碼至少 8 碼'))
      return
    }

    setPwChanging(true)
    try {
      const res = await fetch('/api/auth/me/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_password, new_password }),
      })

      if (res.status !== 204) {
        const body = await res.json().catch(() => ({}))
        const detail = (body as any)?.detail
        showToast('error', typeof detail === 'string' ? detail : t('register.toast.passwordChangeFailed', '變更密碼失敗'))
        return
      }

      setPwOld('')
      setPwNew('')
      showToast('success', t('register.toast.passwordChangeOk', '已更新密碼'))
      await handleFetchDiagnostics()
    } catch {
      showToast('error', t('register.toast.passwordChangeFailedNetwork', '變更密碼失敗（網路或伺服器未啟動）'))
    } finally {
      setPwChanging(false)
    }
  }

  const handleLoginKeyDown: KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (loginLoading) return
    void handlePasswordLogin()
  }

  const handleAdminKeyDown: KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (adminKeyLoading) return
    void handleVerifyAdminKey()
  }

  const handleVerifyAdminKey = async () => {
    const key = adminKeyDraft.trim()
    if (!key) {
      showToast('error', t('register.toast.adminKeyRequired'))
      return
    }

    setAdminKeyLoading(true)
    try {
      // Verify by calling bootstrap-status (admin-only).
      const res = await fetch('/api/auth/bootstrap-status', {
        headers: {
          [getAdminApiKeyHeaderName()]: key,
        },
      })

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const detail = (body as any)?.detail
        showToast('error', typeof detail === 'string' ? detail : t('register.toast.adminKeyInvalid'))
        clearAdminApiKeyValue()
        clearAdminUnlockedInSession()
        props.onAdminUnlocked?.(false)
        return
      }

      setAdminApiKeyValue(key)
      setAdminUnlockedInSession(true)
      setAdminKeyDraft('')
      props.onAdminUnlocked?.(true)
      showToast('success', t('register.toast.adminKeyVerifySuccessUnlockTab'))
    } catch {
      showToast('error', t('register.toast.adminKeyVerifyFailedNetwork'))
    } finally {
      setAdminKeyLoading(false)
    }
  }

  return (
    <div className="register-page">
      {whoami?.must_change_password ? (
        <div
          style={{
            margin: '12px 0',
            padding: '12px 14px',
            borderRadius: 10,
            border: '1px solid rgba(255, 165, 0, 0.35)',
            background: 'rgba(255, 165, 0, 0.12)',
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{t('register.password.mustChangeTitle', '需要變更密碼')}</div>
          <div style={{ opacity: 0.9 }}>
            {t(
              'register.password.mustChangeHint',
              '你的密碼已被重設，請先到「使用者管理」或「管理者頁」變更密碼後再使用其他功能。',
            )}
          </div>
        </div>
      ) : null}
      <section className="register-card">
        <h2 className="register-title">{t('register.title')}</h2>

        {!hasApiKey ? (
          <>
            <div className="register-form">
              <div className="register-row">
                <label className="register-label" style={{ minWidth: 220, flex: 1 }}>
                  {t('register.tenantCodeOptional')}
                  <input
                    className="register-input"
                    type="text"
                    placeholder={t('register.tenantCodePlaceholder')}
                    value={loginTenantCode}
                    onChange={(e) => setLoginTenantCode(e.target.value)}
                    onKeyDown={handleLoginKeyDown}
                  />
                </label>
                <label className="register-label" style={{ minWidth: 220, flex: 1 }}>
                  {t('register.username')}
                  <input
                    className="register-input"
                    type="text"
                    placeholder={t('register.usernamePlaceholder')}
                    value={loginUsername}
                    onChange={(e) => setLoginUsername(e.target.value)}
                    onKeyDown={handleLoginKeyDown}
                  />
                </label>
                <label className="register-label" style={{ minWidth: 220, flex: 1 }}>
                  {t('register.password')}
                  <input
                    className="register-input"
                    type="password"
                    placeholder={t('register.passwordPlaceholder')}
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    onKeyDown={handleLoginKeyDown}
                  />
                </label>
              </div>

              <div className="register-actions">
                <button className="btn-primary" disabled={loginLoading} onClick={handlePasswordLogin}>
                  {loginLoading ? t('register.loggingIn') : t('register.login')}
                </button>
              </div>
            </div>

            <details
              className="register-details"
              open={false}
            >
              <summary className="register-summary">{t('register.tips')}</summary>
              <div className="register-hint">
                {t('register.adminHint')}
              </div>
              <div className="register-form" style={{ marginTop: '0.75rem' }}>
                <label className="register-label">
                  {t('register.adminKey')}
                  <input
                    className="register-input"
                    type="password"
                    placeholder={t('register.adminKeyPlaceholder')}
                    value={adminKeyDraft}
                    onChange={(e) => setAdminKeyDraft(e.target.value)}
                    onKeyDown={handleAdminKeyDown}
                  />
                </label>
                <div className="register-actions">
                  <button className="btn-secondary" disabled={adminKeyLoading} onClick={handleVerifyAdminKey}>
                    {adminKeyLoading ? t('register.verifying') : t('register.verifyAndUnlock')}
                  </button>
                </div>
              </div>
            </details>
          </>
        ) : (
          <>
            <div className="register-row" style={{ marginTop: '0.75rem' }}>
              <div className="register-kv">
                <div className="register-k">{t('register.tenantId')}</div>
                <div className="register-v">
                  {storedTenantId ? (
                    <>
                      <strong title={storedTenantId}>{storedTenantLabel || t('common.unknown')}</strong>
                    </>
                  ) : (
                    <span className="muted">{t('register.tenantNotSaved')}</span>
                  )}
                </div>
              </div>
              <div className="register-kv">
                <div className="register-k">{t('register.role')}</div>
                <div className="register-v">
                  {whoami ? (
                    <code>
                      {whoami.is_admin
                        ? t('roles.globalAdmin')
                        : t(`roles.${String(whoami.actor_role || 'user').trim() || 'user'}`)}
                    </code>
                  ) : (
                    <span className="muted">{t('register.roleLoading')}</span>
                  )}
                </div>
              </div>
              <div className="register-actions">
                <button className="btn-secondary" disabled={diagLoading} onClick={handleFetchDiagnostics}>
                  {diagLoading ? t('common.loading') : t('register.updateIdentity')}
                </button>
                <button className="btn-secondary" onClick={handleClearApiKey}>{t('register.logout')}</button>
              </div>
            </div>

            <details className="register-details" open>
              <summary className="register-summary">{t('register.tenantSettings')}</summary>
              <div className="register-row">
                <div className="register-kv">
                  <div className="register-k">{t('register.tenantSelected')}</div>
                  <div className="register-v">{storedTenantId ? <span title={storedTenantId}>{storedTenantLabel || t('common.unknown')}</span> : <span className="muted">{t('register.none')}</span>}</div>
                </div>
                <div className="register-actions">
                  <button className="btn-secondary" onClick={handleClearTenant}>{t('register.clearTenantId')}</button>
                </div>
              </div>

              <div className="register-actions">
                <button className="btn-secondary" disabled={loadingTenants} onClick={refreshTenants}>
                  {loadingTenants ? t('common.loading') : t('register.refreshTenants')}
                </button>
                {tenantsAuthRequired === true && <span className="muted">{t('register.tenantsNeedAuth')}</span>}
              </div>

              {tenants && (
                <div className="register-tenants">
                  <div className="register-tenants-title">{t('register.tenants')}</div>
                  {tenants.length === 0 ? (
                    <div className="muted">{t('register.tenantsEmpty')}</div>
                  ) : (
                    <div className="register-tenants-grid">
                      {tenants.map((tenant) => (
                        <div key={tenant.id} className="register-tenant-item">
                          <div className="register-tenant-id">
                            <code title={tenant.id}>{getTenantLabelById(tenant.id) || t('common.unknown')}</code>
                          </div>
                          <div className="register-tenant-meta muted">
                            name={tenant.name ?? '-'} / code={tenant.code ?? '-'}
                          </div>
                          <div className="register-actions">
                            <button className="btn-secondary" onClick={() => handleSetTenant(tenant.id)}>{t('register.useTenant')}</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </details>

            <details className="register-details">
              <summary className="register-summary">{t('register.adminTips')}</summary>
              <div className="register-hint">{t('register.adminTipsText')}</div>
              <div className="register-form" style={{ marginTop: '0.75rem' }}>
                <label className="register-label">
                  {t('register.adminKey')}
                  <input
                    className="register-input"
                    type="password"
                    placeholder={t('register.adminKeyPlaceholder')}
                    value={adminKeyDraft}
                    onChange={(e) => setAdminKeyDraft(e.target.value)}
                    onKeyDown={handleAdminKeyDown}
                  />
                </label>
                <div className="register-actions">
                  <button className="btn-secondary" disabled={adminKeyLoading} onClick={handleVerifyAdminKey}>
                    {adminKeyLoading ? t('register.verifying') : t('register.verifyAndUnlock')}
                  </button>
                </div>
              </div>
            </details>
          </>
        )}

      </section>

      {hasApiKey ? (
        <section className="register-card" style={{ marginTop: 16 }}>
          <h2 className="register-title">{t('register.password.title', '變更密碼')}</h2>
          <div className="register-hint">{t('register.password.hint', '需要提供舊密碼；成功後會撤銷其他登入金鑰。')}</div>

          <div className="register-form" style={{ marginTop: '0.75rem' }}>
            <div className="register-row">
              <label className="register-label" style={{ minWidth: 220, flex: 1 }}>
                {t('register.password.old', '舊密碼')}
                <input
                  className="register-input"
                  type="password"
                  placeholder={t('register.password.oldPlaceholder', '輸入目前密碼')}
                  value={pwOld}
                  onChange={(e) => setPwOld(e.target.value)}
                />
              </label>
              <label className="register-label" style={{ minWidth: 220, flex: 1 }}>
                {t('register.password.new', '新密碼')}
                <input
                  className="register-input"
                  type="password"
                  placeholder={t('register.password.newPlaceholder', '至少 8 碼')}
                  value={pwNew}
                  onChange={(e) => setPwNew(e.target.value)}
                />
              </label>
            </div>

            <div className="register-actions">
              <button className="btn-primary" disabled={pwChanging} onClick={() => void handleChangeMyPassword()}>
                {pwChanging ? t('register.password.changing', '更新中…') : t('register.password.change', '更新密碼')}
              </button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}
