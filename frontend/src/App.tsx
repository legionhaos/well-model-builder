import { useState, useEffect, useCallback, useRef, type PointerEvent as ReactPointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api/client'
import type { CalculateResponse, PresetItem, WellParams } from './types/well'
import { WellInputForm } from './components/WellInputForm'
import { OperatingPointCards } from './components/OperatingPointCards'
import { NodalChart } from './components/NodalChart'
import { AiChatPanel } from './components/AiChatPanel'
import { EnhancementWorkbench, type EnhancementId } from './components/EnhancementWorkbench'
import { SettingsModal } from './components/SettingsModal'
import { clearPersistedJson, loadPersistedJson, savePersistedJson } from './utils/cookies'
import { validateWellPhysics } from './utils/validation'

const WELL_PARAMS_COOKIE_KEY = 'wmb_well_params'

const FALLBACK_PRESETS: PresetItem[] = [
  {
    id: 'well_01',
    name: 'Эталон well_01 (ТЗ v3.1)',
    description: 'Стандартный тестовый кейс из ТЗ: нефтяная залежь 1500 м, WCT 50%',
    data: {
      ipr: {
        p_res: 200.0,
        wct: 50.0,
        pi: 1.0,
        pb: 150.0,
        points: 21,
      },
      vlp: {
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
        p_wh: 10.0,
        geo_grad: 3.0,
        h_res: 1500.0,
        t_res: 90.0,
        roughness: 0.0001,
        q_max: 400.0,
        points: 21,
      },
    },
  },
  {
    id: 'well_high_wct',
    name: 'Высокообводненная (WCT 90%)',
    description: 'Поздняя стадия разработки: высокая плотность столба жидкости',
    data: {
      ipr: {
        p_res: 220.0,
        wct: 90.0,
        pi: 1.5,
        pb: 120.0,
        points: 21,
      },
      vlp: {
        inclinometry: {
          MD: [0.0, 1200.0, 1800.0],
          TVD: [0.0, 1200.0, 1600.0],
        },
        casing: { d: 0.12 },
        tubing: { d: 0.073, h_mes: 1200.0 },
        pvt: {
          wct: 90.0,
          rp: 40.0,
          gamma_oil: 0.85,
          gamma_gas: 0.65,
          gamma_wat: 1.02,
          t_res: 75.0,
        },
        p_wh: 12.0,
        geo_grad: 2.8,
        h_res: 1800.0,
        t_res: 75.0,
        roughness: 0.0001,
        q_max: 500.0,
        points: 21,
      },
    },
  },
  {
    id: 'well_no_intersection',
    name: 'Без пересечения (не фонтанирует)',
    description: 'Низкое пластовое давление или высокое противодавление',
    data: {
      ipr: {
        p_res: 45.0,
        wct: 30.0,
        pi: 0.5,
        pb: 30.0,
        points: 21,
      },
      vlp: {
        inclinometry: {
          MD: [0.0, 1000.0, 1500.0],
          TVD: [0.0, 1000.0, 1100.0],
        },
        casing: { d: 0.1 },
        tubing: { d: 0.062, h_mes: 1000.0 },
        pvt: {
          wct: 30.0,
          rp: 80.0,
          gamma_oil: 0.82,
          gamma_gas: 0.7,
          gamma_wat: 1.0,
          t_res: 80.0,
        },
        p_wh: 25.0,
        geo_grad: 3.0,
        h_res: 1500.0,
        t_res: 80.0,
        roughness: 0.0001,
        q_max: 300.0,
        points: 21,
      },
    },
  },
]

export default function App() {
  const [presets, setPresets] = useState<PresetItem[]>(FALLBACK_PRESETS)
  const [params, setParams] = useState<WellParams>(
    () => loadPersistedJson<WellParams>(WELL_PARAMS_COOKIE_KEY) ?? FALLBACK_PRESETS[0].data,
  )
  const [result, setResult] = useState<CalculateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [settingsVersion, setSettingsVersion] = useState(0)
  const [resetSignal, setResetSignal] = useState(0)
  const [activeTool, setActiveTool] = useState<EnhancementId>('optimize')
  const [chatExpanded, setChatExpanded] = useState(false)
  const [chatPos, setChatPos] = useState<{ x: number; y: number } | null>(null)
  const [isDraggingChat, setIsDraggingChat] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [importDragActive, setImportDragActive] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const chatWidgetRef = useRef<HTMLElement>(null)
  const mainFileInputRef = useRef<HTMLInputElement>(null)
  const dragOffsetRef = useRef<{ dx: number; dy: number }>({ dx: 0, dy: 0 })

  const physicsWarnings = validateWellPhysics(params, result).warnings

  useEffect(() => {
    savePersistedJson(WELL_PARAMS_COOKIE_KEY, params, 30)
  }, [params])

  const openTool = useCallback((tool: EnhancementId) => {
    setActiveTool(tool)
    setToolsOpen(true)
  }, [])

  const clampChatPos = useCallback((x: number, y: number) => {
    const el = chatWidgetRef.current
    const width = el?.offsetWidth ?? 390
    const height = el?.offsetHeight ?? 480
    const pad = 8
    const maxX = Math.max(pad, window.innerWidth - width - pad)
    const maxY = Math.max(pad, window.innerHeight - height - pad)
    return {
      x: Math.min(Math.max(pad, x), maxX),
      y: Math.min(Math.max(pad, y), maxY),
    }
  }, [])

  const handleChatHeaderPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if ((event.target as HTMLElement).closest('button')) return
    const widget = chatWidgetRef.current
    if (!widget) return
    event.preventDefault()
    const rect = widget.getBoundingClientRect()
    dragOffsetRef.current = {
      dx: event.clientX - rect.left,
      dy: event.clientY - rect.top,
    }
    setChatPos({ x: rect.left, y: rect.top })
    setIsDraggingChat(true)
  }, [])

  useEffect(() => {
    if (!isDraggingChat) return
    const onPointerMove = (event: PointerEvent) => {
      const next = clampChatPos(
        event.clientX - dragOffsetRef.current.dx,
        event.clientY - dragOffsetRef.current.dy,
      )
      setChatPos(next)
    }
    const onPointerUp = () => {
      setIsDraggingChat(false)
    }
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
    }
  }, [isDraggingChat, clampChatPos])

  useEffect(() => {
    if (!chatOpen || !chatPos) return
    const adjust = () => {
      setChatPos((prev) => (prev ? clampChatPos(prev.x, prev.y) : null))
    }
    const raf = requestAnimationFrame(adjust)
    window.addEventListener('resize', adjust)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', adjust)
    }
  }, [chatOpen, chatExpanded, clampChatPos])
  // Загрузка пресетов с бэкенда при старте
  useEffect(() => {
    api.presets()
      .then((items) => {
        if (Array.isArray(items) && items.length > 0) {
          setPresets(items)
        }
      })
      .catch(() => {
        // Fallback уже установлен
      })
  }, [])

  // Вызов расчета узлового анализа
  const handleCalculate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.calculate(params)
      setResult(resp)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Неизвестная ошибка расчета'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [params])

  // Автоматический первый расчет для эталона
  useEffect(() => {
    handleCalculate()
  }, [])

  const handleSelectPreset = (preset: PresetItem) => {
    setParams(preset.data)
    setError(null)
  }

  const handleResultFromChat = (calcRes?: CalculateResponse | null) => {
    if (calcRes) {
      setResult(calcRes)
      setError(null)
    }
  }

  const mergeWellParams = useCallback((base: WellParams, incoming: Partial<WellParams>): WellParams => {
    const pickDefined = (obj: Record<string, unknown> | undefined) => {
      const clean: Record<string, unknown> = {}
      if (!obj) return clean
      for (const [k, v] of Object.entries(obj)) {
        if (v !== null && v !== undefined && !(typeof v === 'number' && !Number.isFinite(v))) {
          clean[k] = v
        }
      }
      return clean
    }

    const incIpr = pickDefined(incoming.ipr as Record<string, unknown> | undefined)
    const rawVlp = (incoming.vlp ?? {}) as Record<string, unknown>
    const incVlp = pickDefined(rawVlp)
    const incTubing = pickDefined(rawVlp.tubing as Record<string, unknown> | undefined)
    const incCasing = pickDefined(rawVlp.casing as Record<string, unknown> | undefined)
    const incPvt = pickDefined(rawVlp.pvt as Record<string, unknown> | undefined)
    const incInclinometry = rawVlp.inclinometry as { MD?: number[]; TVD?: number[] } | undefined
    const nextWct = typeof incIpr.wct === 'number' ? incIpr.wct : base.ipr.wct

    delete incVlp.tubing
    delete incVlp.casing
    delete incVlp.pvt
    delete incVlp.inclinometry

    return {
      ...base,
      ipr: {
        ...base.ipr,
        ...incIpr,
      },
      vlp: {
        ...base.vlp,
        ...incVlp,
        inclinometry:
          Array.isArray(incInclinometry?.MD) &&
          incInclinometry.MD.length > 0 &&
          Array.isArray(incInclinometry?.TVD) &&
          incInclinometry.TVD.length > 0
            ? { MD: incInclinometry.MD, TVD: incInclinometry.TVD }
            : base.vlp.inclinometry,
        casing: {
          ...base.vlp.casing,
          ...incCasing,
        },
        tubing: {
          ...base.vlp.tubing,
          ...incTubing,
        },
        pvt: {
          ...base.vlp.pvt,
          ...incPvt,
          wct: typeof incPvt.wct === 'number' ? incPvt.wct : nextWct,
        },
      },
    }
  }, [])

  const handleApplyAndCalculate = useCallback(
    async (partial: Partial<WellParams>) => {
      const nextParams = mergeWellParams(params, partial)
      setParams(nextParams)
      setLoading(true)
      setError(null)
      try {
        const resp = await api.calculate(nextParams)
        setResult(resp)
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Неизвестная ошибка расчета'
        setError(msg)
      } finally {
        setLoading(false)
      }
    },
    [mergeWellParams, params],
  )

  const handleResetSession = useCallback(() => {
    clearPersistedJson(WELL_PARAMS_COOKIE_KEY)
    setParams(FALLBACK_PRESETS[0].data)
    setResetSignal((s) => s + 1)
    setError(null)
    setImportStatus(null)
  }, [])

  const handleMainFileImport = useCallback(async (file?: File) => {
    if (!file || importBusy) return
    setImportBusy(true)
    setError(null)
    setImportStatus(`Разбор файла «${file.name}»...`)
    try {
      const isImage = /\.(png|jpe?g|webp)$/i.test(file.name) || file.type.startsWith('image/')
      let parsed: Partial<WellParams> | null = null
      let extractedCount = 0
      let fallbackMessage = ''

      const countNumericLeaves = (obj: unknown): number => {
        if (!obj || typeof obj !== 'object') return 0
        let count = 0
        for (const val of Object.values(obj as Record<string, unknown>)) {
          if (typeof val === 'number' && Number.isFinite(val)) count += 1
          else if (val && typeof val === 'object' && !Array.isArray(val)) count += countNumericLeaves(val)
          else if (Array.isArray(val) && val.length > 0) count += 1
        }
        return count
      }

      if (isImage) {
        const res = await api.visionUpload(file)
        parsed = res.extracted_params ?? null
        extractedCount = countNumericLeaves(parsed)
        fallbackMessage = res.message ?? ''
      } else {
        const res = await api.upload(file)
        parsed = res.parsed_params ?? null
        extractedCount = Math.max(countNumericLeaves(parsed), Object.keys(res.extracted_values ?? {}).length)
      }

      if (!parsed || extractedCount === 0) {
        setImportStatus(fallbackMessage || `Файл «${file.name}» прочитан, но числовые параметры скважины не найдены`)
        return
      }

      const nextParams = mergeWellParams(params, parsed)
      setParams(nextParams)
      setLoading(true)
      try {
        const calcResp = await api.calculate(nextParams)
        setResult(calcResp)
        setImportStatus(`«${file.name}» разобран (${extractedCount} полей, сохранён на сервере) — расчёт и график обновлены`)
      } catch (calcErr) {
        const calcMsg = calcErr instanceof Error ? calcErr.message : 'Неизвестная ошибка расчета'
        setError(calcMsg)
        setImportStatus(`«${file.name}» загружен, но расчёт не сошёлся: ${calcMsg}`)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Не удалось разобрать файл'
      setImportStatus(`Ошибка загрузки: ${msg}`)
    } finally {
      setLoading(false)
      setImportBusy(false)
    }
  }, [importBusy, mergeWellParams, params])

  return (
    <div className="dashboard-frame">
      <aside className="side-rail">
        <nav className="rail-nav" aria-label="Основная навигация">
          <button className="rail-link active" type="button"><span className="rail-icon">⌂</span>Главная</button>
          <button className="rail-link" type="button" onClick={() => openTool('optimize')}><span className="rail-icon">▦</span>Инструменты</button>
          <button className="rail-link" type="button" onClick={() => openTool('rag')}><span className="rail-icon">≡</span>База методик</button>
          <button className="rail-link" type="button" onClick={() => openTool('report')}><span className="rail-icon">▤</span>Отчёты</button>
          <button className="rail-link" type="button" onClick={() => setSettingsOpen(true)}><span className="rail-icon">⚙</span>Настройки</button>
        </nav>
      </aside>
      <div className="app-shell design-1">
      <div className="page-heading">
        <div><h1>Анализ работы скважины</h1></div>
      </div>
      <div className="workspace-caption"><strong>Параметры расчёта</strong><span>Настройте пласт, свойства флюидов и конструкцию скважины</span></div>

      {/* Рабочая область: параметры и результаты */}
      <main className="app-main-layout">
        {/* Колонка 1: Форма параметров и пресетов */}
        <section className="layout-col col-params">
          <div
            onDragOver={(event) => {
              event.preventDefault()
              setImportDragActive(true)
            }}
            onDragLeave={() => setImportDragActive(false)}
            onDrop={(event) => {
              event.preventDefault()
              setImportDragActive(false)
              const file = event.dataTransfer.files?.[0]
              if (file) void handleMainFileImport(file)
            }}
            style={{
              marginBottom: '12px',
              padding: '10px 14px',
              borderRadius: '8px',
              border: `1px dashed ${importDragActive ? 'var(--accent)' : 'var(--line)'}`,
              background: importDragActive ? 'var(--accent-soft)' : 'var(--surface)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '10px',
              flexWrap: 'wrap',
            }}
          >
            <input
              ref={mainFileInputRef}
              type="file"
              accept=".json,.txt,.csv,.xlsx,.docx,.pdf,.png,.jpg,.jpeg,.webp"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) void handleMainFileImport(file)
              }}
            />
            <div style={{ minWidth: 0, flex: '1 1 200px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--ink)' }}>
                {importBusy ? 'Разбор файла...' : 'Импорт файла с параметрами'}
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--muted)', whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.35, marginTop: '2px' }}>
                {importStatus ?? 'Перетащите .json, .txt, .csv, .xlsx, .docx, .pdf или фото'}
              </div>
            </div>
            <button
              type="button"
              className="btn-quick-calc"
              disabled={importBusy}
              onClick={() => mainFileInputRef.current?.click()}
            >
              {importBusy ? 'Загрузка...' : 'Загрузить файл'}
            </button>
          </div>
          <WellInputForm
            params={params}
            onChange={setParams}
            onCalculate={handleCalculate}
            loading={loading}
            presets={presets}
            onSelectPreset={handleSelectPreset}
          />
        </section>

        {/* Колонка 2: KPI карточки, график и инструменты */}
        <section className="layout-col col-results">
          <OperatingPointCards
            result={result}
            loading={loading}
            error={error}
            warnings={physicsWarnings}
          />

          <div className="results-heading"><strong>Результаты расчёта</strong><span>Последний расчёт · только что</span></div>
          <div className="chart-panel-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <span className="chart-title-mark">N</span>
                <div><span className="eyebrow">ГРАФИК РАСЧЁТА</span><h3>График IPR и VLP</h3></div>
              </div>
              {result?.operating_point && (
                <div className="chart-legend-point">
                  <span className="point-dot" />
                  <span>
                    Точка: {result.operating_point.q_liq.toFixed(1)} м³/сут @ {result.operating_point.p_wf.toFixed(1)} атм
                  </span>
                </div>
              )}
            </div>

            <div className="chart-body">
              <NodalChart result={result} />
            </div>

            <div className="chart-footer-info">
              <span><i className="legend-line ipr"/> IPR</span>
              <span><i className="legend-line vlp"/> VLP</span>
              <span><i className="legend-point"/> Рабочая точка</span>
            </div>
          </div>
          <section className="secondary-tools">
            <div className="secondary-tools-heading"><div><span className="eyebrow">ИНСТРУМЕНТЫ</span><h2>Дополнительные инструменты</h2></div><button type="button" onClick={() => openTool('optimize')}>Все инструменты <span aria-hidden="true">→</span></button></div>
            <div className="secondary-tools-grid">
              <button type="button" onClick={() => openTool('whatif')}><span>↗</span><strong>What-if сценарии</strong><small>Проверить изменение параметров</small></button>
              <button type="button" onClick={() => openTool('optimize')}><span>⌁</span><strong>Оптимизация</strong><small>Подобрать режим работы</small></button>
              <button type="button" onClick={() => openTool('match')}><span>▤</span><strong>Сверка с замером</strong><small>Сопоставить модель и факт</small></button>
              <button type="button" onClick={() => openTool('report')}><span>⇧</span><strong>Отчёты</strong><small>Экспорт результатов расчёта</small></button>
            </div>
          </section>
        </section>

      </main>
      {toolsOpen && createPortal(
        <div className="tools-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setToolsOpen(false) }}>
          <section className="tools-dialog design-1" role="dialog" aria-modal="true" aria-label="Инженерные инструменты">
            <header className="tools-dialog-header">
              <div><span className="eyebrow">МОДУЛИ</span><h2>Инженерные инструменты</h2></div>
              <button type="button" className="tools-dialog-close" onClick={() => setToolsOpen(false)} aria-label="Закрыть инструменты">×</button>
            </header>
            <div className="tools-dialog-body"><EnhancementWorkbench params={params} result={result} onParams={setParams} initialTab={activeTool} /></div>
          </section>
        </div>,
        document.body,
      )}
      {chatOpen ? (
        <section
          ref={chatWidgetRef}
          className={`chat-floating-widget ${chatExpanded ? 'expanded' : 'compact'} ${isDraggingChat ? 'is-dragging' : ''}`}
          style={chatPos ? { left: chatPos.x, top: chatPos.y, right: 'auto', bottom: 'auto' } : undefined}
          role="dialog"
          aria-modal="false"
          aria-label="Инженерный ассистент"
        >
          <AiChatPanel
            params={params}
            onResult={handleResultFromChat}
            onParams={setParams}
            expanded={chatExpanded}
            onToggleExpand={() => setChatExpanded(!chatExpanded)}
            onClose={() => setChatOpen(false)}
            onHeaderPointerDown={handleChatHeaderPointerDown}
            isDragging={isDraggingChat}
            onOpenSettings={() => setSettingsOpen(true)}
            settingsVersion={settingsVersion}
            resetSignal={resetSignal}
          />
        </section>
      ) : (
        <button className="chat-fab" type="button" onClick={() => setChatOpen(true)} aria-label="Открыть чат ассистента" title="Консультант по расчётам">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <span>Ассистент</span>
        </button>
      )}
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSettingsChanged={() => setSettingsVersion((v) => v + 1)}
        onApplyParams={handleApplyAndCalculate}
        onResetSession={handleResetSession}
      />
      </div>
    </div>
  )
}
