export interface Curve {
  q_liq: number[]
  p_wf: number[]
}

export interface OperatingPoint {
  q_liq: number
  p_wf: number
}

export interface CalculateResponse {
  status?: string
  ipr: Curve
  vlp: Curve
  operating_point: OperatingPoint | null
  meta?: {
    calc_time_ms?: number
    message?: string
  }
  message?: string
  description?: string
}

export interface WellParams {
  ipr: {
    p_res: number
    wct: number
    pi: number
    pb: number
    points?: number
    [key: string]: unknown
  }
  vlp: {
    inclinometry: {
      MD: number[]
      TVD: number[]
    }
    casing: { d: number }
    tubing: { d: number; h_mes: number }
    pvt: {
      wct: number
      rp: number
      gamma_oil: number
      gamma_gas: number
      gamma_wat: number
      t_res?: number
    }
    p_wh: number
    geo_grad: number
    h_res: number
    t_res?: number
    roughness?: number
    q_max?: number
    points?: number
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface PresetItem {
  id: string
  name: string
  description: string
  data: WellParams
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
