import type {
  CalculateResponse,
  ChatResponse,
  WellParams,
  OptimizationResult,
  MatchingResult,
  BatchResult,
  ScanResult,
  LLMSettingsConfig,
  ServerFileItem,
} from '../types/well'
import { loadPersistedJson } from '../utils/cookies'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export const LLM_SETTINGS_COOKIE_KEY = 'wmb_llm_config'

function buildLlmHeaders(override?: Partial<LLMSettingsConfig>): Record<string, string> {
  const saved = override ?? loadPersistedJson<LLMSettingsConfig>(LLM_SETTINGS_COOKIE_KEY)
  const headers: Record<string, string> = {}
  if (saved?.base_url?.trim()) headers['X-LLM-Base-Url'] = saved.base_url.trim()
  if (saved?.model?.trim()) headers['X-LLM-Model'] = saved.model.trim()
  if (saved?.api_key?.trim()) headers['X-LLM-Api-Key'] = saved.api_key.trim()
  return headers
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    })
  } catch (err) {
    const raw = err instanceof Error ? err.message : ''
    if (/load failed|failed to fetch|networkerror/i.test(raw)) {
      throw new Error('Соединение с сервером прервано или превышено время ожидания. Попробуйте ещё раз.')
    }
    throw err
  }
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

async function downloadFile(path: string, payload: unknown, fallbackName: string) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(`Ошибка выгрузки: HTTP ${response.status}`)
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

export type StreamCallbacks = {
  onStatus?: (message: string, sessionId?: string) => void
  onTool?: (entry: { step: number; tool: string; status: string; duration_ms: number }) => void
  onDelta?: (chunk: string) => void
  onDone?: (response: ChatResponse) => void
}

export const api = {
  calculate: (params: WellParams) =>
    request<CalculateResponse>('/api/calculate', { method: 'POST', body: JSON.stringify(params) }),
  presets: () =>
    request<Array<{ id: string; name: string; description: string; data: WellParams }>>('/api/presets'),
  chatStatus: (override?: Partial<LLMSettingsConfig>) =>
    request<{ available: boolean; message?: string }>('/api/chat/status', {
      headers: buildLlmHeaders(override),
    }),
  chat: (message: string, params: WellParams | undefined, session_id: string | undefined) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      headers: buildLlmHeaders(),
      body: JSON.stringify({ message, params, session_id }),
    }),
  chatStream: async (
    message: string,
    params: WellParams | undefined,
    session_id: string | undefined,
    callbacks: StreamCallbacks,
  ): Promise<ChatResponse> => {
    let response: Response
    try {
      response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...buildLlmHeaders() },
        body: JSON.stringify({ message, params, session_id }),
      })
    } catch (err) {
      const raw = err instanceof Error ? err.message : ''
      if (/load failed|failed to fetch|networkerror/i.test(raw)) {
        throw new Error('Соединение с сервером прервано или превышено время ожидания. Попробуйте ещё раз.')
      }
      throw err
    }
    if (!response.ok || !response.body) {
      return api.chat(message, params, session_id)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalResponse: ChatResponse | null = null

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''

      for (const rawEvent of events) {
        const line = rawEvent
          .split('\n')
          .find((l) => l.startsWith('data:'))
        if (!line) continue
        const jsonStr = line.slice(5).trim()
        if (!jsonStr) continue
        let ev: any
        try {
          ev = JSON.parse(jsonStr)
        } catch {
          continue
        }
        if (ev.type === 'status') {
          callbacks.onStatus?.(ev.message, ev.session_id)
        } else if (ev.type === 'tool') {
          callbacks.onTool?.(ev)
        } else if (ev.type === 'delta' && typeof ev.chunk === 'string') {
          callbacks.onDelta?.(ev.chunk)
        } else if (ev.type === 'done') {
          finalResponse = {
            available: Boolean(ev.available),
            text: String(ev.text ?? ''),
            session_id: String(ev.session_id ?? session_id ?? ''),
            tool_trace: Array.isArray(ev.tool_trace) ? ev.tool_trace : [],
            calculation_result: ev.calculation_result ?? null,
          }
          callbacks.onDone?.(finalResponse)
        }
      }
    }

    if (!finalResponse) {
      throw new Error('Поток ответа завершился неожиданно')
    }
    return finalResponse
  },
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{
      filename: string
      text: string
      sources: string[]
      extracted_values: Record<string, unknown>
      parsed_params?: Partial<WellParams> | null
    }>('/api/chat/upload', {
      method: 'POST',
      headers: buildLlmHeaders(),
      body: form,
    })
  },
  serverFiles: () => request<{ files: ServerFileItem[] }>('/api/chat/files'),
  readServerFile: (folder: 'uploads' | 'samples', name: string) =>
    request<{
      filename: string
      folder: string
      text: string
      sources: string[]
      extracted_values: Record<string, unknown>
      parsed_params?: Partial<WellParams> | null
    }>(`/api/chat/files/${folder}/${encodeURIComponent(name)}`),
  visionUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; extracted_params: WellParams | null; filename: string; method: string; message?: string }>(
      '/api/enhancements/vision',
      { method: 'POST', headers: buildLlmHeaders(), body: form },
    )
  },
  audioUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; transcript: string; extracted_parameters: WellParams | null; message?: string }>(
      '/api/enhancements/audio',
      { method: 'POST', headers: buildLlmHeaders(), body: form },
    )
  },
  // 05: Engineering report exports
  reportMarkdown: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    request<{ well_name: string; markdown: string }>('/api/enhancements/report/markdown', {
      method: 'POST',
      body: JSON.stringify({ well_name, params, calculation_result }),
    }),
  downloadReportHtml: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    downloadFile('/api/enhancements/report/html', { well_name, params, calculation_result }, `well_report_${well_name.replace(/\s+/g, '_')}.html`),
  downloadReportExcel: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    downloadFile('/api/enhancements/report/excel', { well_name, params, calculation_result }, `well_report_${well_name.replace(/\s+/g, '_')}.xlsx`),
  downloadReportCsv: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    downloadFile('/api/enhancements/report/csv', { well_name, params, calculation_result }, `well_report_${well_name.replace(/\s+/g, '_')}.csv`),
  getReportJson: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    request<Record<string, unknown>>('/api/enhancements/report/json', {
      method: 'POST',
      body: JSON.stringify({ well_name, params, calculation_result }),
    }),

  // 06: File scanning
  scanFolder: (folder_path = 'samples', recursive = true) =>
    request<ScanResult>('/api/enhancements/scan', { method: 'POST', body: JSON.stringify({ folder_path, recursive }) }),
  optimize: (params: WellParams, optimization_type = 'all') =>
    request<{ status: string; results: OptimizationResult }>('/api/enhancements/optimize', {
      method: 'POST',
      body: JSON.stringify({ params, optimization_type }),
    }),
  matchMeasurement: (params: WellParams, measured_q_liq: number, measured_p_wf?: number) =>
    request<MatchingResult>('/api/enhancements/match', {
      method: 'POST',
      body: JSON.stringify({ params, measured_q_liq, measured_p_wf }),
    }),
  meetingProtocol: (transcript: string) =>
    request<{ status: string; well_name: string; date: string; protocol_markdown: string }>('/api/enhancements/protocol', {
      method: 'POST',
      body: JSON.stringify({ transcript }),
    }),
  batchCalculate: (wells: Array<{ id: string; name: string; params: WellParams }>) =>
    request<BatchResult>('/api/enhancements/batch', { method: 'POST', body: JSON.stringify({ wells }) }),
  downloadBatchExcel: (wells: Array<{ id: string; name: string; params: WellParams }>) =>
    downloadFile('/api/enhancements/batch/excel', { wells }, 'field_batch_summary.xlsx'),
}
