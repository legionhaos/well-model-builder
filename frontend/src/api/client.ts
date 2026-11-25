import type {
  CalculateResponse,
  ChatResponse,
  WellParams,
  OptimizationResult,
  MatchingResult,
  BatchResult,
  ScanResult,
} from '../types/well'

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

export const api = {
  calculate: (params: WellParams) => request<CalculateResponse>('/api/calculate', { method: 'POST', body: JSON.stringify(params) }),
  presets: () => request<Array<{ id: string; name: string; description: string; data: WellParams }>>('/api/presets'),
  chatStatus: () => request<{ available: boolean; message?: string }>('/api/chat/status'),
  chat: (message: string, params: WellParams | undefined, session_id: string | undefined) =>
    request<ChatResponse>('/api/chat', { method: 'POST', body: JSON.stringify({ message, params, session_id }) }),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ filename: string; text: string; sources: string[]; extracted_values: Record<string, unknown>; parsed_params?: Partial<WellParams> | null }>('/api/chat/upload', { method: 'POST', body: form })
  },
  visionUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; extracted_params: WellParams; filename: string; method: string }>('/api/enhancements/vision', { method: 'POST', body: form })
  },
  audioUpload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ status: string; transcript: string; extracted_parameters: WellParams | null }>('/api/enhancements/audio', { method: 'POST', body: form })
  },
  // 05: Engineering report exports
  reportMarkdown: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    request<{ well_name: string; markdown: string }>('/api/enhancements/report/markdown', { method: 'POST', body: JSON.stringify({ well_name, params, calculation_result }) }),
  downloadReportHtml: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    downloadFile('/api/enhancements/report/html', { well_name, params, calculation_result }, `well_report_${well_name.replace(/\s+/g, '_')}.html`),
  downloadReportExcel: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    downloadFile('/api/enhancements/report/excel', { well_name, params, calculation_result }, `well_report_${well_name.replace(/\s+/g, '_')}.xlsx`),
  downloadReportCsv: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    downloadFile('/api/enhancements/report/csv', { well_name, params, calculation_result }, `well_report_${well_name.replace(/\s+/g, '_')}.csv`),
  getReportJson: (well_name: string, params: WellParams, calculation_result: CalculateResponse) =>
    request<Record<string, unknown>>('/api/enhancements/report/json', { method: 'POST', body: JSON.stringify({ well_name, params, calculation_result }) }),

  // 06: File scanning
  scanFolder: (folder_path = 'samples', recursive = true) =>
    request<ScanResult>('/api/enhancements/scan', { method: 'POST', body: JSON.stringify({ folder_path, recursive }) }),
  optimize: (params: WellParams, optimization_type = 'all') =>
    request<{ status: string; results: OptimizationResult }>('/api/enhancements/optimize', { method: 'POST', body: JSON.stringify({ params, optimization_type }) }),
  matchMeasurement: (params: WellParams, measured_q_liq: number, measured_p_wf?: number) =>
    request<MatchingResult>('/api/enhancements/match', { method: 'POST', body: JSON.stringify({ params, measured_q_liq, measured_p_wf }) }),
  meetingProtocol: (transcript: string) =>
    request<{ status: string; well_name: string; date: string; protocol_markdown: string }>('/api/enhancements/protocol', { method: 'POST', body: JSON.stringify({ transcript }) }),
  batchCalculate: (wells: Array<{ id: string; name: string; params: WellParams }>) =>
    request<BatchResult>('/api/enhancements/batch', { method: 'POST', body: JSON.stringify({ wells }) }),
  downloadBatchExcel: (wells: Array<{ id: string; name: string; params: WellParams }>) =>
    downloadFile('/api/enhancements/batch/excel', { wells }, 'field_batch_summary.xlsx'),
}
