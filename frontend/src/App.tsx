import { useState, useEffect, useCallback } from 'react'
import { api } from './api/client'
import type { CalculateResponse, PresetItem, WellParams } from './types/well'
import { WellInputForm } from './components/WellInputForm'
import { OperatingPointCards } from './components/OperatingPointCards'
import { NodalChart } from './components/NodalChart'
import { AiChatPanel } from './components/AiChatPanel'
import { EnhancementWorkbench } from './components/EnhancementWorkbench'

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
  const [params, setParams] = useState<WellParams>(FALLBACK_PRESETS[0].data)
  const [result, setResult] = useState<CalculateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <div className="app-shell">
      {/* Верхняя навигационная панель */}
      <header className="app-header">
        <div className="brand-group">
          <div className="brand-logo" aria-hidden="true">W</div>
          <div>
            <h1 className="brand-title">Well Model Builder <span className="version-tag">v3.1</span></h1>
            <p className="brand-subtitle">Система узлового анализа «пласт — скважина» · Роль 4</p>
          </div>
        </div>

        <div className="header-actions">
          <div className="service-badges">
            <span className="badge-svc" title="IPR сервис Brown (1984)">IPR :8003</span>
            <span className="badge-svc" title="VLP + Black-Oil PVT">VLP :8002</span>
            <span className="badge-svc" title="Nodal пересечение">NODAL :8004</span>
            <span className="badge-svc" title="Backend оркестратор">API :8080</span>
          </div>
          <button
            type="button"
            className="btn-quick-calc"
            onClick={handleCalculate}
            disabled={loading}
          >
            {loading ? 'Расчет...' : 'Пересчитать'}
          </button>
        </div>
      </header>

      {/* Рабочая область: параметры, результат и инженерный помощник */}
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

        {/* Колонка 2: KPI карточки и Nodal график */}
        <section className="layout-col col-results">
          <OperatingPointCards
            result={result}
            loading={loading}
            error={error}
          />

          <div className="chart-panel-card">
            <div className="chart-header">
              <div>
                <span className="eyebrow">УЗЛОВОЙ АНАЛИЗ</span>
                <h3>Совмещенный график IPR и VLP</h3>
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
              <span>● IPR: Composite Brown (1984)</span>
              <span>● VLP: Colebrook-White + Black-Oil PVT (RK45)</span>
              <span>● Nodal: Точное геометрическое пересечение</span>
            </div>
          </div>
          <EnhancementWorkbench params={params} result={result} onParams={setParams} />
        </section>

        {/* Колонка 3: Чат ИИ-ассистента */}
        <section className="layout-col col-chat">
          <AiChatPanel
            params={params}
            onResult={handleResultFromChat}
          />
        </section>
      </main>
    </div>
  )
}
