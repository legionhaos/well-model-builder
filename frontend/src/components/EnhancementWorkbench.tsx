import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { BatchResult, CalculateResponse, MatchingResult, OptimizationResult, ScanResult, WellParams } from '../types/well'

type Props = { params: WellParams; result: CalculateResponse | null; onParams: (params: WellParams) => void }
type Tool = 'optimize' | 'match' | 'batch' | 'protocol' | 'files' | 'report'

export function EnhancementWorkbench({ params, result, onParams }: Props) {
  const [active, setActive] = useState<Tool>('optimize')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [optimization, setOptimization] = useState<OptimizationResult | null>(null)
  const [matching, setMatching] = useState<MatchingResult | null>(null)
  const [scan, setScan] = useState<ScanResult | null>(null)
  const [batch, setBatch] = useState<BatchResult | null>(null)
  const [protocol, setProtocol] = useState('')
  const [transcript, setTranscript] = useState('')
  const [measuredQ, setMeasuredQ] = useState(115)
  const [measuredP, setMeasuredP] = useState(55)
  const imageRef = useRef<HTMLInputElement>(null)
  const audioRef = useRef<HTMLInputElement>(null)

  async function run(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (cause) { setError(cause instanceof Error ? cause.message : 'Операция не выполнена') }
    finally { setBusy(false) }
  }
  const tabs: Array<[Tool, string]> = [['optimize', 'Оптимизация'], ['match', 'Замер'], ['batch', 'Фонд'], ['protocol', 'Протокол'], ['files', 'Файлы'], ['report', 'Отчёт']]

  return <section className="enhancement-workbench">
    <header className="enhancement-heading"><div><span className="eyebrow">РАСШИРЕННЫЕ ИНСТРУМЕНТЫ</span><h3>Инженерные операции</h3></div></header>
    <nav className="enhancement-tabs" aria-label="Инженерные инструменты">{tabs.map(([id, title]) => <button key={id} type="button" className={active === id ? 'active' : ''} aria-pressed={active === id} onClick={() => { setActive(id); setError('') }}>{title}</button>)}</nav>
    <div className="enhancement-content">
      {active === 'optimize' && <div className="tool-pane"><p>Подбор диаметра НКТ, оптимального устьевого давления и критической обводнённости.</p><button disabled={busy} onClick={() => run(async () => { const response = await api.optimize(params); setOptimization(response.results) })}>{busy ? 'Расчёт…' : 'Подобрать режим'}</button>{optimization && <div className="tool-results">{optimization.tubing_optimization && <p><strong>НКТ:</strong> {optimization.tubing_optimization.recommendation}</p>}{optimization.wellhead_sensitivity && <p><strong>Устье:</strong> {optimization.wellhead_sensitivity.recommendation}</p>}{optimization.critical_wct && <p><strong>Обводнённость:</strong> {optimization.critical_wct.summary}</p>}</div>}</div>}
      {active === 'match' && <div className="tool-pane"><p>Сопоставить расчётную модель с фактическим замером.</p><div className="tool-fields"><label>Фактический дебит, м³/сут<input type="number" value={measuredQ} onChange={e => setMeasuredQ(Number(e.target.value))}/></label><label>Забойное давление, атм<input type="number" value={measuredP} onChange={e => setMeasuredP(Number(e.target.value))}/></label></div><button disabled={busy} onClick={() => run(async () => setMatching(await api.matchMeasurement(params, measuredQ, measuredP)))}>{busy ? 'Сравнение…' : 'Сравнить с моделью'}</button>{matching && <div className="tool-results"><p>{matching.diagnosis.join(' ')}</p><p>{matching.recommendations.join(' ')}</p>{matching.calibrated_parameters.recommended_pi != null && <p><strong>Рекомендуемый PI:</strong> {matching.calibrated_parameters.recommended_pi.toFixed(3)}</p>}</div>}</div>}
      {active === 'batch' && <div className="tool-pane"><p>Найти подготовленные файлы в папке samples и выполнить пакетный расчёт.</p><button disabled={busy} onClick={() => run(async () => { const scanned = await api.scanFolder(); setScan(scanned); const wells = scanned.wells.filter(w => w.is_ready_for_calc && w.extracted_parameters).map(w => ({ id: w.relative_path, name: w.well_name, params: w.extracted_parameters! })); if (wells.length) setBatch(await api.batchCalculate(wells)) })}>{busy ? 'Сканирование…' : 'Сканировать и рассчитать фонд'}</button>{scan && <p>Найдено файлов: {scan.total_files_found}; готово к расчёту: {scan.ready_for_calculation}.</p>}{batch && <div className="tool-results"><p><strong>Фонд:</strong> {batch.summary.flowing_wells} из {batch.summary.total_wells} фонтанируют; суммарный дебит {batch.summary.total_q_liq_m3_day.toFixed(1)} м³/сут.</p><button type="button" onClick={() => run(() => api.downloadBatchExcel(batch.wells_data.map(w => ({ id: w.id, name: w.name, params: scan?.wells.find(scanned => scanned.relative_path === w.id)?.extracted_parameters ?? params }))))}>Скачать Excel</button></div>}</div>}
      {active === 'protocol' && <div className="tool-pane"><label>Текст или транскрипт совещания<textarea rows={4} value={transcript} onChange={e => setTranscript(e.target.value)} placeholder="Вставьте заметки совещания…"/></label><button disabled={busy || !transcript.trim()} onClick={() => run(async () => setProtocol((await api.meetingProtocol(transcript)).protocol_markdown))}>{busy ? 'Формирование…' : 'Сформировать протокол'}</button>{protocol && <pre className="tool-results">{protocol}</pre>}</div>}
      {active === 'files' && <div className="tool-pane"><p>Извлечь параметры из снимка паспорта скважины или получить транскрипцию аудиозаписи.</p><input ref={imageRef} hidden type="file" accept="image/png,image/jpeg,.jpg" onChange={e => { const file = e.target.files?.[0]; if (file) void run(async () => { const response = await api.visionUpload(file); onParams(response.extracted_params) }) }}/><input ref={audioRef} hidden type="file" accept="audio/*,.wav,.mp3,.webm,.ogg" onChange={e => { const file = e.target.files?.[0]; if (file) void run(async () => { const response = await api.audioUpload(file); if (response.extracted_parameters) onParams(response.extracted_parameters); else setTranscript(response.transcript) }) }}/><div className="tool-actions"><button disabled={busy} onClick={() => imageRef.current?.click()}>Распознать снимок</button><button disabled={busy} onClick={() => audioRef.current?.click()}>Расшифровать аудио</button></div></div>}
      {active === 'report' && <div className="tool-pane"><p>Экспорт текущих параметров и результатов узлового анализа во всех форматах.</p><div className="tool-actions"><button disabled={!result || busy} onClick={() => run(() => api.downloadReportHtml('Скважина 01', params, result!))}>📄 Скачать HTML-паспорт</button><button disabled={!result || busy} onClick={() => run(() => api.downloadReportExcel('Скважина 01', params, result!))}>📊 Скачать Excel (.xlsx)</button><button disabled={!result || busy} onClick={() => run(() => api.downloadReportCsv('Скважина 01', params, result!))}>📋 Скачать CSV</button><button disabled={!result || busy} onClick={() => run(async () => { const response = await api.reportMarkdown('Скважина 01', params, result!); const blob = new Blob([response.markdown], { type: 'text/markdown;charset=utf-8' }); const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'well_report.md'; link.click(); URL.revokeObjectURL(url) })}>📝 Скачать Markdown</button></div></div>}
      {error && <p className="tool-error" role="alert">{error}</p>}
    </div>
  </section>
}
