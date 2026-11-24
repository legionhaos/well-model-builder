import type { CalculateResponse, ChatResponse, PresetItem, WellParams } from '../types/well'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...init?.headers },
  })
  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null
      ? [body.message, body.description, body.detail].filter(Boolean).join(': ')
      : String(body || `HTTP ${response.status}`)
    throw new Error(detail || `HTTP ${response.status}`)
  }
  if (!contentType.includes('application/json')) throw new Error('Сервер вернул ответ не в формате JSON')
  return body as T
}

export const api = {
  calculate: (params: WellParams) => request<CalculateResponse>('/api/calculate', { method: 'POST', body: JSON.stringify(params) }),
  presets: () => request<PresetItem[]>('/api/presets'),
  chatStatus: () => request<{ available: boolean; message?: string }>('/api/chat/status'),
  chat: (message: string, params: WellParams | undefined, session_id: string | undefined) =>
    request<ChatResponse>('/api/chat', { method: 'POST', body: JSON.stringify({ message, params, session_id }) }),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ filename: string; text: string; sources: string[]; extracted_values: Record<string, unknown> }>('/api/chat/upload', { method: 'POST', body: form })
  },
}
