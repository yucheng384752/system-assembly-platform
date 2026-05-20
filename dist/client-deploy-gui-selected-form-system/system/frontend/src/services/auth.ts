export const API_KEY_STORAGE_KEY = 'form_analysis_api_key'

function _getEnvString(key: 'VITE_API_KEY' | 'VITE_API_KEY_HEADER'): string {
  // Test hook: vitest/jsdom cannot reliably mutate import.meta.env at runtime.
  // Allow a global override for unit tests without affecting production.
  try {
    const override = (globalThis as any)?.__FORM_ANALYSIS_ENV__?.[key]
    if (typeof override === 'string') return override
  } catch {
    // ignore
  }

  try {
    const v = (import.meta.env as any)?.[key]
    return typeof v === 'string' ? v : ''
  } catch {
    return ''
  }
}

export function getApiKeyHeaderName(): string {
  const envHeader = _getEnvString('VITE_API_KEY_HEADER')
  return envHeader.trim() || 'X-API-Key'
}

export function getApiKeyValue(): string {
  try {
    const stored = window.localStorage.getItem(API_KEY_STORAGE_KEY) || ''
    if (stored.trim()) return stored.trim()
  } catch {
    // ignore
  }

  const envKey = _getEnvString('VITE_API_KEY')
  return envKey.trim()
}

export function setApiKeyValue(rawKey: string): void {
  const value = String(rawKey || '').trim()
  try {
    if (!value) {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(API_KEY_STORAGE_KEY, value)
  } catch {
    // ignore
  }
}

export function clearApiKeyValue(): void {
  try {
    window.localStorage.removeItem(API_KEY_STORAGE_KEY)
  } catch {
    // ignore
  }
}
