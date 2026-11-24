export interface Curve {
  q_liq: number[]
  p_wf: number[]
}

export interface OperatingPoint {
  q_liq: number
  p_wf: number
}

export interface CalculateResponse {
  ipr: Curve
  vlp: Curve
  operating_point: OperatingPoint | null
  meta?: { calc_time_ms?: number }
  message?: string
  description?: string
}

export interface WellParams {
  ipr: Record<string, unknown>
  vlp: Record<string, unknown>
}

export interface ChatResponse {
  available: boolean
  text: string
  session_id: string
  tool_trace: Array<{
    step: number
    tool: string
    args: Record<string, unknown>
    status: string
    duration_ms: number
    result?: unknown
  }>
  calculation_result?: CalculateResponse | null
}
