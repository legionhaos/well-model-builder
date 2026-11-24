import {
  CartesianGrid, ComposedChart, Legend, Line, ReferenceDot, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { CalculateResponse } from '../types/well'

const colors = { ipr: '#19b6a0', vlp: '#ef9f52', point: '#f0cb69' }

export function NodalChart({ result }: { result: CalculateResponse | null }) {
  if (!result) return <div className="chart-empty"><span className="chart-empty-icon">⌁</span><p>Рассчитайте модель, чтобы увидеть кривые притока и подъёма</p></div>
  const rows = new Map<number, { q: number; ipr?: number; vlp?: number }>()
  result.ipr.q_liq.forEach((q, i) => rows.set(q, { ...rows.get(q), q, ipr: result.ipr.p_wf[i] }))
  result.vlp.q_liq.forEach((q, i) => rows.set(q, { ...rows.get(q), q, vlp: result.vlp.p_wf[i] }))
  const data = [...rows.values()].sort((a, b) => a.q - b.q)
  return <div className="chart-wrap">
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 14, right: 18, bottom: 12, left: 2 }}>
        <CartesianGrid stroke="#27363c" strokeDasharray="3 5" vertical={false} />
        <XAxis dataKey="q" type="number" domain={['auto', 'auto']} tick={{ fill: '#829296', fontSize: 11 }} axisLine={{ stroke: '#3a4b50' }} tickLine={false} label={{ value: 'Дебит жидкости, м³/сут', position: 'insideBottom', offset: -4, fill: '#829296', fontSize: 11 }} />
        <YAxis type="number" domain={['auto', 'auto']} tick={{ fill: '#829296', fontSize: 11 }} axisLine={false} tickLine={false} label={{ value: 'p_wf, атм', angle: -90, position: 'insideLeft', fill: '#829296', fontSize: 11 }} />
        <Tooltip contentStyle={{ background: '#17252b', border: '1px solid #34454b', borderRadius: 8, color: '#e9efec' }} formatter={(value: number, name: string) => [`${Number(value).toFixed(2)} атм`, name]} labelFormatter={(label) => `${Number(label).toFixed(2)} м³/сут`} />
        <Legend wrapperStyle={{ fontSize: 12, color: '#aab8b8', paddingTop: 12 }} />
        <Line name="IPR · приток" type="monotone" dataKey="ipr" stroke={colors.ipr} strokeWidth={2.5} dot={false} connectNulls />
        <Line name="VLP · подъём" type="monotone" dataKey="vlp" stroke={colors.vlp} strokeWidth={2.5} dot={false} connectNulls />
        {result.operating_point && <ReferenceDot x={result.operating_point.q_liq} y={result.operating_point.p_wf} r={6} fill={colors.point} stroke="#101b22" strokeWidth={2} />}
      </ComposedChart>
    </ResponsiveContainer>
  </div>
}
