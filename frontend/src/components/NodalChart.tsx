import {
  CartesianGrid, ComposedChart, Legend, Line, ReferenceDot, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { CalculateResponse } from '../types/well'
import { inspectCalculationPhysics } from '../utils/physics'

const colors = { ipr: 'var(--ipr)', vlp: 'var(--vlp)', point: 'var(--point)' }

export function NodalChart({
  result,
  blockedWarnings = [],
}: {
  result: CalculateResponse | null
  blockedWarnings?: string[]
}) {
  if (!result) {
    if (blockedWarnings.length > 0) {
      return (
        <div className="chart-empty">
          <span className="chart-empty-icon" aria-hidden="true">!</span>
          <p>Нефизичный расчёт не отображён на основном графике: {blockedWarnings[0]}</p>
        </div>
      )
    }
    return (
      <div className="chart-empty">
        <span className="chart-empty-icon" aria-hidden="true">∿</span>
        <p>Рассчитайте модель, чтобы увидеть кривые притока и подъёма</p>
      </div>
    )
  }

  const { isPhysical, warnings } = inspectCalculationPhysics(result)
  const op = result.operating_point
  const hasNegativeOp = Boolean(op && (op.q_liq <= 0 || op.p_wf <= 0))
  if (!isPhysical || hasNegativeOp) {
    return (
      <div className="chart-empty">
        <span className="chart-empty-icon" aria-hidden="true">!</span>
        <p>График заблокирован: {warnings[0] || 'отрицательный дебит или некорректные параметры'}</p>
      </div>
    )
  }

  const rows = new Map<number, { q: number; ipr?: number; vlp?: number }>()
  result.ipr.q_liq.forEach((q, i) => {
    if (q >= 0 && result.ipr.p_wf[i] >= 0) {
      rows.set(q, { ...rows.get(q), q, ipr: result.ipr.p_wf[i] })
    }
  })
  result.vlp.q_liq.forEach((q, i) => {
    if (q >= 0 && result.vlp.p_wf[i] >= 0) {
      rows.set(q, { ...rows.get(q), q, vlp: result.vlp.p_wf[i] })
    }
  })
  const data = [...rows.values()].sort((a, b) => a.q - b.q)

  return (
    <div className="chart-wrap">
      {blockedWarnings.length > 0 && (
        <div className="alert alert-warning" role="status" style={{ marginBottom: '10px' }}>
          <div className="alert-icon" aria-hidden="true">!</div>
          <div className="alert-content">
            <strong>Последний некорректный расчёт не применён к графику</strong>
            <p>Отображается предыдущая физически корректная кривая.</p>
          </div>
        </div>
      )}
      <ResponsiveContainer width="100%" height={380} minHeight={350}>
        <ComposedChart data={data} margin={{ top: 14, right: 18, bottom: 12, left: 2 }}>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 5" vertical={false} />
          <XAxis dataKey="q" type="number" domain={['auto', 'auto']} tick={{ fill: 'var(--chart-axis)', fontSize: 11 }} axisLine={{ stroke: 'var(--chart-grid)' }} tickLine={false} label={{ value: 'Дебит жидкости, м³/сут', position: 'insideBottom', offset: -4, fill: 'var(--chart-axis)', fontSize: 11 }} />
          <YAxis type="number" domain={['auto', 'auto']} tick={{ fill: 'var(--chart-axis)', fontSize: 11 }} axisLine={false} tickLine={false} label={{ value: 'p_wf, атм', angle: -90, position: 'insideLeft', fill: 'var(--chart-axis)', fontSize: 11 }} />
          <Tooltip contentStyle={{ background: 'var(--chart-tooltip)', border: '1px solid var(--chart-tooltip-border)', borderRadius: 8, color: 'var(--ink)' }} formatter={(value: number, name: string) => [`${Number(value).toFixed(2)} атм`, name]} labelFormatter={(label) => `${Number(label).toFixed(2)} м³/сут`} />
          <Legend wrapperStyle={{ fontSize: 12, color: 'var(--muted)', paddingTop: 12 }} />
          <Line name="IPR · приток" type="monotone" dataKey="ipr" stroke={colors.ipr} strokeWidth={2.5} dot={false} connectNulls />
          <Line name="VLP · подъём" type="monotone" dataKey="vlp" stroke={colors.vlp} strokeWidth={2.5} dot={false} connectNulls />
          {op && <ReferenceDot x={op.q_liq} y={op.p_wf} r={6} fill={colors.point} stroke="var(--surface)" strokeWidth={2} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
