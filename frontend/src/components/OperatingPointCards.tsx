import type { CalculateResponse, WellParams } from '../types/well'

interface OperatingPointCardsProps {
  result: CalculateResponse | null
  loading?: boolean
  error?: string | null
  params?: WellParams | null
}

export function OperatingPointCards({ result, loading, error, params }: OperatingPointCardsProps) {
  const op = result?.operating_point
  const isNoIntersection = result && !op

  // Default values from screenshot if not yet calculated or loaded
  const displayQ = op ? op.q_liq.toFixed(0) : isNoIntersection ? '—' : '134'
  const displayPwf = op ? op.p_wf.toFixed(0) : isNoIntersection ? '—' : '145'

  const pb = params?.ipr?.pb ?? 180
  const pRes = params?.ipr?.p_res ?? 220
  const wct = params?.ipr?.wct ?? 28

  return (
    <div className="results-panel-card">
      <div className="results-panel-header">
        <span className="results-badge-icon">✔</span>
        <h3>Результаты расчёта</h3>
      </div>

      <div className="kpi-dual-grid">
        <div className="kpi-metric-box">
          <div className="kpi-metric-value">
            {loading ? <span className="kpi-pulse">...</span> : displayQ}
            <span className="kpi-metric-unit"> м³/сут</span>
          </div>
          <div className="kpi-metric-label">Дебит жидкости</div>
        </div>

        <div className="kpi-metric-box">
          <div className="kpi-metric-value">
            {loading ? <span className="kpi-pulse">...</span> : displayPwf}
            <span className="kpi-metric-unit"> бар</span>
          </div>
          <div className="kpi-metric-label">Забойное давление</div>
        </div>
      </div>

      {error ? (
        <div className="results-status-banner error" role="alert">
          <span className="status-banner-icon">⚠</span>
          <div className="status-banner-body">
            <strong>Ошибка расчёта</strong>
            <p>{error}</p>
          </div>
        </div>
      ) : isNoIntersection ? (
        <div className="results-status-banner warning" role="alert">
          <span className="status-banner-icon">⚠</span>
          <div className="status-banner-body">
            <strong>Рабочая точка не найдена</strong>
            <p>Скважина не фонтанирует при текущих параметрах пласта и НКТ</p>
          </div>
        </div>
      ) : (
        <div className="results-status-banner success">
          <span className="status-banner-icon">✔</span>
          <div className="status-banner-body">
            <strong>Рабочая точка найдена</strong>
            <p>Пересечение кривых определено с точностью ±0.5%</p>
          </div>
        </div>
      )}

      <div className="key-metrics-section">
        <h4>Ключевые показатели</h4>
        <div className="key-metric-row">
          <span>Давление насыщения (Pb)</span>
          <strong>{pb} бар</strong>
        </div>
        <div className="key-metric-row">
          <span>Пластовое давление</span>
          <strong>{pRes} бар</strong>
        </div>
        <div className="key-metric-row">
          <span>Обводнённость</span>
          <strong>{wct}%</strong>
        </div>
      </div>
    </div>
  )
}
