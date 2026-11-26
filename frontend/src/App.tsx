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
import { PdfOcrModeSelect } from './components/PdfOcrModeSelect'
import { validateWellPhysics } from './utils/physics'
import { deleteCookie, getCookie, loadJson, saveJson, setCookie } from './utils/storage'

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

const MAIN_STORAGE_KEYS = {
  params: 'wmb_well_params',
  result: 'wmb_last_result',
} as const

type WellFundItem = {
  id: string
  name: string
  params: WellParams
  result: CalculateResponse | null
}

function isValidWellParams(val: unknown): val is WellParams {
  if (!val || typeof val !== 'object') return false
  const obj = val as Record<string, unknown>
  const ipr = obj.ipr as Record<string, unknown> | undefined
  const vlp = obj.vlp as Record<string, unknown> | undefined
  if (!ipr || typeof ipr !== 'object' || !vlp || typeof vlp !== 'object') return false
  const inc = vlp.inclinometry as Record<string, unknown> | undefined
  return Boolean(
    typeof ipr.p_res === 'number' &&
    typeof ipr.pi === 'number' &&
    inc &&
    Array.isArray(inc.MD) && inc.MD.length >= 2 &&
    Array.isArray(inc.TVD) && inc.TVD.length >= 2 &&
    vlp.casing && typeof vlp.casing === 'object' &&
    vlp.tubing && typeof vlp.tubing === 'object' &&
    vlp.pvt && typeof vlp.pvt === 'object',
  )
}

function isValidCalcResult(val: unknown): val is CalculateResponse {
  if (!val || typeof val !== 'object') return false
  const obj = val as Record<string, unknown>
  return Boolean(obj.ipr && typeof obj.ipr === 'object' && obj.vlp && typeof obj.vlp === 'object')
}

export default function App() {
  const [presets, setPresets] = useState<PresetItem[]>(FALLBACK_PRESETS)
  const [params, setParams] = useState<WellParams>(() => {
    const cookieRaw = getCookie('wmb_well_params')
    if (cookieRaw) {
      try {
        const parsed = JSON.parse(cookieRaw)
        if (isValidWellParams(parsed)) return parsed
      } catch {
        // fallback to localStorage
      }
    }
    return loadJson<WellParams>(MAIN_STORAGE_KEYS.params, FALLBACK_PRESETS[0].data, isValidWellParams)
  })
  const [result, setResult] = useState<CalculateResponse | null>(() =>
    loadJson<CalculateResponse | null>(
      MAIN_STORAGE_KEYS.result,
      null,
      (v): v is CalculateResponse | null => v === null || isValidCalcResult(v),
    ),
  )

  useEffect(() => {
    saveJson(MAIN_STORAGE_KEYS.params, params)
    try {
      setCookie('wmb_well_params', JSON.stringify(params))
    } catch {
      // ignore cookie write errors
    }
  }, [params])

  useEffect(() => {
    if (result) {
      saveJson(MAIN_STORAGE_KEYS.result, result)
    }
  }, [result])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [resetSignal, setResetSignal] = useState(0)
  const [activeTool, setActiveTool] = useState<EnhancementId>('optimize')
  const [chatExpanded, setChatExpanded] = useState(false)
  const [chatPos, setChatPos] = useState<{ x: number; y: number } | null>(null)
  const [isDraggingChat, setIsDraggingChat] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [importDragActive, setImportDragActive] = useState(false)
  const [importStatus, setImportStatus] = useState<string | null>(null)
  const [serverFundWells, setServerFundWells] = useState<WellFundItem[]>([])
  const [importedWells, setImportedWells] = useState<WellFundItem[]>([])
  const [activeImportedWellId, setActiveImportedWellId] = useState<string | null>(null)
  const chatWidgetRef = useRef<HTMLElement>(null)
  const mainFileInputRef = useRef<HTMLInputElement>(null)
  const mainFolderInputRef = useRef<HTMLInputElement>(null)
  const dragOffsetRef = useRef<{ dx: number; dy: number }>({ dx: 0, dy: 0 })

  const openTool = useCallback((tool: EnhancementId) => {
    setImportOpen(false)
    setSettingsOpen(false)
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

  const applyCalculationOutcome = useCallback(
    (resp: CalculateResponse, _targetParams?: WellParams | null) => {
      setResult(resp)
      setError(null)
      return true
    },
    [],
  )

  // Вызов расчета узлового анализа
  const handleCalculate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.calculate(params)
      applyCalculationOutcome(resp, params)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Неизвестная ошибка расчета'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [params, applyCalculationOutcome])

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
      applyCalculationOutcome(calcRes, params)
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

  // Автозагрузка фонда скважин из samples/ для верхнего переключателя
  useEffect(() => {
    api.scanFolder()
      .then((res) => {
        const ready = (res.wells ?? [])
          .filter((w) => w.extracted_parameters)
          .sort((a, b) => a.filename.localeCompare(b.filename))
          .map((w, idx) => ({
            id: `sample-${idx}-${w.filename}`,
            name: w.well_name || w.filename,
            params: mergeWellParams(FALLBACK_PRESETS[0].data, w.extracted_parameters!),
            result: null as CalculateResponse | null,
          }))
        if (ready.length > 0) {
          setServerFundWells(ready)
          setActiveImportedWellId((prev) => prev ?? ready[0].id)
        }
      })
      .catch(() => {
        // Fallback на presets остаётся автоматически
      })
  }, [mergeWellParams])

  const handleSelectFundWell = useCallback(
    async (item: WellFundItem) => {
      setActiveImportedWellId(item.id)
      setParams(item.params)
      setImportStatus(`Активна скважина «${item.name}»`)
      if (item.result) {
        applyCalculationOutcome(item.result, item.params)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const calcResp = await api.calculate(item.params)
        applyCalculationOutcome(calcResp, item.params)
        setServerFundWells((prev) => prev.map((w) => (w.id === item.id ? { ...w, result: calcResp } : w)))
        setImportedWells((prev) => prev.map((w) => (w.id === item.id ? { ...w, result: calcResp } : w)))
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Неизвестная ошибка расчета'
        setError(msg)
      } finally {
        setLoading(false)
      }
    },
    [applyCalculationOutcome],
  )

  const SUPPORTED_EXT_RE = /\.(json|txt|csv|xlsx|docx|pdf|zip|png|jpe?g|webp)$/i

  const collectDroppedFiles = useCallback(async (dataTransfer: DataTransfer): Promise<File[]> => {
    const collected: File[] = []
    const items = Array.from(dataTransfer.items ?? [])

    const readEntry = async (entry: FileSystemEntry): Promise<void> => {
      if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === '__MACOSX') return
      if (entry.isFile) {
        const fileEntry = entry as FileSystemFileEntry
        await new Promise<void>((resolve) => {
          fileEntry.file(
            (file) => {
              if (file.size > 0 && SUPPORTED_EXT_RE.test(file.name)) {
                collected.push(file)
              }
              resolve()
            },
            () => resolve(),
          )
        })
      } else if (entry.isDirectory) {
        const dirEntry = entry as FileSystemDirectoryEntry
        const reader = dirEntry.createReader()
        while (true) {
          const batch = await new Promise<FileSystemEntry[]>((resolve) => {
            reader.readEntries(
              (entries) => resolve(entries),
              () => resolve([]),
            )
          })
          if (!batch.length) break
          for (const child of batch) {
            await readEntry(child)
          }
        }
      }
    }

    const entries = items
      .map((item) => (typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null))
      .filter((entry): entry is FileSystemEntry => entry !== null)

    if (entries.length > 0) {
      for (const entry of entries) {
        await readEntry(entry)
      }
      return collected
    }

    for (const file of Array.from(dataTransfer.files ?? [])) {
      if (file.size > 0 && SUPPORTED_EXT_RE.test(file.name)) {
        collected.push(file)
      }
    }
    return collected
  }, [])

  const handleMainFilesImport = useCallback(async (rawFiles: File[]) => {
    const files = rawFiles.filter((f) => f.size > 0 && SUPPORTED_EXT_RE.test(f.name))
    if (files.length === 0) {
      setImportStatus('В папке/выборе не найдено поддерживаемых файлов (.json, .txt, .csv, .xlsx, .docx, .pdf, .zip, фото)')
      return
    }
    if (importBusy) return
    setImportBusy(true)
    setError(null)
    setImportStatus(files.length === 1 ? `Разбор «${files[0].name}»...` : `Разбор пакета (${files.length} файлов)...`)

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

    try {
      const parsedEntries: Array<{ name: string; params: WellParams; fieldsCount: number }> = []
      const baseForMerge = files.length > 1 || /\.zip$/i.test(files[0].name) ? FALLBACK_PRESETS[0].data : params

      for (const file of files.slice(0, 30)) {
        const isImage = /\.(png|jpe?g|webp)$/i.test(file.name) || file.type.startsWith('image/')
        try {
          if (isImage) {
            const res = await api.visionUpload(file)
            const fieldsCount = countNumericLeaves(res.extracted_params)
            if (res.extracted_params && fieldsCount > 0) {
              parsedEntries.push({
                name: file.name,
                params: mergeWellParams(baseForMerge, res.extracted_params),
                fieldsCount,
              })
            }
          } else {
            const res = await api.upload(file)
            if (Array.isArray(res.wells) && res.wells.length > 0) {
              for (const w of res.wells) {
                const fc = countNumericLeaves(w.parsed_params)
                if (w.parsed_params && fc > 0) {
                  parsedEntries.push({
                    name: w.filename,
                    params: mergeWellParams(FALLBACK_PRESETS[0].data, w.parsed_params),
                    fieldsCount: fc,
                  })
                }
              }
            } else {
              const fc = Math.max(countNumericLeaves(res.parsed_params), Object.keys(res.extracted_values ?? {}).length)
              if (res.parsed_params && fc > 0) {
                parsedEntries.push({
                  name: file.name,
                  params: mergeWellParams(baseForMerge, res.parsed_params),
                  fieldsCount: fc,
                })
              }
            }
          }
        } catch {
          // Пропускаем отдельный повреждённый файл, чтобы пакет дочитался
        }
      }

      if (parsedEntries.length === 0) {
        setImportStatus(
          files.length === 1
            ? `Файл «${files[0].name}» прочитан, но числовые параметры скважины не найдены`
            : `Проверено файлов: ${files.length}, но параметры скважин не найдены`,
        )
        return
      }

      setLoading(true)
      const calculatedWells: Array<{ id: string; name: string; params: WellParams; result: CalculateResponse | null }> = []
      for (let i = 0; i < parsedEntries.length; i += 1) {
        const entry = parsedEntries[i]
        let calcResp: CalculateResponse | null = null
        try {
          calcResp = await api.calculate(entry.params)
        } catch {
          calcResp = null
        }
        calculatedWells.push({
          id: `${i}-${entry.name}`,
          name: entry.name,
          params: entry.params,
          result: calcResp,
        })
      }

      const activeWell = calculatedWells.find((w) => w.result !== null) ?? calculatedWells[0]
      setImportedWells(calculatedWells)
      setActiveImportedWellId(activeWell.id)
      setParams(activeWell.params)
      if (activeWell.result) {
        applyCalculationOutcome(activeWell.result, activeWell.params)
      }

      if (calculatedWells.length === 1) {
        setImportStatus(`«${activeWell.name}» разобран (${parsedEntries[0].fieldsCount} полей) — расчёт и график обновлены`)
      } else {
        const okCount = calculatedWells.filter((w) => w.result !== null).length
        setImportStatus(`Разобрано файлов: ${calculatedWells.length} (рассчитано: ${okCount}). Активна: «${activeWell.name}»`)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Не удалось разобрать файлы'
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
          <button className={`rail-link ${!toolsOpen && !settingsOpen && !importOpen ? 'active' : ''}`} type="button" onClick={() => { setToolsOpen(false); setSettingsOpen(false); setImportOpen(false) }}><span className="rail-icon">⌂</span>Главная</button>
          <button className={`rail-link ${toolsOpen && activeTool !== 'rag' && activeTool !== 'report' ? 'active' : ''}`} type="button" onClick={() => openTool('optimize')}><span className="rail-icon">▦</span>Инструменты</button>
          <button className={`rail-link ${toolsOpen && activeTool === 'rag' ? 'active' : ''}`} type="button" onClick={() => openTool('rag')}><span className="rail-icon">≡</span>База методик</button>
          <button className={`rail-link ${importOpen ? 'active' : ''}`} type="button" onClick={() => { setToolsOpen(false); setSettingsOpen(false); setImportOpen(true) }}><span className="rail-icon">⇩</span>Импорт</button>
          <button className={`rail-link ${toolsOpen && activeTool === 'report' ? 'active' : ''}`} type="button" onClick={() => openTool('report')}><span className="rail-icon">▤</span>Отчёты</button>
          <button className={`rail-link ${settingsOpen ? 'active' : ''}`} type="button" onClick={() => { setToolsOpen(false); setImportOpen(false); setSettingsOpen(true) }}><span className="rail-icon">⚙</span>Настройки</button>
        </nav>
      </aside>
      <div className="app-shell design-1">
      <div className="page-heading">
        <div><h1>Анализ работы скважины</h1></div>
      </div>

      {/* Верхняя строка вкладок фонда скважин (стиль вкладок браузера) */}
      {(() => {
        const fundWells: WellFundItem[] =
          importedWells.length > 0
            ? importedWells
            : serverFundWells.length > 0
              ? serverFundWells
              : presets.map((p) => ({
                  id: p.id,
                  name: p.name.split('(')[0].trim(),
                  params: p.data,
                  result: null,
                }))
        return (
          <div className="well-tabs-strip" role="tablist" aria-label="Фонд скважин">
            <div className="well-tabs-list">
              {fundWells.map((item) => {
                const isActive = activeImportedWellId === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    className={`well-browser-tab ${isActive ? 'active' : ''}`}
                    onClick={() => void handleSelectFundWell(item)}
                    disabled={loading}
                    title={item.name}
                  >
                    <span className="well-tab-title">{item.name}</span>
                    {item.result?.operating_point && (
                      <span className="well-tab-q">{item.result.operating_point.q_liq.toFixed(1)} м³/сут</span>
                    )}
                  </button>
                )
              })}
              <button
                type="button"
                className="well-browser-tab-add"
                onClick={() => {
                  setToolsOpen(false)
                  setSettingsOpen(false)
                  setImportOpen(true)
                }}
                title="Загрузить файлы, папку или .zip"
                aria-label="Добавить скважины из файла или папки"
              >
                +
              </button>
            </div>
            <div className="well-tabs-right">
              {importedWells.length > 0 && (
                <button
                  type="button"
                  className="well-tab-link"
                  onClick={() => {
                    setImportedWells([])
                    setActiveImportedWellId(serverFundWells[0]?.id ?? null)
                    setImportStatus(null)
                  }}
                >
                  Вернуть samples
                </button>
              )}
              <button
                type="button"
                className="well-tab-link"
                onClick={() => openTool('batch')}
              >
                Сводка фонда
              </button>
            </div>
          </div>
        )
      })()}

      <div className="workspace-caption"><strong>Параметры расчёта</strong><span>Настройте пласт, свойства флюидов и конструкцию скважины</span></div>

      {/* Рабочая область: параметры и результаты */}
      <main className="app-main-layout">
        {/* Колонка 1: Форма параметров и пресетов */}
        <section className="layout-col col-params">
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
            physicalWarnings={validateWellPhysics(params)}
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
      {importOpen && createPortal(
        <div className="tools-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setImportOpen(false) }}>
          <section className="tools-dialog design-1" role="dialog" aria-modal="true" aria-label="Импорт файлов и папок">
            <header className="tools-dialog-header">
              <div><span className="eyebrow">ЗАГРУЗКА ДАННЫХ</span><h2>Импорт файла или папки</h2></div>
              <button type="button" className="tools-dialog-close" onClick={() => setImportOpen(false)} aria-label="Закрыть импорт">×</button>
            </header>
            <div className="tools-dialog-body import-drawer-body">
              <div className="tool-pane">
                <p>
                  Перетащите сюда или выберите файлы скважин (<code>.json</code>, <code>.txt</code>, <code>.csv</code>,{' '}
                  <code>.xlsx</code>, <code>.docx</code>, <code>.pdf</code> с OCR, фото паспорта или <code>.zip</code>-архив)
                  или целую папку — параметры подставятся в модель и сразу рассчитаются.
                </p>
                <PdfOcrModeSelect />
                <div
                  className={`main-import-dropzone ${importDragActive ? 'is-dragover' : ''} ${importStatus?.startsWith('Ошибка') ? 'is-error' : ''}`}
                  onDragOver={(event) => {
                    event.preventDefault()
                    setImportDragActive(true)
                  }}
                  onDragLeave={() => setImportDragActive(false)}
                  onDrop={(event) => {
                    event.preventDefault()
                    setImportDragActive(false)
                    void collectDroppedFiles(event.dataTransfer).then((files) => handleMainFilesImport(files))
                  }}
                >
                  <input
                    ref={mainFileInputRef}
                    type="file"
                    accept=".json,.txt,.csv,.xlsx,.docx,.pdf,.zip,.png,.jpg,.jpeg,.webp"
                    multiple
                    hidden
                    onChange={(event) => {
                      const files = Array.from(event.target.files ?? [])
                      event.target.value = ''
                      if (files.length > 0) void handleMainFilesImport(files)
                    }}
                  />
                  <input
                    ref={mainFolderInputRef}
                    type="file"
                    {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
                    multiple
                    hidden
                    onChange={(event) => {
                      const files = Array.from(event.target.files ?? [])
                      event.target.value = ''
                      if (files.length > 0) void handleMainFilesImport(files)
                    }}
                  />
                  <div className="main-import-row">
                    <div className="main-import-info">
                      <div className="main-import-title">
                        {importBusy ? 'Разбор...' : 'Импорт файла или папки'}
                      </div>
                      <div className={`main-import-status ${importStatus?.startsWith('Ошибка') ? 'is-error' : ''}`}>
                        {importStatus ?? 'Перетащите папку, .zip или файл (.json, .txt, .csv, .xlsx, .pdf, фото)'}
                      </div>
                    </div>
                    <div className="main-import-actions">
                      <button
                        type="button"
                        className="btn-import-secondary"
                        disabled={importBusy}
                        onClick={() => mainFolderInputRef.current?.click()}
                      >
                        Папка
                      </button>
                      <button
                        type="button"
                        className="btn-quick-calc"
                        disabled={importBusy}
                        onClick={() => mainFileInputRef.current?.click()}
                      >
                        {importBusy ? 'Загрузка...' : 'Загрузить файл'}
                      </button>
                    </div>
                  </div>
                  {importedWells.length > 1 && (
                    <div className="imported-wells-bar">
                      {importedWells.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className={`imported-well-chip ${activeImportedWellId === item.id ? 'active' : ''}`}
                          onClick={() => void handleSelectFundWell(item)}
                        >
                          {item.name}
                          {item.result?.operating_point ? ` (${item.result.operating_point.q_liq.toFixed(1)} м³/сут)` : ''}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
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
      {settingsOpen && createPortal(
        <SettingsModal
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          onApplyParams={(partial) => {
            const next = mergeWellParams(params, partial)
            setParams(next)
            setSettingsOpen(false)
            setLoading(true)
            api.calculate(next)
              .then((resp) => applyCalculationOutcome(resp, next))
              .catch((err) => setError(err instanceof Error ? err.message : 'Ошибка расчета'))
              .finally(() => setLoading(false))
          }}
          onResetSession={() => {
            deleteCookie('wmb_well_params')
            saveJson(MAIN_STORAGE_KEYS.params, FALLBACK_PRESETS[0].data)
            setParams(FALLBACK_PRESETS[0].data)
            setError(null)
            setResetSignal((v) => v + 1)
            setLoading(true)
            api.calculate(FALLBACK_PRESETS[0].data)
              .then((resp) => applyCalculationOutcome(resp, FALLBACK_PRESETS[0].data))
              .catch(() => {})
              .finally(() => setLoading(false))
          }}
        />,
        document.body,
      )}
      </div>
    </div>
  )
}
