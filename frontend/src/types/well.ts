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
  meta?: { calc_time_ms?: number; message?: string }
  warnings?: string[]
  message?: string
  description?: string
}

export interface LLMSettingsConfig {
  base_url: string
  model: string
  api_key: string
}

export interface ServerFileItem {
  name: string
  folder: 'uploads' | 'samples'
  size_bytes: number
  modified_at: string
  has_parsed_params: boolean
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
    p_wh: number
    t_res?: number
    geo_grad: number
    h_res: number
    roughness?: number
    q_max?: number
    points?: number
    inclinometry: { MD: number[]; TVD: number[] }
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

export interface OptimizationResult {
  tubing_optimization?: {
    best_tubing: { name: string; d_m: number; operating_point: OperatingPoint | null }
    recommendation: string
    scenarios: Array<{ tubing_name: string; d_m: number; status: string; operating_point: OperatingPoint | null; reason?: string }>
  }
  wellhead_sensitivity?: {
    optimal_p_wh: number
    max_flow_rate: number
    recommendation: string
    sensitivity_curve: Array<{ p_wh: number; q_liq?: number; p_wf?: number; status: string; reason?: string }>
  }
  critical_wct?: {
    current_wct: number
    critical_wct: number | null
    summary: string
    curve: Array<{ wct: number; status: string; q_liq?: number; p_wf?: number }>
  }
}

export interface MatchingResult {
  status: string
  comparison: {
    measured: { q_liq: number; p_wf?: number | null }
    model: { q_liq: number; p_wf: number }
    deltas: { delta_q_liq_m3_day: number; delta_q_liq_percent: number; delta_p_wf_atm: number | null; delta_p_wf_percent: number | null }
  }
  diagnosis: string[]
  recommendations: string[]
  calibrated_parameters: { base_pi: number; recommended_pi: number | null; formula: string | null }
}

export interface BatchSummary {
  total_wells: number
  flowing_wells: number
  killed_wells: number
  error_wells: number
  flowing_factor_pct: number
  total_q_liq_m3_day: number
  total_q_oil_m3_day: number
  average_flowing_p_wf_atm: number | null
}

export interface BatchResult {
  status: string
  batch_time: string
  summary: BatchSummary
  wells_data: Array<{ id: string; name: string; status: string; q_liq_m3_day: number; q_oil_m3_day: number; p_wf_atm: number | null; wct_pct: number; error?: string | null }>
}

export interface ScannedWell {
  filename: string
  relative_path: string
  well_name: string
  format: string
  size_bytes: number
  is_ready_for_calc: boolean
  validation_status: string
  extracted_parameters: WellParams | null
}

export interface ScanResult {
  status: string
  scanned_directory: string
  total_files_found: number
  ready_for_calculation: number
  wells: ScannedWell[]
}
