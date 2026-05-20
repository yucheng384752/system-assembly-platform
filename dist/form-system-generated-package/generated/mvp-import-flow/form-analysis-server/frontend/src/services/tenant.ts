export const TENANT_STORAGE_KEY = 'form_analysis_tenant_id'

const API_BASE_URL = (import.meta.env?.VITE_API_URL as string) || ''

import { getAdminApiKeyValue } from './adminAuth'
import { getAdminApiKeyHeaderName } from './adminAuth'
import i18n from '../i18n'

type TenantRow = {
  id: string
  name?: string
  code?: string
  is_active?: boolean
}

type ToastType = 'info' | 'error' | 'success'

type EnsureTenantIdOptions = {
  notify?: boolean
  reason?: 'bootstrap' | 'recovery'
  /**
   * Whether to allow using admin privileges to create a default tenant when none exist.
   * Defaults to false to avoid surprising admin actions during normal browsing.
   */
  allowAdminBootstrap?: boolean
}

function emitToast(type: ToastType, message: string): void {
  try {
    window.dispatchEvent(new CustomEvent('app:toast', { detail: { type, message } }))
  } catch {
    // ignore
  }
}

let inFlight: Promise<string> | null = null
let validatedTenantId: string | null = null

function getStoredTenantId(): string {
  return window.localStorage.getItem(TENANT_STORAGE_KEY) || ''
}

function setStoredTenantId(id: string): void {
  if (id) {
    window.localStorage.setItem(TENANT_STORAGE_KEY, id)
    validatedTenantId = id
  }
}

function clearStoredTenantId(): void {
  window.localStorage.removeItem(TENANT_STORAGE_KEY)
  validatedTenantId = null
}

export function setTenantId(id: string): void {
  setStoredTenantId(id)
}

export function clearTenantId(): void {
  clearStoredTenantId()
}

export function getTenantId(): string {
  return getStoredTenantId()
}

/**
 * Ensure a tenant id exists in localStorage.
 * - If one is already stored, returns it.
 * - If none is stored and backend returns exactly one tenant, auto-select it.
 * - If multiple tenants exist, returns empty string (caller must rely on UI selection).
 */
export async function ensureTenantId(): Promise<string> {
  return ensureTenantIdWithOptions()
}

export async function ensureTenantIdWithOptions(options?: EnsureTenantIdOptions): Promise<string> {
  const tenantsUrl = API_BASE_URL ? `${API_BASE_URL}/api/tenants` : '/api/tenants'
  const existing = getStoredTenantId()
  let prefetchedTenants: TenantRow[] | null = null
  let expiredDetected = false
  const notify = options?.notify === true
  const reason = options?.reason ?? 'bootstrap'
  const allowAdminBootstrap = options?.allowAdminBootstrap === true

  const notifyExpiredRecovered = (mode: 'reconnected' | 'recreated') => {
    if (!notify && !expiredDetected) return
    if (mode === 'recreated') {
      emitToast('success', i18n.t('tenant.toast.resetRecreated', { code: 'UT' }))
      return
    }
    emitToast('info', i18n.t('tenant.toast.resetReconnected'))
  }
  if (existing) {
    if (validatedTenantId === existing) return existing

    // The backend DB can be recreated/reset while the browser keeps localStorage.
    // Validate the stored tenant id against /api/tenants; if missing, re-bootstrap.
    try {
      const res = await fetch(tenantsUrl)
      if (res.ok) {
        const tenants = (await res.json()) as TenantRow[]
        if (Array.isArray(tenants)) {
          const found = tenants.some((t) => String(t?.id || '') === existing)
          if (found) {
            validatedTenantId = existing
            return existing
          }

          // Stored id is stale. Clear it and fall through to normal bootstrap.
          expiredDetected = true
          clearStoredTenantId()

          prefetchedTenants = tenants

          if (tenants.length === 1 && tenants[0]?.id) {
            const id = String(tenants[0].id)
            setStoredTenantId(id)
            notifyExpiredRecovered('reconnected')
            return id
          }
          if (tenants.length > 1) {
            // Ambiguous; let caller/UI handle tenant selection.
            if (notify || reason === 'recovery') {
              emitToast('error', i18n.t('tenant.toast.resetMultipleTenants'))
            }
            return ''
          }
          // tenants.length === 0 -> fall through to create.
        }
      }
    } catch {
      // If we can't validate (network/server down), keep the stored value.
      return existing
    }
  }

  if (!inFlight) {
    inFlight = (async () => {
      try {
        const tenants =
          prefetchedTenants ??
          (await (async () => {
            const res = await fetch(tenantsUrl)
            if (!res.ok) return null
            return (await res.json()) as TenantRow[]
          })())

        if (!tenants || !Array.isArray(tenants)) return ''

        if (Array.isArray(tenants) && tenants.length === 0) {
          // No tenants exist yet; create a default tenant for local/dev bootstrap.
          // This requires admin privileges.
          const adminKey = getAdminApiKeyValue()
          if (!allowAdminBootstrap || !adminKey) {
            if (notify || reason === 'recovery') {
              emitToast('error', i18n.t('tenant.toast.noTenantsNeedAdmin'))
            }
            return ''
          }
          const createUrl = API_BASE_URL ? `${API_BASE_URL}/api/tenants` : '/api/tenants'
          const createRes = await fetch(createUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              [getAdminApiKeyHeaderName()]: adminKey,
            },
            body: JSON.stringify({ name: 'UT', code: 'ut', is_default: true, is_active: true }),
          })

          if (createRes.ok) {
            const created = (await createRes.json()) as TenantRow
            if (created?.id) {
              const id = String(created.id)
              setStoredTenantId(id)
              notifyExpiredRecovered('recreated')
              return id
            }
          } else {
            // If creation failed (e.g. race/409), re-fetch once.
            const retry = await fetch(tenantsUrl)
            if (retry.ok) {
              const retryTenants = (await retry.json()) as TenantRow[]
              if (Array.isArray(retryTenants) && retryTenants.length === 1 && retryTenants[0]?.id) {
                const id = String(retryTenants[0].id)
                setStoredTenantId(id)
                notifyExpiredRecovered('reconnected')
                return id
              }
            }
          }
          return ''
        }
        if (Array.isArray(tenants) && tenants.length === 1 && tenants[0]?.id) {
          const id = String(tenants[0].id)
          setStoredTenantId(id)
          if (reason === 'recovery') notifyExpiredRecovered('reconnected')
          return id
        }
        return ''
      } catch {
        return ''
      } finally {
        inFlight = null
      }
    })()
  }

  return inFlight
}
