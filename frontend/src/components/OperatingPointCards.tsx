import type { CalculateResponse } from '../types/well'

interface OperatingPointCardsProps {
  result: CalculateResponse | null
  loading?: boolean
  error?: string | null
}

export function OperatingPointCards({ result, loading, error }: OperatingPointCardsProps) {
  const op = result?.operating_point
  const isNoIntersection = result && !op
  const calcTime = result?.meta?.calc_time_ms

  return (
    <div className="kpi-container">
      {error && (
        <div className="alert alert-error" role="alert">
          <div className="alert-icon" aria-hidden="true">!</div>
          <div className="alert-content">
            <strong>Ошибка расчета:</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {isNoIntersection && (
        <div className="alert alert-warning" role="alert">
          <div className="alert-icon" aria-hidden="true">!</div>
          <div className="alert-content">
            <strong>Скважина не фонтанирует (рабочая точка не найдена)</strong>
            <p>
              Кривая VLP лежит выше кривой IPR во всем диапазоне дебитов. Пластовой энергии
              недостаточно для подъема флюида на поверхность при текущем устьевом давлении и
              обводненности.
            </p>
          </div>
        </div>
      )}

      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-header">
            <span className="kpi-label">Дебит жидкости (q_liq)</span>
            <span className="kpi-unit">м³/сут</span>
          </div>
          <div className="kpi-value">
            {loading ? (
              <span className="kpi-skeleton" />
            ) : op ? (
              op.q_liq.toFixed(2)
            ) : isNoIntersection ? (
              '—'
            ) : (
              '0.00'
            )}
          </div>
          <div className="kpi-footer">
            {op ? 'Оптимальный приток' : isNoIntersection ? 'Нет притока' : 'Не рассчитано'}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span className="kpi-label">Забойное давление (p_wf)</span>
            <span className="kpi-unit">атм</span>
          </div>
          <div className="kpi-value">
            {loading ? (
              <span className="kpi-skeleton" />
            ) : op ? (
              op.p_wf.toFixed(2)
            ) : isNoIntersection ? (
              '—'
            ) : (
              '0.00'
            )}
          </div>
          <div className="kpi-footer">
            {op ? 'Давление на забое' : isNoIntersection ? 'Срыв подачи' : 'Не рассчитано'}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <span className="kpi-label">Статус системы</span>
            <span className="kpi-unit">Nodal</span>
          </div>
          <div className="kpi-status">
            {loading ? (
              <span className="status-badge status-loading">
                <span className="badge-pulse" /> Расчет...
              </span>
            ) : op ? (
              <span className="status-badge status-success">
                <span className="badge-dot" /> Согласовано
              </span>
            ) : isNoIntersection ? (
              <span className="status-badge status-warning">
                <span className="badge-dot" /> Нет решения
              </span>
            ) : (
              <span className="status-badge status-idle">
                <span className="badge-dot" /> Готов к расчету
              </span>
            )}
          </div>
          <div className="kpi-footer">
            {calcTime !== undefined ? `Время: ${calcTime.toFixed(1)} мс` : 'Автономное ядро'}
          </div>
        </div>
      </div>
    </div>
  )
}
