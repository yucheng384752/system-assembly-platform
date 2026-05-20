import { ensureTenantIdWithOptions, TENANT_STORAGE_KEY } from './tenant'
import { getApiKeyHeaderName, getApiKeyValue } from './auth'
import { getAdminApiKeyHeaderName } from './adminAuth'
import i18n from '../i18n'

// Global fetch wrapper: auto-inject X-Tenant-Id for all /api* requests except /api/tenants.
// This prevents accidental cross-tenant calls and removes per-call header boilerplate.
export function installGlobalFetchWrapper(): () => void {
  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    try {
      let tenantId = window.localStorage.getItem(TENANT_STORAGE_KEY) || ''
      const apiKeyHeaderName = getApiKeyHeaderName()
      const apiKeyValue = getApiKeyValue()

      // Determine request URL
      const urlString =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url

      const url = new URL(urlString, window.location.href)
      const isApiPath = url.pathname.startsWith('/api')
      const isTenantListPath = url.pathname.startsWith('/api/tenants')
      const isAuthPath = url.pathname.startsWith('/api/auth')

      if (!isApiPath) {
        return originalFetch(input as any, init)
      }

      // Do not auto-inject admin headers globally.
      // Admin-only requests must explicitly set X-Admin-API-Key at call sites after the user
      // deliberately enables admin mode. This avoids surprising "admin parameter" usage on load.
      //
      // We still allow attaching the regular API key when present.
      if (isTenantListPath || isAuthPath) {
        const mergedHeaders = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined))
        const adminHeaderName = getAdminApiKeyHeaderName()
        const hasAdminHeader = Boolean((mergedHeaders.get(adminHeaderName) || '').trim())
        if (apiKeyValue && !hasAdminHeader) {
          mergedHeaders.set(apiKeyHeaderName, apiKeyValue)
        }

        // If no regular API key exists, call as-is.
        if (!apiKeyValue) {
          return originalFetch(input as any, init)
        }

        if (input instanceof Request) {
          // Clone to keep request body reusable.
          const wrappedRequest = new Request(input.clone(), { ...init, headers: mergedHeaders })
          return originalFetch(wrappedRequest)
        }

        return originalFetch(input as any, { ...init, headers: mergedHeaders })
      }

      const attemptFetch = async (forcedTenantId?: string) => {
        const mergedHeaders = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined))
        const explicitTenantId = (mergedHeaders.get('X-Tenant-Id') || '').trim()
        const effectiveTenantId = forcedTenantId ?? (explicitTenantId || tenantId)

        // Hard block tenant-scoped API calls when tenant is not explicitly selected.
        // This prevents silently using a default/guessed tenant.
        // If API key auth is enabled server-side, tenant is bound to the API key,
        // so it's safe to allow requests without X-Tenant-Id when an API key exists.
        if (!effectiveTenantId && !apiKeyValue) {
          return new Response(
            JSON.stringify({
              detail:
                i18n.t('errors.noTenantSelected'),
            }),
            { status: 400, headers: { 'Content-Type': 'application/json' } },
          )
        }

        // Set/override tenant header only when we actually have one.
        if (effectiveTenantId) {
          mergedHeaders.set('X-Tenant-Id', effectiveTenantId)
        }
        if (apiKeyValue) {
          mergedHeaders.set(apiKeyHeaderName, apiKeyValue)
        }

        if (input instanceof Request) {
          // Clone to keep request body reusable.
          const wrappedRequest = new Request(input.clone(), { ...init, headers: mergedHeaders })
          return originalFetch(wrappedRequest)
        }

        return originalFetch(input as any, { ...init, headers: mergedHeaders })
      }

      const res = await attemptFetch()
      if (res.status !== 404) return res

      // Auto-recover from stale tenant id after DB reset/reseed.
      try {
        const data = await res.clone().json().catch(() => null)
        const detail = typeof (data as any)?.detail === 'string' ? (data as any).detail : ''
        if (!detail || !detail.toLowerCase().includes('tenant not found')) {
          return res
        }

        const refreshed = await ensureTenantIdWithOptions({ notify: true, reason: 'recovery' })
        if (!refreshed) return res

        return await attemptFetch(refreshed)
      } catch {
        return res
      }
    } catch {
      // Fallback: never block fetch due to wrapper errors
      return originalFetch(input as any, init)
    }
  }

  return () => {
    window.fetch = originalFetch
  }
}
