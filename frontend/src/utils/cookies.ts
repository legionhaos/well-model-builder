/** Persistent client storage using 30-day cookies with localStorage fallback for oversized payloads. */

const DEFAULT_DAYS = 30

export function setCookie(name: string, value: string, days = DEFAULT_DAYS): void {
  if (typeof document === 'undefined') return
  const maxAge = Math.max(1, Math.floor(days * 24 * 60 * 60))
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; max-age=${maxAge}; path=/; SameSite=Lax`
}

export function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const prefix = `${encodeURIComponent(name)}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      try {
        return decodeURIComponent(trimmed.slice(prefix.length))
      } catch {
        return null
      }
    }
  }
  return null
}

export function deleteCookie(name: string): void {
  if (typeof document === 'undefined') return
  document.cookie = `${encodeURIComponent(name)}=; max-age=0; path=/; SameSite=Lax`
}

export function savePersistedJson(key: string, data: unknown, days = DEFAULT_DAYS): void {
  try {
    const serialized = JSON.stringify(data)
    if (encodeURIComponent(serialized).length <= 3600) {
      setCookie(key, serialized, days)
    } else {
      deleteCookie(key)
    }
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(key, serialized)
    }
  } catch {
    // Ignore storage quota errors
  }
}

export function loadPersistedJson<T>(key: string): T | null {
  const cookieVal = getCookie(key)
  if (cookieVal) {
    try {
      return JSON.parse(cookieVal) as T
    } catch {
      // fallback to localStorage
    }
  }
  try {
    if (typeof localStorage !== 'undefined') {
      const lsVal = localStorage.getItem(key)
      if (lsVal) return JSON.parse(lsVal) as T
    }
  } catch {
    // Ignore parse errors
  }
  return null
}

export function clearPersistedJson(key: string): void {
  deleteCookie(key)
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(key)
    }
  } catch {
    // Ignore
  }
}
