export const ADMIN_API_KEY_STORAGE_KEY = 'form_analysis_admin_api_key'
export const ADMIN_UNLOCKED_SESSION_KEY = 'form_analysis_admin_unlocked'

export function getAdminApiKeyHeaderName(): string {
  return 'X-Admin-API-Key'
}

export function getAdminApiKeyValue(): string {
  try {
    const sessionValue = window.sessionStorage.getItem(ADMIN_API_KEY_STORAGE_KEY) || ''
    if (sessionValue.trim()) return sessionValue.trim()

    const stored = window.localStorage.getItem(ADMIN_API_KEY_STORAGE_KEY) || ''
    if (!stored.trim()) return ''

    const migrated = stored.trim()
    window.sessionStorage.setItem(ADMIN_API_KEY_STORAGE_KEY, migrated)
    window.localStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY)
    return migrated
  } catch {
    return ''
  }
}

export function setAdminApiKeyValue(rawKey: string): void {
  const value = String(rawKey || '').trim()
  try {
    if (!value) {
      window.sessionStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY)
      window.localStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY)
      return
    }
    window.sessionStorage.setItem(ADMIN_API_KEY_STORAGE_KEY, value)
    window.localStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY)
  } catch {
    // ignore
  }
}

export function clearAdminApiKeyValue(): void {
  try {
    window.sessionStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY)
    window.localStorage.removeItem(ADMIN_API_KEY_STORAGE_KEY)
  } catch {
    // ignore
  }
}

export function isAdminUnlockedInSession(): boolean {
  try {
    return (window.sessionStorage.getItem(ADMIN_UNLOCKED_SESSION_KEY) || '') === '1'
  } catch {
    return false
  }
}

export function setAdminUnlockedInSession(ok: boolean): void {
  try {
    if (!ok) {
      window.sessionStorage.removeItem(ADMIN_UNLOCKED_SESSION_KEY)
      return
    }
    window.sessionStorage.setItem(ADMIN_UNLOCKED_SESSION_KEY, '1')
  } catch {
    // ignore
  }
}

export function clearAdminUnlockedInSession(): void {
  setAdminUnlockedInSession(false)
}
