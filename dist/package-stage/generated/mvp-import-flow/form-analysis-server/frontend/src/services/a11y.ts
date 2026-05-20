export type FontScaleId = 'sm' | 'md' | 'lg'

const FONT_SCALE_STORAGE_KEY = 'FORM_A11Y_FONT_SCALE'

const FONT_SCALES: Record<FontScaleId, number> = {
  sm: 0.9,
  md: 1.0,
  lg: 1.15,
}

export function getFontScaleId(): FontScaleId {
  const raw = String(window.localStorage.getItem(FONT_SCALE_STORAGE_KEY) || '').trim().toLowerCase()
  if (raw === 'sm' || raw === 'md' || raw === 'lg') return raw
  return 'md'
}

export function applyFontScale(id: FontScaleId): void {
  const scale = FONT_SCALES[id] ?? 1.0
  document.documentElement.style.setProperty('--font-scale', String(scale))
  document.documentElement.setAttribute('data-font-scale', id)
}

export function setFontScaleId(id: FontScaleId): void {
  window.localStorage.setItem(FONT_SCALE_STORAGE_KEY, id)
  applyFontScale(id)
}

export function initA11yFromStorage(): void {
  try {
    applyFontScale(getFontScaleId())
  } catch {
    // ignore
  }
}
