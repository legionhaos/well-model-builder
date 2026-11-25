import type { CalculateResponse } from '../types/well'
import { inspectCalculationPhysics } from '../utils/physics'

interface OperatingPointCardsProps {
  result: CalculateResponse | null
  loading?: boolean
  error?: string | null
  physicalWarnings?: string[]
}

export function OperatingPointCards({
  result,
  loading,
  error,
  physicalWarnings = [],
}: OperatingPointCardsProps) {
  const { warnings: calcWarnings } = inspectCalculationPhysics(result)
  const combinedWarnings = [...physicalWarnings]
  for (const w of calcWarnings) {
    if (!combinedWarnings.includes(w)) combinedWarnings.push(w)
  }

  const op = result?.operating_point ?? null
  const isNoIntersection = Boolean(result) && !op
  const isNegativeOrZeroFlow = Boolean(op && op.q_liq <= 0)
  const isBadBottomholePressure = Boolean(op && op.p_wf <= 0)
  const hasWarnings = combinedWarnings.length > 0 || isNegativeOrZeroFlow || isBadBottomholePressure
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

      {hasWarnings && (
        <div className="alert alert-warning" role="alert">
          <div className="alert-icon" aria-hidden="true">!</div>
          <div className="alert-content">
            <strong>Предупреждение: проверьте корректность параметров и результата расчёта</strong>
            {combinedWarnings.length > 0 && (
              <ul className="alert-warnings-list">
                {combinedWarnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            )}
            <p>
              Расчёт, график и экспорт не заблокированы — результаты отображаются с предупреждающей
              маркировкой.
            </p>
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
        <div className={`kpi-card ${isNegativeOrZeroFlow ? 'is-warning' : ''}`}>
          <div className="kpi-header">
            <span className="kpi-label">Дебит жидкости (q_liq)</span>
            <span className="kpi-unit">м³/сут</span>
          </div>
          <div className="kpi-value" style={isNegativeOrZeroFlow ? { color: 'var(--error-ink)' } : undefined}>
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
            {isNegativeOrZeroFlow
              ? 'Отрицательный / нулевой дебит!'
              : op
                ? 'Оптимальный приток'
                : isNoIntersection
                  ? 'Нет притока'
                  : 'Не рассчитано'}
          </div>
        </div>

        <div className={`kpi-card ${isBadBottomholePressure ? 'is-warning' : ''}`}>
          <div className="kpi-header">
            <span className="kpi-label">Забойное давление (p_wf)</span>
            <span className="kpi-unit">атм</span>
          </div>
          <div className="kpi-value" style={isBadBottomholePressure ? { color: 'var(--error-ink)' } : undefined}>
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
            {isBadBottomholePressure
              ? 'Аномальное давление на забое'
              : op
                ? 'Давление на забое'
                : isNoIntersection
                  ? 'Срыв подачи'
                  : 'Не рассчитано'}
          </div>
        </div>

        <div className={`kpi-card ${hasWarnings ? 'is-warning' : ''}`}>
          <div className="kpi-header">
            <span className="kpi-label">Статус системы</span>
            <span className="kpi-unit">Nodal</span>
          </div>
          <div className="kpi-status">
            {loading ? (
              <span className="status-badge status-loading">
                <span className="badge-pulse" /> Расчет...
              </span>
            ) : op && hasWarnings ? (
              <span className="status-badge status-warning">
                <span className="badge-dot" /> С предупреждением
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
                <span className="badge-dot" /> Ожидание
              </span>
            )}
          </div>
          <div className="kpi-footer">
            {calcTime ? `Расчет за ${calcTime.toFixed(1)} мс` : 'Ядро IPR/VLP'}
          </div>
        </div>
      </div>
    </div>
  )
}
