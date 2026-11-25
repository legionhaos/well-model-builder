import type { CalculateResponse } from '../types/well'
import { inspectCalculationPhysics } from '../utils/physics'

interface OperatingPointCardsProps {
  result: CalculateResponse | null
  loading?: boolean
  error?: string | null
  physicalWarnings?: string[]
  blockedNotice?: string | null
}

export function OperatingPointCards({
  result,
  loading,
  error,
  physicalWarnings = [],
  blockedNotice = null,
}: OperatingPointCardsProps) {
  const { isPhysical, warnings: calcWarnings } = inspectCalculationPhysics(result)
  const combinedWarnings = [...physicalWarnings]
  for (const w of calcWarnings) {
    if (!combinedWarnings.includes(w)) combinedWarnings.push(w)
  }

  const rawOp = result?.operating_point ?? null
  const isBlocked =
    Boolean(blockedNotice) ||
    combinedWarnings.length > 0 ||
    (Boolean(result) && (!isPhysical || (rawOp !== null && (rawOp.q_liq <= 0 || rawOp.p_wf <= 0))))
  const op = rawOp && !isBlocked ? rawOp : null
  const isNoIntersection = Boolean(result) && !rawOp && !isBlocked
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

      {(combinedWarnings.length > 0 || blockedNotice) && (
        <div className="alert alert-error" role="alert">
          <div className="alert-icon" aria-hidden="true">!</div>
          <div className="alert-content">
            <strong>ВНИМАНИЕ: некорректные параметры или отрицательный дебит</strong>
            {blockedNotice && <p>{blockedNotice}</p>}
            {combinedWarnings.map((w, idx) => (
              <p key={idx}>{w}</p>
            ))}
            <p>
              Нефизичные значения не заносятся в основные поля KPI и график. Вы можете исправить
              параметры или выгрузить отчёт с предупреждающей маркировкой.
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
            ) : isBlocked ? (
              '—'
            ) : isNoIntersection ? (
              '—'
            ) : (
              '0.00'
            )}
          </div>
          <div className="kpi-footer">
            {op ? 'Оптимальный приток' : isBlocked ? 'Заблокировано (нефизично)' : isNoIntersection ? 'Нет притока' : 'Не рассчитано'}
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
            ) : isBlocked ? (
              '—'
            ) : isNoIntersection ? (
              '—'
            ) : (
              '0.00'
            )}
          </div>
          <div className="kpi-footer">
            {op ? 'Давление на забое' : isBlocked ? 'Заблокировано (нефизично)' : isNoIntersection ? 'Срыв подачи' : 'Не рассчитано'}
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
            ) : isBlocked ? (
              <span className="status-badge status-warning">
                <span className="badge-dot" /> Отклонено
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
