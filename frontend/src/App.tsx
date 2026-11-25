import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api/client'
import type { CalculateResponse, PresetItem, WellParams } from './types/well'
import { WellInputForm } from './components/WellInputForm'
import { OperatingPointCards } from './components/OperatingPointCards'
import { NodalChart } from './components/NodalChart'
import { AiChatPanel } from './components/AiChatPanel'
import { EnhancementWorkbench, type EnhancementId } from './components/EnhancementWorkbench'
import { getCookie, loadJson, saveJson, setCookie } from './utils/storage'

const FALLBACK_PRESETS: PresetItem[] = [
  {
    id: 'standard_oil',
    name: 'Стандартный нефтяной',
    description: 'Стандартная нефтяная скважина: P_res 220 бар, P_b 180 бар, WCT 28%, НКТ 73 мм',
    data: {
      ipr: {
        p_res: 220.0,
        wct: 28.0,
        pi: 1.25,
        pb: 180.0,
        perm: 120,
        porosity: 0.18,
        points: 21,
      },
      vlp: {
        inclinometry: {
          MD: [0.0, 1000.0, 1800.0],
          TVD: [0.0, 1000.0, 1600.0],
        },
        casing: { d: 0.12 },
        tubing: { d: 0.073, h_mes: 800.0 },
        pvt: {
          wct: 28.0,
          rp: 80.0,
          gamma_oil: 0.84,
          gamma_gas: 0.7,
          gamma_wat: 1.0,
          t_res: 80.0,
        },
        p_wh: 1.0,
        geo_grad: 3.0,
        h_res: 1800.0,
        roughness: 0.0001,
        q_max: 300.0,
        points: 21,
      },
    },
  },
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
        perm: 100,
        porosity: 0.16,
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
        perm: 150,
        porosity: 0.20,
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
        roughness: 0.0001,
        q_max: 500.0,
        points: 21,
      },
    },
  },
  {
    id: 'well_no_intersection',
    name: 'Без рабочей точки (не фонтанирует)',
    description: 'Низкое пластовое давление: кривая VLP выше IPR',
    data: {
      ipr: {
        p_res: 45.0,
        wct: 30.0,
        pi: 0.5,
        pb: 30.0,
        perm: 35,
        porosity: 0.12,
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
        roughness: 0.0001,
        q_max: 300.0,
        points: 21,
      },
    },
  },
]

const STORAGE_KEYS = {
  presetId: 'wmb_preset_id',
  params: 'wmb_well_params',
  result: 'wmb_last_result',
  darkMode: 'wmb_dark_mode',
} as const

function isValidWellParams(val: unknown): val is WellParams {
  if (!val || typeof val !== 'object') return false
  const obj = val as Record<string, unknown>
  return Boolean(obj.ipr && typeof obj.ipr === 'object' && obj.vlp && typeof obj.vlp === 'object')
}

function isValidCalculateResponse(val: unknown): val is CalculateResponse {
  if (!val || typeof val !== 'object') return false
  const obj = val as Record<string, unknown>
  return Boolean(obj.ipr && typeof obj.ipr === 'object' && obj.vlp && typeof obj.vlp === 'object')
}

const DEFAULT_RESULT: CalculateResponse = {
  status: 'ok',
  ipr: {
    q_liq: [0, 25, 50, 75, 100, 125, 134, 150, 175, 200, 225, 250],
    p_wf: [220, 212, 202, 190, 175, 155, 145, 130, 100, 70, 40, 10],
  },
  vlp: {
    q_liq: [0, 25, 50, 75, 100, 125, 134, 150, 175, 200, 225, 250],
    p_wf: [10, 30, 52, 78, 105, 133, 145, 160, 178, 195, 210, 225],
  },
  operating_point: { q_liq: 134.0, p_wf: 145.0 },
  meta: { calc_time_ms: 18.4 },
}

export default function App() {
  const [presets, setPresets] = useState<PresetItem[]>(FALLBACK_PRESETS)
  const [selectedPresetId, setSelectedPresetId] = useState<string>(() => {
    return getCookie(STORAGE_KEYS.presetId) || loadJson<string>(STORAGE_KEYS.presetId, FALLBACK_PRESETS[0].id)
  })
  const [params, setParams] = useState<WellParams>(() =>
    loadJson<WellParams>(STORAGE_KEYS.params, FALLBACK_PRESETS[0].data, isValidWellParams),
  )
  const [result, setResult] = useState<CalculateResponse | null>(() =>
    loadJson<CalculateResponse>(STORAGE_KEYS.result, DEFAULT_RESULT, isValidCalculateResponse),
  )
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [activeTool, setActiveTool] = useState<EnhancementId>('whatif')
  const [toolsTab, setToolsTab] = useState<'tools' | 'analytics' | 'docs'>('tools')
  const [activeNav, setActiveNav] = useState('home')
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    const fromCookie = getCookie(STORAGE_KEYS.darkMode)
    if (fromCookie !== null) return fromCookie === '1'
    return loadJson<boolean>(STORAGE_KEYS.darkMode, false)
  })
  const [presetDropdownOpen, setPresetDropdownOpen] = useState(false)

  // Сохраняем выбранные параметры, пресет, тему и результат между перезаходами
  useEffect(() => {
    setCookie(STORAGE_KEYS.presetId, selectedPresetId)
    saveJson(STORAGE_KEYS.presetId, selectedPresetId)
  }, [selectedPresetId])

  useEffect(() => {
    saveJson(STORAGE_KEYS.params, params)
  }, [params])

  useEffect(() => {
    if (result) {
      saveJson(STORAGE_KEYS.result, result)
    }
  }, [result])

  useEffect(() => {
    setCookie(STORAGE_KEYS.darkMode, isDarkMode ? '1' : '0')
    saveJson(STORAGE_KEYS.darkMode, isDarkMode)
  }, [isDarkMode])

  const loadInputRef = useRef<HTMLInputElement>(null)

  // Загрузка пресетов с бэкенда при старте
  useEffect(() => {
    api.presets()
      .then((items) => {
        if (Array.isArray(items) && items.length > 0) {
          // Keep standard_oil at front if not returned by server
          const list = items.some((p) => p.id === 'standard_oil')
            ? items
            : [FALLBACK_PRESETS[0], ...items]
          setPresets(list)
        }
      })
      .catch(() => {
        // Fallback already in state
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

  // Автоматический расчет при монтировании
  useEffect(() => {
    handleCalculate()
  }, [])

  const handleSelectPreset = (preset: PresetItem) => {
    setSelectedPresetId(preset.id)
    setParams(preset.data)
    setError(null)
    setPresetDropdownOpen(false)
  }

  const handleResultFromChat = (calcRes?: CalculateResponse | null) => {
    if (calcRes) {
      setResult(calcRes)
      setError(null)
    }
  }

  const openSpecificTool = (id: EnhancementId) => {
    setActiveTool(id)
    setToolsOpen(true)
  }

  const handleSaveParams = () => {
    const blob = new Blob([JSON.stringify(params, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `well_params_${selectedPresetId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleLoadParams = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const loaded = JSON.parse(event.target?.result as string)
        if (loaded && loaded.ipr && loaded.vlp) {
          setParams(loaded)
          handleCalculate()
        }
      } catch {
        alert('Некорректный JSON файл параметров')
      }
    }
    reader.readAsText(file)
  }

  const selectedPreset = presets.find((p) => p.id === selectedPresetId) || presets[0]

  return (
    <div className={`dashboard-root ${isDarkMode ? 'dark-theme' : 'light-theme'}`}>
      {/* 1. Левый сайдбар навигации */}
      <aside className="main-side-rail">
        <div className="rail-top">
          <a className="brand-logo-lockup" href="/" aria-label="Well Model Builder">
            <svg className="droplet-brand-icon" width="28" height="28" viewBox="0 0 24 24" fill="#2563eb">
              <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
            </svg>
            <div className="brand-name-group">
              <span className="brand-primary">Well Model</span>
              <span className="brand-secondary">Builder</span>
            </div>
          </a>

          <nav className="rail-navigation">
            <button
              type="button"
              className={`rail-nav-item ${activeNav === 'home' ? 'active' : ''}`}
              onClick={() => setActiveNav('home')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                <polyline points="9 22 9 12 15 12 15 22" />
              </svg>
              <span>Главная</span>
            </button>

            <button
              type="button"
              className={`rail-nav-item ${activeNav === 'tools' ? 'active' : ''}`}
              onClick={() => {
                setActiveNav('tools')
                setToolsOpen(true)
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
              <span>Инструменты</span>
            </button>

            <button
              type="button"
              className={`rail-nav-item ${activeNav === 'methodology' ? 'active' : ''}`}
              onClick={() => openSpecificTool('rag')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <line x1="3" y1="6" x2="3.01" y2="6" />
                <line x1="3" y1="12" x2="3.01" y2="12" />
                <line x1="3" y1="18" x2="3.01" y2="18" />
              </svg>
              <span>База методик</span>
            </button>

            <button
              type="button"
              className={`rail-nav-item ${activeNav === 'reports' ? 'active' : ''}`}
              onClick={() => openSpecificTool('report')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
              <span>Отчёты</span>
            </button>

            <button
              type="button"
              className={`rail-nav-item ${activeNav === 'profile' ? 'active' : ''}`}
              onClick={() => setActiveNav('profile')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span>Профиль</span>
            </button>
          </nav>
        </div>

        <div className="rail-bottom">
          <div className="theme-toggle-cluster" role="radiogroup" aria-label="Переключение темы оформления">
            <button
              type="button"
              className={`theme-pill-btn ${!isDarkMode ? 'active' : ''}`}
              onClick={() => setIsDarkMode(false)}
              title="Светлая тема"
            >
              ☼
            </button>
            <button
              type="button"
              className={`theme-pill-btn ${isDarkMode ? 'active' : ''}`}
              onClick={() => setIsDarkMode(true)}
              title="Тёмная тема"
            >
              ☽
            </button>
          </div>

          <div className="rail-network-status">
            <span className="network-dot pulse" />
            <span className="network-text">Система<br /><strong>в сети</strong></span>
          </div>

          <div className="rail-app-version">v1.0.0</div>
        </div>
      </aside>

      {/* 2. Основная рабочая зона */}
      <div className="main-content-flow">
        {/* Верхний Header */}
        <header className="main-top-header">
          <div className="header-search-box">
            <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              placeholder="Поиск по параметрам, методикам... Ctrl + K"
              aria-label="Глобальный поиск"
            />
            <kbd className="search-kbd-badge">Ctrl + K</kbd>
          </div>

          <div className="header-right-tools">
            <button type="button" className="notification-bell-btn" title="Уведомления" aria-label="Уведомления">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
              <span className="unread-dot" />
            </button>

            <div className="user-avatar-badge" title="Инженер М.И.">
              MI
            </div>
          </div>
        </header>

        {/* Подзаголовок страницы и панель действий */}
        <div className="page-subheading-bar">
          <div className="page-title-stack">
            <h1 className="page-h1">Анализ работы скважины</h1>
            <p className="page-subtitle">Расчёт IPR, VLP и поиск рабочей точки</p>
          </div>

          <div className="page-actions-cluster">
            {/* Дропдаун выбора пресета */}
            <div className="preset-dropdown-container">
              <button
                type="button"
                className="preset-select-btn"
                onClick={() => setPresetDropdownOpen(!presetDropdownOpen)}
                aria-haspopup="listbox"
                aria-expanded={presetDropdownOpen}
              >
                <span className="preset-gear-ico">⚙</span>
                <span className="preset-btn-text">
                  Пресет: <strong>{selectedPreset.name}</strong>
                </span>
                <span className="preset-chevron">▾</span>
              </button>

              {presetDropdownOpen && (
                <div className="preset-dropdown-menu" role="listbox">
                  {presets.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className={`preset-dropdown-item ${p.id === selectedPresetId ? 'active' : ''}`}
                      onClick={() => handleSelectPreset(p)}
                    >
                      <strong>{p.name}</strong>
                      <small>{p.description}</small>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              type="button"
              className="action-ghost-btn"
              onClick={handleSaveParams}
              title="Сохранить текущие параметры в JSON файл"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                <polyline points="17 21 17 13 7 13 7 21" />
                <polyline points="7 3 7 8 15 8" />
              </svg>
              <span>Сохранить</span>
            </button>

            <button
              type="button"
              className="action-ghost-btn"
              onClick={() => loadInputRef.current?.click()}
              title="Загрузить параметры скважины из JSON файла"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <span>Загрузить</span>
            </button>
            <input ref={loadInputRef} type="file" accept=".json" hidden onChange={handleLoadParams} />

            <button
              type="button"
              className="action-primary-calc-btn"
              onClick={handleCalculate}
              disabled={loading}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <span>{loading ? 'Расчёт…' : 'Рассчитать'}</span>
            </button>
          </div>
        </div>

        {/* 3. Трехколоночная сетка приложения */}
        <main className="three-column-dashboard-grid">
          {/* Левая колонка: Форма параметров расчёта */}
          <section className="dashboard-col col-parameters" aria-label="Параметры расчёта">
            <WellInputForm
              params={params}
              onChange={setParams}
              onCalculate={handleCalculate}
              loading={loading}
              presets={presets}
              onSelectPreset={handleSelectPreset}
            />
          </section>

          {/* Центральная колонка: График IPR/VLP + 12 Инструментов */}
          <section className="dashboard-col col-center-workspace" aria-label="График и инженерные инструменты">
            {/* Верх: Карточка Графика */}
            <div className="card-panel-wrapper chart-panel-wrapper">
              <NodalChart result={result} loading={loading} />
            </div>

            {/* Низ: Карточка 12 Инструментов */}
            <div className="card-panel-wrapper secondary-tools-panel">
              <div className="tools-panel-tabs-bar">
                <button
                  type="button"
                  className={`tools-panel-tab ${toolsTab === 'tools' ? 'active' : ''}`}
                  onClick={() => setToolsTab('tools')}
                >
                  Дополнительные инструменты
                </button>
                <button
                  type="button"
                  className={`tools-panel-tab ${toolsTab === 'analytics' ? 'active' : ''}`}
                  onClick={() => openSpecificTool('optimize')}
                >
                  Графики и аналитика
                </button>
                <button
                  type="button"
                  className={`tools-panel-tab ${toolsTab === 'docs' ? 'active' : ''}`}
                  onClick={() => openSpecificTool('protocol')}
                >
                  Документы
                </button>
              </div>

              <div className="tools-tiles-grid-6x2">
                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('whatif')}>
                  <span className="tool-tile-icon">🧪</span>
                  <span className="tool-tile-label">What-if сценарии</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('optimize')}>
                  <span className="tool-tile-icon">📈</span>
                  <span className="tool-tile-label">Оптимизация</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('match')}>
                  <span className="tool-tile-icon">🎯</span>
                  <span className="tool-tile-label">Сверка с замером</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('batch')}>
                  <span className="tool-tile-icon">🥞</span>
                  <span className="tool-tile-label">Пакетный расчёт</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('vision')}>
                  <span className="tool-tile-icon">🖼</span>
                  <span className="tool-tile-label">Распознавание (фото / PDF)</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('report')}>
                  <span className="tool-tile-icon">📥</span>
                  <span className="tool-tile-label">Отчёты и экспорт</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('voice')}>
                  <span className="tool-tile-icon">🎙</span>
                  <span className="tool-tile-label">Аудио и ГС</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('protocol')}>
                  <span className="tool-tile-icon">👥</span>
                  <span className="tool-tile-label">Протокол совещания</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('rag')}>
                  <span className="tool-tile-icon">📦</span>
                  <span className="tool-tile-label">База методик</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('guardrails')}>
                  <span className="tool-tile-icon">🛡</span>
                  <span className="tool-tile-label">Анализ рисков</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('scan')}>
                  <span className="tool-tile-icon">✔</span>
                  <span className="tool-tile-label">Проверка данных</span>
                </button>

                <button type="button" className="tool-tile-btn" onClick={() => openSpecificTool('import')}>
                  <span className="tool-tile-icon">🕒</span>
                  <span className="tool-tile-label">История расчётов</span>
                </button>
              </div>
            </div>
          </section>

          {/* Правая колонка: Результаты расчёта + Встроенный ИИ-ассистент */}
          <section className="dashboard-col col-right-sidebar" aria-label="Результаты расчёта и ИИ-помощник">
            <div className="card-panel-wrapper results-card-wrapper">
              <OperatingPointCards
                result={result}
                loading={loading}
                error={error}
                params={params}
              />
            </div>

            <div className="card-panel-wrapper chat-card-wrapper">
              <AiChatPanel
                params={params}
                onResult={handleResultFromChat}
                onParams={setParams}
              />
            </div>
          </section>
        </main>
      </div>

      {/* Модальное окно для полного функционала выбранного инструмента */}
      {toolsOpen &&
        createPortal(
          <div
            className="tools-full-modal-overlay"
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) setToolsOpen(false)
            }}
          >
            <div className="tools-full-modal-dialog" role="dialog" aria-modal="true">
              <header className="modal-top-bar">
                <div className="modal-title-group">
                  <span className="modal-category-eyebrow">РАСШИРЕННЫЙ ИНЖЕНЕРНЫЙ МОДУЛЬ</span>
                  <h2 className="modal-h2">12 Инженерных возможностей</h2>
                </div>
                <button
                  type="button"
                  className="modal-close-x-btn"
                  onClick={() => setToolsOpen(false)}
                  aria-label="Закрыть окно инструментов"
                >
                  ✕
                </button>
              </header>

              <div className="modal-scrollable-body">
                <EnhancementWorkbench
                  params={params}
                  result={result}
                  onParams={setParams}
                  initialActive={activeTool}
                />
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
