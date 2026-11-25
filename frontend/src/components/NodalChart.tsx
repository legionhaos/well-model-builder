import { useState } from 'react'
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CalculateResponse } from '../types/well'

interface NodalChartProps {
  result: CalculateResponse | null
  loading?: boolean
}

export function NodalChart({ result, loading }: NodalChartProps) {
  const [scaleType, setScaleType] = useState<'linear' | 'log'>('linear')

  // Fallback demo curves matching the screenshot if result is not loaded yet
  const demoIprQ = [0, 25, 50, 75, 100, 125, 134, 150, 175, 200, 225, 250]
  const demoIprP = [220, 212, 202, 190, 175, 155, 145, 130, 100, 70, 40, 10]
  const demoVlpQ = [0, 25, 50, 75, 100, 125, 134, 150, 175, 200, 225, 250]
  const demoVlpP = [10, 30, 52, 78, 105, 133, 145, 160, 178, 195, 210, 225]

  const iprQ = result?.ipr?.q_liq?.length ? result.ipr.q_liq : demoIprQ
  const iprP = result?.ipr?.p_wf?.length ? result.ipr.p_wf : demoIprP
  const vlpQ = result?.vlp?.q_liq?.length ? result.vlp.q_liq : demoVlpQ
  const vlpP = result?.vlp?.p_wf?.length ? result.vlp.p_wf : demoVlpP

  const rows = new Map<number, { q: number; ipr?: number; vlp?: number }>()
  iprQ.forEach((q, i) => rows.set(q, { ...rows.get(q), q, ipr: iprP[i] }))
  vlpQ.forEach((q, i) => rows.set(q, { ...rows.get(q), q, vlp: vlpP[i] }))

  let data = [...rows.values()].sort((a, b) => a.q - b.q)
  if (scaleType === 'log') {
    data = data.filter((d) => d.q > 0)
  }

  const op = result?.operating_point || { q_liq: 134, p_wf: 145 }

  return (
    <div className="nodal-chart-container">
      <div className="nodal-chart-header">
        <div className="nodal-chart-title">
          <svg className="chart-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          <h3>График IPR и VLP</h3>
        </div>

        <div className="chart-controls-group">
          <div className="scale-toggle-pills" role="radiogroup" aria-label="Масштаб графика">
            <button
              type="button"
              className={`scale-pill ${scaleType === 'linear' ? 'active' : ''}`}
              onClick={() => setScaleType('linear')}
            >
              Линейный
            </button>
            <button
              type="button"
              className={`scale-pill ${scaleType === 'log' ? 'active' : ''}`}
              onClick={() => setScaleType('log')}
            >
              Логарифмический
            </button>
          </div>

          <div className="chart-legend-inline">
            <span className="legend-item">
              <span className="legend-dot dot-ipr" />
              <span>IPR</span>
            </span>
            <span className="legend-item">
              <span className="legend-dot dot-vlp" />
              <span>VLP</span>
            </span>
            <span className="legend-item">
              <span className="legend-star">★</span>
              <span>Рабочая точка</span>
            </span>
          </div>
        </div>
      </div>

      <div className="nodal-chart-canvas">
        {loading && <div className="chart-loading-overlay">Расчёт модели...</div>}
        <ResponsiveContainer width="100%" height="100%" minHeight={210}>
          <ComposedChart data={data} margin={{ top: 28, right: 18, bottom: 14, left: 4 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="q"
              type="number"
              scale={scaleType === 'log' ? 'log' : 'linear'}
              domain={['auto', 'auto']}
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={{ stroke: '#cbd5e1' }}
              tickLine={{ stroke: '#cbd5e1' }}
              label={{
                value: 'Дебит жидкости, м³/сут',
                position: 'insideBottom',
                offset: -12,
                fill: '#1e293b',
                fontSize: 12,
                fontWeight: 500,
              }}
            />
            <YAxis
              type="number"
              domain={[0, 'auto']}
              tick={{ fill: '#64748b', fontSize: 11 }}
              axisLine={{ stroke: '#cbd5e1' }}
              tickLine={{ stroke: '#cbd5e1' }}
              label={{
                value: 'Давление, бар',
                angle: -90,
                position: 'insideLeft',
                offset: 2,
                fill: '#1e293b',
                fontSize: 12,
                fontWeight: 500,
              }}
            />
            <Tooltip
              contentStyle={{
                background: '#ffffff',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                fontSize: '12px',
                color: '#0f172a',
              }}
              formatter={(value: number, name: string) => [
                `${Number(value).toFixed(1)} бар`,
                name === 'ipr' ? 'IPR (приток)' : 'VLP (подъём)',
              ]}
              labelFormatter={(label) => `Дебит: ${Number(label).toFixed(1)} м³/сут`}
            />

            <Line
              name="ipr"
              type="monotone"
              dataKey="ipr"
              stroke="#2563eb"
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#2563eb', strokeWidth: 0 }}
              activeDot={{ r: 5 }}
              connectNulls
            />
            <Line
              name="vlp"
              type="monotone"
              dataKey="vlp"
              stroke="#f97316"
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#f97316', strokeWidth: 0 }}
              activeDot={{ r: 5 }}
              connectNulls
            />

            {op && (
              <>
                <ReferenceLine
                  x={op.q_liq}
                  stroke="#94a3b8"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                />
                <ReferenceLine
                  y={op.p_wf}
                  stroke="#94a3b8"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                />
                <ReferenceDot
                  x={op.q_liq}
                  y={op.p_wf}
                  r={7}
                  fill="#2563eb"
                  stroke="#ffffff"
                  strokeWidth={2}
                  label={{
                    position: 'top',
                    content: (props: any) => {
                      const { cx, cy } = props
                      if (cx === undefined || cy === undefined) return null
                      return (
                        <g transform={`translate(${cx - 58}, ${cy - 52})`}>
                          <rect
                            width={116}
                            height={44}
                            rx={8}
                            fill="#ffffff"
                            stroke="#e2e8f0"
                            filter="drop-shadow(0 2px 5px rgba(0,0,0,0.08))"
                          />
                          <text
                            x={58}
                            y={18}
                            textAnchor="middle"
                            fontSize={11}
                            fontWeight={600}
                            fill="#0f172a"
                          >
                            {`q = ${op.q_liq.toFixed(0)} м³/сут`}
                          </text>
                          <text
                            x={58}
                            y={34}
                            textAnchor="middle"
                            fontSize={11}
                            fontWeight={600}
                            fill="#0f172a"
                          >
                            {`p_wf = ${op.p_wf.toFixed(0)} бар`}
                          </text>
                        </g>
                      )
                    },
                  }}
                />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
