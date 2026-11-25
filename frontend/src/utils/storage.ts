const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30 // 30 дней

export type AudioMode = 'auto' | 'whisper' | 'multimodal'
export type PdfOcrMode = 'auto' | 'tesseract' | 'vision'

export interface AppSettings {
  api_key: string
  base_url: string
  model: string
  audio_mode: AudioMode
  pdf_ocr_mode: PdfOcrMode
}

export const DEFAULT_APP_SETTINGS: AppSettings = {
  api_key: '',
  base_url: 'https://openrouter.ai/api/v1',
  model: 'openai/gpt-4o-mini',
  audio_mode: 'auto',
  pdf_ocr_mode: 'auto',
}

const SETTINGS_COOKIE_KEY = 'wmb_ai_settings'
const SETTINGS_STORAGE_KEY = 'wmb_ai_settings'

export function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const prefix = `${encodeURIComponent(name)}=`
  for (const part of document.cookie.split('; ')) {
    if (part.startsWith(prefix)) {
      try {
        return decodeURIComponent(part.slice(prefix.length))
      } catch {
        return null
      }
    }
  }
  return null
}

export function setCookie(name: string, value: string, maxAgeSeconds = COOKIE_MAX_AGE_SECONDS): void {
  if (typeof document === 'undefined') return
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax`
}

export function deleteCookie(name: string): void {
  if (typeof document === 'undefined') return
  document.cookie = `${encodeURIComponent(name)}=; path=/; max-age=0; SameSite=Lax`
}

export function loadJson<T>(key: string, fallback: T, validate?: (val: unknown) => val is T): T {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    const parsed: unknown = JSON.parse(raw)
    if (validate && !validate(parsed)) return fallback
    return parsed as T
  } catch {
    return fallback
  }
}

export function saveJson<T>(key: string, value: T): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Игнорируем переполнение квоты или приватный режим браузера
  }
}

function normalizeSettings(raw: unknown): AppSettings {
  const obj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const audioRaw = obj.audio_mode
  const ocrRaw = obj.pdf_ocr_mode
  return {
    api_key: typeof obj.api_key === 'string' ? obj.api_key : DEFAULT_APP_SETTINGS.api_key,
    base_url: typeof obj.base_url === 'string' && obj.base_url.trim() ? obj.base_url : DEFAULT_APP_SETTINGS.base_url,
    model: typeof obj.model === 'string' && obj.model.trim() ? obj.model : DEFAULT_APP_SETTINGS.model,
    audio_mode: audioRaw === 'whisper' || audioRaw === 'multimodal' ? audioRaw : 'auto',
    pdf_ocr_mode: ocrRaw === 'tesseract' || ocrRaw === 'vision' ? ocrRaw : 'auto',
  }
}

export function loadAppSettings(): AppSettings {
  const cookieRaw = getCookie(SETTINGS_COOKIE_KEY)
  if (cookieRaw) {
    try {
      return normalizeSettings(JSON.parse(cookieRaw))
    } catch {
      // fallback to localStorage
    }
  }
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem(SETTINGS_STORAGE_KEY)
      if (stored) {
        return normalizeSettings(JSON.parse(stored))
      }
    } catch {
      // fallback to defaults
    }
  }
  return { ...DEFAULT_APP_SETTINGS }
}

export function saveAppSettings(settings: AppSettings): AppSettings {
  const normalized = normalizeSettings(settings)
  const serialized = JSON.stringify(normalized)
  setCookie(SETTINGS_COOKIE_KEY, serialized, COOKIE_MAX_AGE_SECONDS)
  saveJson(SETTINGS_STORAGE_KEY, normalized)
  return normalized
}

export function resetAppSettings(): AppSettings {
  deleteCookie(SETTINGS_COOKIE_KEY)
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.removeItem(SETTINGS_STORAGE_KEY)
    } catch {
      // ignore
    }
  }
  return { ...DEFAULT_APP_SETTINGS }
}
