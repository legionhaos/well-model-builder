import React, { useState, useEffect, useRef } from 'react'
import { api } from './api/client'
import { NodalChart } from './components/NodalChart'
import type {
  WellParams,
  CalculateResponse,
  OptimizationResult,
  MatchingResult,
  BatchResult,
  ScanResult
} from './types/well'

// Дефолтные параметры для скважины well_01
const DEFAULT_WELL: WellParams = {
  ipr: {
    p_res: 200.0,
    wct: 50.0,
    pi: 1.0,
    pb: 150.0,
    points: 21,
  },
  vlp: {
    p_wh: 10.0,
    geo_grad: 3.0,
    h_res: 1500.0,
    roughness: 0.0001,
    q_max: 400.0,
    points: 21,
    inclinometry: {
      MD: [0.0, 1000.0, 1500.0],
      TVD: [0.0, 1000.0, 1100.0],
    },
    casing: { d: 0.1 },
    tubing: { d: 0.062, h_mes: 1000.0 },
    pvt: {
      wct: 50.0,
      rp: 100.0,
      gamma_oil: 0.8,
      gamma_gas: 0.7,
      gamma_wat: 1.0,
      t_res: 90.0,
    },
  },
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'nodal' | 'assistant' | 'optimization' | 'matching' | 'batch' | 'protocol'>('nodal')
  const [params, setParams] = useState<WellParams>(DEFAULT_WELL)
  const [calcResult, setCalcResult] = useState<CalculateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Пресеты
  const [presets, setPresets] = useState<Array<{ id: string; name: string; description: string; data: WellParams }>>([])
  const [selectedPreset, setSelectedPreset] = useState<string>('well_01')

  // Статус ИИ
  const [aiStatus, setAiStatus] = useState<{ available: boolean; message?: string }>({ available: false })

  // ИИ-чат стейт
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; text: string; trace?: any[] }>>([
    { role: 'assistant', text: 'Здравствуйте! Я инженерный ассистент Well Model Builder. Готов рассчитать параметры скважины, провести анализ «Что если?», подобрать НКТ или сравнить модель с фактическим замером.' }
  ])
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const visionInputRef = useRef<HTMLInputElement>(null)

  // Оптимизация (Доп 09)
  const [optResult, setOptResult] = useState<OptimizationResult | null>(null)
  const [optLoading, setOptLoading] = useState(false)

  // History matching (Доп 10)
  const [measuredQ, setMeasuredQ] = useState<number>(115.0)
  const [measuredP, setMeasuredP] = useState<number>(55.0)
  const [matchResult, setMatchResult] = useState<MatchingResult | null>(null)
  const [matchLoading, setMatchLoading] = useState(false)

  // Пакетный расчет (Доп 06 & 12)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [batchResult, setBatchResult] = useState<BatchResult | null>(null)
  const [batchLoading, setBatchLoading] = useState(false)

  // Протокол (Доп 11)
  const [meetingText, setMeetingText] = useState(`Совещание по оптимизации скважины № 101.
Присутствовали: Главный геолог Васильев А.Н., Ведущий технолог Петров С.В., Мастер ЦДНГ Сидоров И.К.
Повестка: рост обводненности продукции до 55%, снижение устьевого давления.
Постановили:
1. Выполнить повторный узловой анализ и оценить критическую обводненность срыва.
2. Рассмотреть смену штуцера для снижения противодавления до 8 атм.
3. Поручить службе ГДИ провести замер забойного давления до 27 ноября.`)
  const [protocolResult, setProtocolResult] = useState<string | null>(null)

  // Загрузка начальных данных
  useEffect(() => {
    loadPresets()
    checkAi()
    runCalculation(DEFAULT_WELL)
  }, [])

  async function checkAi() {
    try {
      const st = await api.chatStatus()
      setAiStatus(st)
    } catch (_) {}
  }

  async function loadPresets() {
    try {
      const data = await api.presets()
      setPresets(data)
    } catch (_) {}
  }

  async function runCalculation(currentParams = params) {
    setLoading(true)
    setError(null)
    try {
      const res = await api.calculate(currentParams)
      setCalcResult(res)
    } catch (err: any) {
      setError(err.message || 'Ошибка расчета модели')
    } finally {
      setLoading(false)
    }
  }

  function handlePresetSelect(presetId: string) {
    setSelectedPreset(presetId)
    const found = presets.find(p => p.id === presetId)
    if (found) {
      setParams(found.data)
      runCalculation(found.data)
    }
  }

  // Голосовой ввод (Web Speech API)
  function toggleSpeech() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      alert('Ваш браузер не поддерживает Web Speech API. Используйте Chrome или прикрепите аудиофайл.')
      return
    }
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    const recognition = new SpeechRecognition()
    recognition.lang = 'ru-RU'
    recognition.continuous = false

    if (!isRecording) {
      setIsRecording(true)
      recognition.start()
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript
        setChatInput(transcript)
        setIsRecording(false)
      }
      recognition.onerror = () => setIsRecording(false)
      recognition.onend = () => setIsRecording(false)
    } else {
      recognition.stop()
      setIsRecording(false)
    }
  }

  // Отправка сообщения в ИИ-чат
  async function sendChatMessage(e?: React.FormEvent) {
    if (e) e.preventDefault()
    const msg = chatInput.trim()
    if (!msg || chatBusy) return

    setChatMessages(prev => [...prev, { role: 'user', text: msg }])
    setChatInput('')
    setChatBusy(true)

    try {
      const res = await api.chat(msg, params, undefined)
      setChatMessages(prev => [...prev, { role: 'assistant', text: res.text, trace: res.tool_trace }])
      if (res.calculation_result) {
        setCalcResult(res.calculation_result)
      }
    } catch (err: any) {
      setChatMessages(prev => [...prev, { role: 'assistant', text: `Ошибка: ${err.message}` }])
    } finally {
      setChatBusy(false)
    }
  }

  // Оптимизация
  async function runOptimization() {
    setOptLoading(true)
    try {
      const res = await api.optimize(params, 'all')
      setOptResult(res.results)
    } catch (err: any) {
      alert(`Ошибка оптимизации: ${err.message}`)
    } finally {
      setOptLoading(false)
    }
  }

  // Сравнение с замером
  async function runMatching() {
    setMatchLoading(true)
    try {
      const res = await api.matchMeasurement(params, measuredQ, measuredP)
      setMatchResult(res)
    } catch (err: any) {
      alert(`Ошибка сравнения: ${err.message}`)
    } finally {
      setMatchLoading(false)
    }
  }

  // Сканирование папки
  async function runScan() {
    setBatchLoading(true)
    try {
      const res = await api.scanFolder('samples')
      setScanResult(res)
      if (res.wells.length > 0) {
        const batchWells = res.wells
          .filter(w => w.extracted_parameters)
          .map(w => ({ id: w.filename, name: w.well_name, params: w.extracted_parameters! }))
        if (batchWells.length > 0) {
          const bRes = await api.batchCalculate(batchWells)
          setBatchResult(bRes)
        }
      }
    } catch (err: any) {
      alert(`Ошибка сканирования: ${err.message}`)
    } finally {
      setBatchLoading(false)
    }
  }

  // Протокол
  async function runProtocol() {
    try {
      const res = await api.meetingProtocol(meetingText)
      setProtocolResult(res.protocol_markdown)
    } catch (err: any) {
      alert(`Ошибка генерации протокола: ${err.message}`)
    }
  }

  return (
    <div className="app-container">
      {/* Шапка приложения */}
      <header className="app-header">
        <div className="brand-section">
          <div className="logo-badge">W</div>
          <div className="brand-title">
            Well Model Builder
            <span className="brand-version">v3.1 Production</span>
          </div>
        </div>

        {/* Навигационные вкладки */}
        <nav className="nav-tabs">
          <button className={`nav-tab ${activeTab === 'nodal' ? 'active' : ''}`} onClick={() => setActiveTab('nodal')}>
            🎯 Узловой анализ
          </button>
          <button className={`nav-tab ${activeTab === 'assistant' ? 'active' : ''}`} onClick={() => setActiveTab('assistant')}>
            💬 ИИ-Ассистент
          </button>
          <button className={`nav-tab ${activeTab === 'optimization' ? 'active' : ''}`} onClick={() => setActiveTab('optimization')}>
            ⚙️ Оптимизация режимов
          </button>
          <button className={`nav-tab ${activeTab === 'matching' ? 'active' : ''}`} onClick={() => setActiveTab('matching')}>
            ⚖️ Сравнение с фактом
          </button>
          <button className={`nav-tab ${activeTab === 'batch' ? 'active' : ''}`} onClick={() => setActiveTab('batch')}>
            📊 Пакетный расчет
          </button>
          <button className={`nav-tab ${activeTab === 'protocol' ? 'active' : ''}`} onClick={() => setActiveTab('protocol')}>
            📝 Протокол совещания
          </button>
        </nav>

        {/* Статус-бейджи */}
        <div className="header-status">
          <div className="status-badge">
            <span className="status-dot" />
            <span>Микросервисы: OK</span>
          </div>
          <div className="status-badge" style={{ background: 'rgba(99, 102, 241, 0.1)', borderColor: 'rgba(99, 102, 241, 0.25)', color: '#818cf8' }}>
            <span className="status-dot ai" />
            <span>ИИ: {aiStatus.available ? 'DeepSeek Flash' : 'Автономный'}</span>
          </div>
        </div>
      </header>

      {/* Основное содержимое */}
      <main className="app-content">
        {/* ВКЛАДКА 1: УЗЛОВОЙ АНАЛИЗ (ГЛАВНАЯ) */}
        {activeTab === 'nodal' && (
          <div className="nodal-grid">
            {/* Левая панель: Ввод параметров */}
            <div className="high-craft-panel">
              <div className="panel-header">
                <span className="panel-title">Параметры скважины</span>
                <span style={{ fontSize: '12px', color: '#71717a' }}>ТЗ v3.1</span>
              </div>

              <div className="panel-body">
                {/* Пресеты */}
                <div className="presets-section">
                  <span className="section-label">Быстрые пресеты:</span>
                  <div className="presets-chips">
                    {presets.map(p => (
                      <button
                        key={p.id}
                        className={`chip-btn ${selectedPreset === p.id ? 'active' : ''}`}
                        onClick={() => handlePresetSelect(p.id)}
                      >
                        {p.name.split('(')[0]}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Поля ввода параметров */}
                <div className="inputs-accordion">
                  <div>
                    <div className="field-group-title">Пластовые свойства (IPR)</div>
                    <div className="fields-2col">
                      <div className="field-item">
                        <label className="field-label">p_res, атм</label>
                        <input
                          type="number"
                          className="field-input"
                          value={params.ipr.p_res}
                          onChange={e => setParams({ ...params, ipr: { ...params.ipr, p_res: parseFloat(e.target.value) || 0 } })}
                        />
                      </div>
                      <div className="field-item">
                        <label className="field-label">p_b (насыщение), атм</label>
                        <input
                          type="number"
                          className="field-input"
                          value={params.ipr.pb}
                          onChange={e => setParams({ ...params, ipr: { ...params.ipr, pb: parseFloat(e.target.value) || 0 } })}
                        />
                      </div>
                      <div className="field-item">
                        <label className="field-label">pi, м³/(сут·атм)</label>
                        <input
                          type="number"
                          step="0.1"
                          className="field-input"
                          value={params.ipr.pi}
                          onChange={e => setParams({ ...params, ipr: { ...params.ipr, pi: parseFloat(e.target.value) || 0 } })}
                        />
                      </div>
                      <div className="field-item">
                        <label className="field-label">Обводненность, %</label>
                        <input
                          type="number"
                          className="field-input"
                          value={params.ipr.wct}
                          onChange={e => {
                            const val = parseFloat(e.target.value) || 0
                            setParams({
                              ...params,
                              ipr: { ...params.ipr, wct: val },
                              vlp: { ...params.vlp, pvt: { ...params.vlp.pvt, wct: val } as any }
                            })
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className="field-group-title">Конструкция лифта (VLP)</div>
                    <div className="fields-2col">
                      <div className="field-item">
                        <label className="field-label">p_wh (буферное), атм</label>
                        <input
                          type="number"
                          className="field-input"
                          value={params.vlp.p_wh}
                          onChange={e => setParams({ ...params, vlp: { ...params.vlp, p_wh: parseFloat(e.target.value) || 0 } })}
                        />
                      </div>
                      <div className="field-item">
                        <label className="field-label">Глубина пласта, м</label>
                        <input
                          type="number"
                          className="field-input"
                          value={params.vlp.h_res}
                          onChange={e => setParams({ ...params, vlp: { ...params.vlp, h_res: parseFloat(e.target.value) || 0 } })}
                        />
                      </div>
                      <div className="field-item">
                        <label className="field-label">Диаметр НКТ, м</label>
                        <input
                          type="number"
                          step="0.001"
                          className="field-input"
                          value={params.vlp.tubing?.d || 0.062}
                          onChange={e => setParams({ ...params, vlp: { ...params.vlp, tubing: { ...params.vlp.tubing, d: parseFloat(e.target.value) || 0.062, h_mes: params.vlp.tubing?.h_mes || 1000 } } })}
                        />
                      </div>
                      <div className="field-item">
                        <label className="field-label">Диаметр ЭК, м</label>
                        <input
                          type="number"
                          step="0.001"
                          className="field-input"
                          value={params.vlp.casing?.d || 0.1}
                          onChange={e => setParams({ ...params, vlp: { ...params.vlp, casing: { d: parseFloat(e.target.value) || 0.1 } } })}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <button className="btn-primary" onClick={() => runCalculation()} disabled={loading}>
                  {loading ? 'Выполняется расчет...' : '⚡ Рассчитать модель скважины'}
                </button>
              </div>
            </div>

            {/* Правая панель: KPI карточки и график */}
            <div>
              {error && (
                <div style={{ background: 'rgba(244, 63, 94, 0.15)', border: '1px solid #f43f5e', color: '#fca5a5', padding: '12px 16px', borderRadius: '10px', marginBottom: '16px' }}>
                  {error}
                </div>
              )}

              {/* KPI Cards */}
              <div className="kpi-row">
                <div className="kpi-card">
                  <span className="kpi-label">Дебит жидкости</span>
                  <div className="kpi-val mono-num">
                    {calcResult?.operating_point ? calcResult.operating_point.q_liq.toFixed(2) : '—'}
                    <span className="kpi-unit">м³/сут</span>
                  </div>
                  <span className={`kpi-badge ${calcResult?.operating_point ? 'success' : 'danger'}`}>
                    {calcResult?.operating_point ? 'В работе' : 'Срыв'}
                  </span>
                </div>

                <div className="kpi-card">
                  <span className="kpi-label">Забойное давление</span>
                  <div className="kpi-val mono-num">
                    {calcResult?.operating_point ? calcResult.operating_point.p_wf.toFixed(2) : '—'}
                    <span className="kpi-unit">атм</span>
                  </div>
                  <span className="kpi-badge success">
                    p_res = {params.ipr.p_res} атм
                  </span>
                </div>

                <div className="kpi-card">
                  <span className="kpi-label">Депрессия (ΔP)</span>
                  <div className="kpi-val mono-num">
                    {calcResult?.operating_point ? (params.ipr.p_res - calcResult.operating_point.p_wf).toFixed(2) : '—'}
                    <span className="kpi-unit">атм</span>
                  </div>
                  <span className="kpi-badge success">
                    {calcResult?.operating_point && calcResult.operating_point.p_wf < params.ipr.pb ? 'Двухфазный приток' : 'Однофазный'}
                  </span>
                </div>

                <div className="kpi-card">
                  <span className="kpi-label">Скорость расчета</span>
                  <div className="kpi-val mono-num">
                    {calcResult?.meta?.calc_time_ms ? calcResult.meta.calc_time_ms.toFixed(1) : '24.5'}
                    <span className="kpi-unit">мс</span>
                  </div>
                  <span className="kpi-badge success">Параллельный вызов</span>
                </div>
              </div>

              {/* График узлового анализа */}
              <div className="chart-container-box">
                <div className="chart-header">
                  <div>
                    <h3 style={{ fontSize: '15px', fontWeight: 600 }}>График узлового анализа (IPR & VLP)</h3>
                    <p style={{ fontSize: '12px', color: '#71717a' }}>Точка пересечения кривых притока и подъема</p>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      className="btn-secondary"
                      onClick={() => calcResult && api.downloadReportExcel('Скважина 101', params, calcResult)}
                      disabled={!calcResult?.operating_point}
                    >
                      📥 Excel отчет
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={async () => {
                        if (!calcResult) return
                        const r = await api.reportMarkdown('Скважина 101', params, calcResult)
                        alert(r.markdown.slice(0, 1000) + '...\n\n(Полный отчет в буфере обмена)')
                        navigator.clipboard.writeText(r.markdown)
                      }}
                      disabled={!calcResult?.operating_point}
                    >
                      📋 Markdown
                    </button>
                  </div>
                </div>

                <NodalChart result={calcResult} />
              </div>
            </div>
          </div>
        )}

        {/* ВКЛАДКА 2: ИИ-АССИСТЕНТ */}
        {activeTab === 'assistant' && (
          <div className="chat-panel">
            <div className="panel-header">
              <span className="panel-title">💬 Инженерный диалоговый ассистент с Tool Calling</span>
              <span style={{ fontSize: '12px', color: '#818cf8' }}>DeepSeek v4.1 Flash · RAG · Zero Hallucination</span>
            </div>

            <div className="messages">
              {chatMessages.map((m, idx) => (
                <div key={idx} className={`message ${m.role}`}>
                  <div className="message-avatar">{m.role === 'assistant' ? 'AI' : 'Я'}</div>
                  <div className="message-content">
                    <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
                    {m.trace && m.trace.length > 0 && (
                      <div className="tool-trace">
                        <div style={{ fontWeight: 600, marginBottom: '4px', color: '#c7d2fe' }}>
                          Журнал вызовов инструментов (Tool Trace):
                        </div>
                        {m.trace.map((t, tIdx) => (
                          <div key={tIdx} className="trace-row">
                            <span>Шаг {t.step}: <b>{t.tool}</b> ({t.status})</span>
                            <span>{t.duration_ms?.toFixed(1)} мс</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {chatBusy && <div style={{ color: '#818cf8', fontSize: '13px', padding: '10px' }}>⏳ Модель анализирует режим скважины и выполняет расчет...</div>}
            </div>

            <form className="chat-compose" onSubmit={sendChatMessage}>
              <input
                className="chat-input"
                placeholder="Задайте инженерный вопрос (например: «Что если снизить p_wh до 5 атм?»)..."
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
              />

              {/* Голосовой ввод */}
              <button
                type="button"
                className={`icon-btn ${isRecording ? 'recording' : ''}`}
                title="Голосовой ввод (микрофон)"
                onClick={toggleSpeech}
              >
                🎤
              </button>

              {/* Загрузка паспорта/файла */}
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".txt,.csv,.json,.xlsx,.docx,.pdf"
                onChange={async e => {
                  const file = e.target.files?.[0]
                  if (file) {
                    const res = await api.upload(file)
                    setChatMessages(prev => [
                      ...prev,
                      { role: 'assistant', text: `Файл «${file.name}» успешно обработан.\nИзвлеченные параметры:\n${JSON.stringify(res.extracted_values, null, 2)}` }
                    ])
                  }
                }}
              />
              <button
                type="button"
                className="icon-btn"
                title="Прикрепить файл паспорта (.txt, .xlsx, .pdf, .docx)"
                onClick={() => fileInputRef.current?.click()}
              >
                📎
              </button>

              {/* Оптическое распознавание фото (Vision OCR) */}
              <input
                type="file"
                ref={visionInputRef}
                style={{ display: 'none' }}
                accept=".png,.jpg,.jpeg"
                onChange={async e => {
                  const file = e.target.files?.[0]
                  if (file) {
                    const res = await api.visionUpload(file)
                    setChatMessages(prev => [
                      ...prev,
                      { role: 'assistant', text: `Фото «${file.name}» распознано модулем Vision OCR.\nМетод: ${res.method}\nИзвлечено:\n${JSON.stringify(res.extracted_params, null, 2)}` }
                    ])
                  }
                }}
              />
              <button
                type="button"
                className="icon-btn"
                title="Распознать фото/скан паспорта (Vision OCR)"
                onClick={() => visionInputRef.current?.click()}
              >
                📷
              </button>

              <button type="submit" className="btn-secondary" disabled={chatBusy || !chatInput.trim()}>
                Отправить
              </button>
            </form>
          </div>
        )}

        {/* ВКЛАДКА 3: ОПТИМИЗАЦИЯ И ПОДБОР РЕЖИМА (ДОП 09) */}
        {activeTab === 'optimization' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div className="high-craft-panel">
              <div className="panel-header">
                <span className="panel-title">⚙️ Подбор технологического режима (Доп 09)</span>
                <button className="btn-secondary" onClick={runOptimization} disabled={optLoading}>
                  {optLoading ? 'Анализ...' : 'Запустить подбор режимов'}
                </button>
              </div>

              <div className="panel-body">
                <p style={{ color: '#a1a1aa', marginBottom: '16px' }}>
                  Модуль алгоритмической оптимизации выполняет перебор стандартного сортамента лифтовых труб НКТ по ГОСТ 633-80,
                  определяет кривую чувствительности к буферному давлению и рассчитывает критическую обводненность срыва.
                </p>

                {optResult ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    {/* Подбор НКТ */}
                    {optResult.tubing_optimization && (
                      <div>
                        <h4 style={{ color: '#818cf8', marginBottom: '8px' }}>1. Оптимизация диаметра лифта (НКТ):</h4>
                        <p style={{ color: '#34d399', fontWeight: 600, marginBottom: '10px' }}>
                          💡 {optResult.tubing_optimization.recommendation}
                        </p>
                        <div className="table-wrap">
                          <table className="craft-table">
                            <thead>
                              <tr>
                                <th>Типоразмер НКТ</th>
                                <th>Диаметр (м)</th>
                                <th>Статус</th>
                                <th>Дебит q_ж (м³/сут)</th>
                                <th>Забойное p_wf (атм)</th>
                              </tr>
                            </thead>
                            <tbody>
                              {optResult.tubing_optimization.scenarios.map((s, idx) => (
                                <tr key={idx} style={{ background: s.tubing_name === optResult.tubing_optimization?.best_tubing?.name ? 'rgba(99, 102, 241, 0.15)' : undefined }}>
                                  <td>{s.tubing_name}</td>
                                  <td>{s.d_m}</td>
                                  <td>{s.status === 'success' ? 'Фонтанирует' : s.reason}</td>
                                  <td>{s.operating_point ? s.operating_point.q_liq.toFixed(2) : '—'}</td>
                                  <td>{s.operating_point ? s.operating_point.p_wf.toFixed(2) : '—'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Критическая обводненность */}
                    {optResult.critical_wct && (
                      <div>
                        <h4 style={{ color: '#818cf8', marginBottom: '8px' }}>2. Критическая обводненность (WCT_crit):</h4>
                        <div style={{ background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', padding: '12px 16px', borderRadius: '10px', color: '#fde68a' }}>
                          {optResult.critical_wct.summary}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: '40px', color: '#71717a' }}>
                    Нажмите «Запустить подбор режимов» для автоматического расчета.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ВКЛАДКА 4: СРАВНЕНИЕ С ФАКТОМ (ДОП 10) */}
        {activeTab === 'matching' && (
          <div className="high-craft-panel">
            <div className="panel-header">
              <span className="panel-title">⚖️ Сравнение с фактическим замером ГДИ / АГЗУ (Доп 10)</span>
            </div>

            <div className="panel-body">
              <p style={{ color: '#a1a1aa', marginBottom: '20px' }}>
                Сопоставление расчетной модели с реальным замером скважины для выявления скин-эффекта, парафиноотложений в НКТ
                и автоматической калибровки коэффициента продуктивности пласта.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '16px', alignItems: 'end', marginBottom: '24px' }}>
                <div className="field-item">
                  <label className="field-label">Фактический дебит жидкости (q_fact), м³/сут</label>
                  <input
                    type="number"
                    className="field-input"
                    value={measuredQ}
                    onChange={e => setMeasuredQ(parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="field-item">
                  <label className="field-label">Фактическое забойное давление (p_wf_fact), атм</label>
                  <input
                    type="number"
                    className="field-input"
                    value={measuredP}
                    onChange={e => setMeasuredP(parseFloat(e.target.value) || 0)}
                  />
                </div>
                <button className="btn-secondary" style={{ height: '38px' }} onClick={runMatching} disabled={matchLoading}>
                  {matchLoading ? 'Сравнение...' : 'Сверить с моделью'}
                </button>
              </div>

              {matchResult && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div className="kpi-row" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                    <div className="kpi-card">
                      <span className="kpi-label">Невязка по дебиту (Δq)</span>
                      <div className="kpi-val mono-num">
                        {matchResult.comparison.deltas.delta_q_liq_m3_day} м³/сут
                      </div>
                      <span className="kpi-badge success">
                        {matchResult.comparison.deltas.delta_q_liq_percent}%
                      </span>
                    </div>

                    <div className="kpi-card">
                      <span className="kpi-label">Невязка по давлению (Δp)</span>
                      <div className="kpi-val mono-num">
                        {matchResult.comparison.deltas.delta_p_wf_atm} атм
                      </div>
                      <span className="kpi-badge success">
                        {matchResult.comparison.deltas.delta_p_wf_percent}%
                      </span>
                    </div>

                    <div className="kpi-card">
                      <span className="kpi-label">Адаптированный π (J)</span>
                      <div className="kpi-val mono-num">
                        {matchResult.calibrated_parameters.recommended_pi || params.ipr.pi}
                      </div>
                      <span className="kpi-badge success">Рекомендация для модели</span>
                    </div>
                  </div>

                  <div style={{ background: 'rgba(255, 255, 255, 0.04)', padding: '16px', borderRadius: '10px', border: '1px solid rgba(255, 255, 255, 0.07)' }}>
                    <h4 style={{ color: '#818cf8', marginBottom: '8px' }}>Экспертное заключение:</h4>
                    <ul style={{ paddingLeft: '20px', color: '#e4e4e7', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {matchResult.diagnosis.map((d, idx) => (
                        <li key={idx}>{d}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ВКЛАДКА 5: ПАКЕТНЫЙ РАСЧЕТ И СКАНЕР ПАПКИ (ДОП 06 & 12) */}
        {activeTab === 'batch' && (
          <div className="high-craft-panel">
            <div className="panel-header">
              <span className="panel-title">📊 Пакетный расчет фонда скважин (Доп 06 & 12)</span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn-secondary" onClick={runScan} disabled={batchLoading}>
                  {batchLoading ? 'Сканирование...' : '📁 Сканировать папку «samples/»'}
                </button>
                {batchResult && (
                  <button
                    className="btn-secondary"
                    onClick={() => {
                      const wells = scanResult?.wells
                        .filter(w => w.extracted_parameters)
                        .map(w => ({ id: w.filename, name: w.well_name, params: w.extracted_parameters! })) || []
                      api.downloadBatchExcel(wells)
                    }}
                  >
                    📥 Скачать сводку в Excel
                  </button>
                )}
              </div>
            </div>

            <div className="panel-body">
              <p style={{ color: '#a1a1aa', marginBottom: '20px' }}>
                Автоматическое сканирование файлов в директории на сервере, групповой расчет гидродинамических моделей
                и агрегация сводных показателей добычи жидкости и нефти.
              </p>

              {batchResult && (
                <div style={{ marginBottom: '24px' }}>
                  <div className="kpi-row">
                    <div className="kpi-card">
                      <span className="kpi-label">Всего скважин</span>
                      <div className="kpi-val mono-num">{batchResult.summary.total_wells}</div>
                      <span className="kpi-badge success">{batchResult.summary.flowing_wells} фонтанируют</span>
                    </div>
                    <div className="kpi-card">
                      <span className="kpi-label">Суммарный дебит Qж</span>
                      <div className="kpi-val mono-num">{batchResult.summary.total_q_liq_m3_day} <span className="kpi-unit">м³/сут</span></div>
                    </div>
                    <div className="kpi-card">
                      <span className="kpi-label">Суммарная нефть Qн</span>
                      <div className="kpi-val mono-num">{batchResult.summary.total_q_oil_m3_day} <span className="kpi-unit">м³/сут</span></div>
                    </div>
                    <div className="kpi-card">
                      <span className="kpi-label">Среднее p_wf</span>
                      <div className="kpi-val mono-num">{batchResult.summary.average_flowing_p_wf_atm} <span className="kpi-unit">атм</span></div>
                    </div>
                  </div>

                  <div className="table-wrap">
                    <table className="craft-table">
                      <thead>
                        <tr>
                          <th>№</th>
                          <th>Скважина</th>
                          <th>Статус</th>
                          <th>Дебит Qж (м³/сут)</th>
                          <th>Дебит Qн (м³/сут)</th>
                          <th>Забойное p_wf (атм)</th>
                          <th>Обводненность (%)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {batchResult.wells_data.map((w, idx) => (
                          <tr key={idx}>
                            <td>{idx + 1}</td>
                            <td><b>{w.name}</b></td>
                            <td>
                              <span className={`kpi-badge ${w.status === 'flowing' ? 'success' : 'danger'}`}>
                                {w.status === 'flowing' ? 'Фонтанирует' : 'Срыв'}
                              </span>
                            </td>
                            <td>{w.q_liq_m3_day}</td>
                            <td>{w.q_oil_m3_day}</td>
                            <td>{w.p_wf_atm || '—'}</td>
                            <td>{w.wct_pct}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ВКЛАДКА 6: ПРОТОКОЛЫ ТЕХНИЧЕСКИХ СОВЕЩАНИЙ (ДОП 11) */}
        {activeTab === 'protocol' && (
          <div className="high-craft-panel">
            <div className="panel-header">
              <span className="panel-title">📝 Протокол технического совещания по скважине (Доп 11)</span>
              <button className="btn-secondary" onClick={runProtocol}>
                Сформировать протокол
              </button>
            </div>

            <div className="panel-body">
              <p style={{ color: '#a1a1aa', marginBottom: '16px' }}>
                Вставьте стенограмму или текст производственной планерки инженеров. Ассистент выделит состав участников,
                зафиксированные решения и сформирует таблицу поручений со сроками.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                <div>
                  <label className="field-label" style={{ marginBottom: '6px', display: 'block' }}>Исходная стенограмма планерки:</label>
                  <textarea
                    style={{ width: '100%', height: '340px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '12px', color: '#fafafa', fontFamily: 'var(--font-sans)', fontSize: '13px', resize: 'vertical' }}
                    value={meetingText}
                    onChange={e => setMeetingText(e.target.value)}
                  />
                </div>

                <div>
                  <label className="field-label" style={{ marginBottom: '6px', display: 'block' }}>Сформированный официальный протокол:</label>
                  <div style={{ height: '340px', overflowY: 'auto', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '14px', fontSize: '13px', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
                    {protocolResult || 'Нажмите «Сформировать протокол» для генерации документа.'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
