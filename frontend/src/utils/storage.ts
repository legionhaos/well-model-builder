const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30 // 30 дней

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
