import { useState } from 'react'
import type { PresetItem, WellParams } from '../types/well'

interface WellInputFormProps {
  params: WellParams
  onChange: (params: WellParams) => void
  onCalculate?: () => void
  loading?: boolean
  presets?: PresetItem[]
  onSelectPreset?: (preset: PresetItem) => void
}

type TabType = 'reservoir' | 'completion' | 'pvt' | 'vlp'

export function WellInputForm({
  params,
  onChange,
}: WellInputFormProps) {
  const [activeTab, setActiveTab] = useState<TabType>('reservoir')
  const [extraOpen, setExtraOpen] = useState(false)
  const [activeTooltip, setActiveTooltip] = useState<string | null>(null)

  // Helpers to update params
  const updateIpr = (field: string, value: number) => {
    onChange({
      ...params,
      ipr: {
        ...params.ipr,
        [field]: value,
      },
      vlp: {
        ...params.vlp,
        pvt: {
          ...params.vlp?.pvt,
          ...(field === 'wct' ? { wct: value } : {}),
        },
      },
    })
  }

  const updateVlp = (field: string, value: unknown) => {
    onChange({
      ...params,
      vlp: {
        ...params.vlp,
        [field]: value,
      },
    })
  }

  const updateVlpNested = (parent: 'casing' | 'tubing' | 'pvt', field: string, value: number) => {
    const parentObj = (params.vlp?.[parent] as Record<string, unknown>) || {}
    onChange({
      ...params,
      vlp: {
        ...params.vlp,
        [parent]: {
          ...parentObj,
          [field]: value,
        },
      },
    })
  }

  // Raw values or sensible defaults matching screenshot
  const perm = (params.ipr?.perm as number) ?? 120
  const porosity = (params.ipr?.porosity as number) ?? 0.18
  const pb = params.ipr?.pb ?? 180
  const pRes = params.ipr?.p_res ?? 220
  const pi = params.ipr?.pi ?? 1.25
  const wct = params.ipr?.wct ?? 28

  // Tubing diameter in mm: if d is in meters (0.073), convert to mm (73)
  const tubD = params.vlp?.tubing?.d ? (params.vlp.tubing.d < 1 ? Math.round(params.vlp.tubing.d * 1000) : params.vlp.tubing.d) : 73
  const horizLength = params.vlp?.tubing?.h_mes ?? 800
  const pWh = params.vlp?.p_wh ?? 1.0

  const handleTubDChange = (mm: number) => {
    updateVlpNested('tubing', 'd', mm > 1 ? mm / 1000 : mm)
  }

  const toggleTooltip = (name: string) => {
    setActiveTooltip(activeTooltip === name ? null : name)
  }

  const renderTooltip = (text: string, name: string) => {
    return (
      <span
        className="tooltip-anchor"
        onClick={() => toggleTooltip(name)}
        onMouseEnter={() => setActiveTooltip(name)}
        onMouseLeave={() => setActiveTooltip(null)}
        title={text}
        role="button"
        tabIndex={0}
      >
        ?
        {activeTooltip === name && <span className="tooltip-bubble">{text}</span>}
      </span>
    )
  }

  return (
    <div className="params-panel-card">
      <div className="params-panel-header">
        <div className="params-title-row">
          <svg className="gear-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          <h3>Параметры расчёта</h3>
        </div>
      </div>

      <nav className="params-subtabs-nav" aria-label="Вкладки параметров">
        <button
          type="button"
          className={`params-subtab ${activeTab === 'reservoir' ? 'active' : ''}`}
          onClick={() => setActiveTab('reservoir')}
        >
          Пласт и флюиды
        </button>
        <button
          type="button"
          className={`params-subtab ${activeTab === 'completion' ? 'active' : ''}`}
          onClick={() => setActiveTab('completion')}
        >
          Заканчивание
        </button>
        <button
          type="button"
          className={`params-subtab ${activeTab === 'pvt' ? 'active' : ''}`}
          onClick={() => setActiveTab('pvt')}
        >
          PVT и свойства
        </button>
        <button
          type="button"
          className={`params-subtab ${activeTab === 'vlp' ? 'active' : ''}`}
          onClick={() => setActiveTab('vlp')}
        >
          VLP
        </button>
      </nav>

      <div className="params-form-body">
        {activeTab === 'reservoir' && (
          <div className="form-section-stack">
            <div className="form-group-block">
              <h4 className="group-heading">Параметры пласта</h4>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-perm">
                  <span>Проницаемость, мД</span>
                  {renderTooltip('Абсолютная проницаемость коллектора пористой среды', 'perm')}
                </label>
                <input
                  id="inp-perm"
                  type="number"
                  step="any"
                  className="param-input"
                  value={perm}
                  onChange={(e) => updateIpr('perm', parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-porosity">
                  <span>Пористость, д.е.д.</span>
                  {renderTooltip('Коэффициент открытой пористости продуктивного пласта', 'porosity')}
                </label>
                <input
                  id="inp-porosity"
                  type="number"
                  step="0.01"
                  className="param-input"
                  value={porosity}
                  onChange={(e) => updateIpr('porosity', parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-pb">
                  <span>Давление насыщения, бар</span>
                  {renderTooltip('Давление перехода нефти в двухфазное состояние (разгазирование)', 'pb')}
                </label>
                <input
                  id="inp-pb"
                  type="number"
                  step="any"
                  className="param-input"
                  value={pb}
                  onChange={(e) => updateIpr('pb', parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-pres">
                  <span>Пластовое давление, бар</span>
                  {renderTooltip('Среднее статическое давление в зоне дренирования скважины', 'pres')}
                </label>
                <input
                  id="inp-pres"
                  type="number"
                  step="any"
                  className="param-input"
                  value={pRes}
                  onChange={(e) => updateIpr('p_res', parseFloat(e.target.value) || 0)}
                />
              </div>
            </div>

            <div className="form-group-block">
              <h4 className="group-heading">Параметры скважины</h4>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-tubd">
                  <span>Диаметр НКТ, мм</span>
                  {renderTooltip('Внутренний диаметр насосно-компрессорных труб (НКТ)', 'tubd')}
                </label>
                <input
                  id="inp-tubd"
                  type="number"
                  step="any"
                  className="param-input"
                  value={tubD}
                  onChange={(e) => handleTubDChange(parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-horiz">
                  <span>Длина горизонт. участка, м</span>
                  {renderTooltip('Длина горизонтального ствола или глубина спуска лифта', 'horiz')}
                </label>
                <input
                  id="inp-horiz"
                  type="number"
                  step="any"
                  className="param-input"
                  value={horizLength}
                  onChange={(e) => updateVlpNested('tubing', 'h_mes', parseFloat(e.target.value) || 0)}
                />
              </div>

              <div className="param-field-row">
                <label className="param-label" htmlFor="inp-pwh">
                  <span>Устьевое давление, бар</span>
                  {renderTooltip('Давление на буфере/манифольде устьевой арматуры', 'pwh')}
                </label>
                <input
                  id="inp-pwh"
                  type="number"
                  step="any"
                  className="param-input"
                  value={pWh}
                  onChange={(e) => updateVlp('p_wh', parseFloat(e.target.value) || 0)}
                />
              </div>
            </div>

            <div className="accordion-extra-wrapper">
              <button
                type="button"
                className="accordion-extra-toggle"
                onClick={() => setExtraOpen(!extraOpen)}
              >
                <span>Дополнительные параметры</span>
                <span className={`chevron-icon ${extraOpen ? 'open' : ''}`}>▾</span>
              </button>

              {extraOpen && (
                <div className="accordion-extra-content">
                  <div className="param-field-row">
                    <label className="param-label" htmlFor="inp-pi">
                      <span>Коэффициент продуктивности PI</span>
                    </label>
                    <input
                      id="inp-pi"
                      type="number"
                      step="0.1"
                      className="param-input"
                      value={pi}
                      onChange={(e) => updateIpr('pi', parseFloat(e.target.value) || 0)}
                    />
                  </div>

                  <div className="param-field-row">
                    <label className="param-label" htmlFor="inp-wct">
                      <span>Обводнённость, %</span>
                    </label>
                    <input
                      id="inp-wct"
                      type="number"
                      step="1"
                      min="0"
                      max="100"
                      className="param-input"
                      value={wct}
                      onChange={(e) => updateIpr('wct', parseFloat(e.target.value) || 0)}
                    />
                  </div>

                  <div className="param-field-row">
                    <label className="param-label" htmlFor="inp-tres">
                      <span>Пластовая температура, °C</span>
                    </label>
                    <input
                      id="inp-tres"
                      type="number"
                      step="any"
                      className="param-input"
                      value={params.vlp?.pvt?.t_res ?? 90}
                      onChange={(e) => updateVlpNested('pvt', 't_res', parseFloat(e.target.value) || 0)}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'completion' && (
          <div className="form-section-stack">
            <div className="form-group-block">
              <h4 className="group-heading">Конструкция скважины</h4>
              <div className="param-field-row">
                <label className="param-label">Глубина пласта H_res, м</label>
                <input
                  type="number"
                  className="param-input"
                  value={params.vlp?.h_res ?? 1500}
                  onChange={(e) => updateVlp('h_res', parseFloat(e.target.value) || 0)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Диаметр колонны, мм</label>
                <input
                  type="number"
                  className="param-input"
                  value={((params.vlp?.casing?.d ?? 0.1) * 1000).toFixed(0)}
                  onChange={(e) => updateVlpNested('casing', 'd', (parseFloat(e.target.value) || 100) / 1000)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Шероховатость НКТ ε</label>
                <input
                  type="number"
                  step="0.0001"
                  className="param-input"
                  value={params.vlp?.roughness ?? 0.0001}
                  onChange={(e) => updateVlp('roughness', parseFloat(e.target.value) || 0.0001)}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'pvt' && (
          <div className="form-section-stack">
            <div className="form-group-block">
              <h4 className="group-heading">PVT флюидов</h4>
              <div className="param-field-row">
                <label className="param-label">Газовый фактор Rp, м³/м³</label>
                <input
                  type="number"
                  className="param-input"
                  value={params.vlp?.pvt?.rp ?? 80}
                  onChange={(e) => updateVlpNested('pvt', 'rp', parseFloat(e.target.value) || 0)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Плотность нефти γ_oil</label>
                <input
                  type="number"
                  step="0.01"
                  className="param-input"
                  value={params.vlp?.pvt?.gamma_oil ?? 0.84}
                  onChange={(e) => updateVlpNested('pvt', 'gamma_oil', parseFloat(e.target.value) || 0.8)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Плотность газа γ_gas</label>
                <input
                  type="number"
                  step="0.01"
                  className="param-input"
                  value={params.vlp?.pvt?.gamma_gas ?? 0.7}
                  onChange={(e) => updateVlpNested('pvt', 'gamma_gas', parseFloat(e.target.value) || 0.7)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Плотность воды γ_wat</label>
                <input
                  type="number"
                  step="0.01"
                  className="param-input"
                  value={params.vlp?.pvt?.gamma_wat ?? 1.0}
                  onChange={(e) => updateVlpNested('pvt', 'gamma_wat', parseFloat(e.target.value) || 1.0)}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'vlp' && (
          <div className="form-section-stack">
            <div className="form-group-block">
              <h4 className="group-heading">Гидравлический расчёт (VLP)</h4>
              <div className="param-field-row">
                <label className="param-label">Геотерм. градиент, °C/100м</label>
                <input
                  type="number"
                  step="0.1"
                  className="param-input"
                  value={params.vlp?.geo_grad ?? 3.0}
                  onChange={(e) => updateVlp('geo_grad', parseFloat(e.target.value) || 3.0)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Предел дебита Q_max</label>
                <input
                  type="number"
                  className="param-input"
                  value={params.vlp?.q_max ?? 300}
                  onChange={(e) => updateVlp('q_max', parseFloat(e.target.value) || 300)}
                />
              </div>
              <div className="param-field-row">
                <label className="param-label">Число точек расчёта</label>
                <input
                  type="number"
                  className="param-input"
                  value={params.vlp?.points ?? 21}
                  onChange={(e) => updateVlp('points', parseInt(e.target.value) || 21)}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
