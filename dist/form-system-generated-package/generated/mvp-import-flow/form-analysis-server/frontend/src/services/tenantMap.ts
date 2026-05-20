export type TenantMapEntry = { name?: string; code?: string }

export const TENANT_MAP_STORAGE_KEY = 'form_analysis_tenant_map_v1'

export function readTenantMap(): Record<string, TenantMapEntry> {
  try {
    const raw = window.localStorage.getItem(TENANT_MAP_STORAGE_KEY) || ''
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Record<string, TenantMapEntry>
  } catch {
    return {}
  }
}

export function writeTenantMap(rows: Array<{ id: string; name?: string; code?: string }>): void {
  try {
    const map: Record<string, TenantMapEntry> = {}
    for (const t of rows || []) {
      const id = String((t as any)?.id || '').trim()
      if (!id) continue

      const entry: TenantMapEntry = {}
      if (typeof t?.name === 'string' && t.name.trim()) entry.name = t.name
      if (typeof t?.code === 'string' && t.code.trim()) entry.code = t.code
      map[id] = entry
    }
    window.localStorage.setItem(TENANT_MAP_STORAGE_KEY, JSON.stringify(map))
  } catch {
    // ignore
  }
}

export function getTenantLabelById(tenantId: string | null | undefined): string {
  const id = String(tenantId || '').trim()
  if (!id) return ''

  const entry = readTenantMap()[id]
  const code = typeof entry?.code === 'string' ? entry.code.trim() : ''

  // UX: always show the short area code only (e.g., UT)
  return code || ''
}
