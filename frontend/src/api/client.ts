import type {
  CalculateResponse,
  ChatResponse,
  ChatStreamEvent,
  WellParams,
  OptimizationResult,
  MatchingResult,
  BatchResult,
  ScanResult,
  ServerFileEntry,
} from '../types/well'
import { loadAppSettings } from '../utils/storage'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

function buildRuntimeHeaders(): Record<string, string> {
  const cfg = loadAppSettings()
  const headers: Record<string, string> = {}
  if (cfg.api_key.trim()) headers['X-LLM-Api-Key'] = cfg.api_key.trim()
  if (cfg.base_url.trim()) headers['X-LLM-Base-Url'] = cfg.base_url.trim()
  if (cfg.model.trim()) headers['X-LLM-Model'] = cfg.model.trim()
  if (cfg.audio_mode) headers['X-Audio-Mode'] = cfg.audio_mode
  if (cfg.pdf_ocr_mode) headers['X-PDF-OCR-Mode'] = cfg.pdf_ocr_mode
  return headers
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...buildRuntimeHeaders(),
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
    const parts =
      typeof body === 'object' && body !== null
        ? Array.from(
            new Set(
              [body.message, body.description, body.detail]
                .map((x) => (typeof x === 'string' ? x.trim() : ''))
                .filter(Boolean),
            ),
          )
        : []
    const detail = parts.length > 0 ? parts.join(': ') : String(body || `HTTP ${response.status}`)
    throw new Error(detail || `HTTP ${response.status}`)
  }
  if (!contentType.includes('application/json')) throw new Error('Сервер вернул ответ не в формате JSON')
  return body as T
}

async function downloadFile(path: string, payload: unknown, fallbackName: string) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...buildRuntimeHeaders() },
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

export const api = {
  calculate: (params: WellParams) => request<CalculateResponse>('/api/calculate', { method: 'POST', body: JSON.stringify(params) }),
  presets: () => request<Array<{ id: string; name: string; description: string; data: WellParams }>>('/api/presets'),
  chatStatus: () => request<{ available: boolean; message?: string }>('/api/chat/status'),
  chat: (message: string, params: WellParams | undefined, session_id: string | undefined) => {
    const cfg = loadAppSettings()
    return request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        params,
        session_id,
        llm_config: cfg.api_key.trim() ? cfg : undefined,
      }),
    })
  },
  chatStream: async (
    message: string,
    params: WellParams | undefined,
    session_id: string | undefined,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<ChatResponse> => {
    const cfg = loadAppSettings()
    let response: Response
    try {
      response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: 'POST',
        signal,
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...buildRuntimeHeaders(),
        },
        body: JSON.stringify({
          message,
          params,
          session_id,
          llm_config: cfg.api_key.trim() ? cfg : undefined,
        }),
      })
    } catch (err) {
      const raw = err instanceof Error ? err.message : ''
      if (/load failed|failed to fetch|networkerror/i.test(raw)) {
        throw new Error('Соединение с сервером прервано или превышено время ожидания.')
      }
      throw err
    }
    if (!response.ok) {
      const txt = await response.text()
      throw new Error(txt || `HTTP ${response.status}`)
    }
    if (!response.body) {
      return api.chat(message, params, session_id)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let finalDone: ChatResponse | null = null

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.replace(/\r\n/g, '\n').split('\n\n')
      buffer = chunks.pop() ?? ''
      for (const block of chunks) {
        const lines = block
          .split('\n')
          .map((l) => l.trim())
          .filter((l) => l.startsWith('data:'))
        for (const line of lines) {
          const jsonStr = line.slice(5).trim()
          if (!jsonStr) continue
          try {
            const evt = JSON.parse(jsonStr) as ChatStreamEvent
            onEvent(evt)
            if (evt.type === 'done') {
              finalDone = {
                available: Boolean(evt.available),
                text: evt.text ?? '',
                session_id: evt.session_id ?? session_id ?? '',
                tool_trace: evt.tool_trace ?? [],
                calculation_result: evt.calculation_result ?? null,
                params: evt.params ?? null,
              }
            }
          } catch {
            // ignore malformed chunk
          }
        }
      }
    }

    if (finalDone) return finalDone
    throw new Error('Поток ответа завершился без финального блока')
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
      stored_file_id?: string | null
      ocr_method?: string | null
      wells?: Array<{ filename: string; parsed_params?: Partial<WellParams> | null; extracted_values?: Record<string, unknown> }>
    }>('/api/chat/upload', { method: 'POST', body: form })
  },
  visionUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; extracted_params: WellParams; filename: string; method: string }>('/api/enhancements/vision', {
      method: 'POST',
      body: form,
    })
  },
  audioUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; transcript: string; engine?: string; extracted_parameters: WellParams | null }>(
      '/api/enhancements/audio',
      { method: 'POST', body: form },
    )
  },
  mcpFiles: () => request<{ count: number; files: ServerFileEntry[] }>('/api/mcp/files'),
  mcpTools: () => request<{ server: string; tools: Array<{ name: string; description: string }> }>('/api/mcp/tools'),

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
