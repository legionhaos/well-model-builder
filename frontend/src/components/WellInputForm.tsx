import { useState, useEffect } from 'react'
import type { PresetItem, WellParams } from '../types/well'
import { getWellFieldErrors, validateWellPhysics } from '../utils/physics'

interface WellInputFormProps {
  params: WellParams
  onChange: (params: WellParams) => void
  onCalculate: () => void
  loading: boolean
  presets: PresetItem[]
  onSelectPreset: (preset: PresetItem) => void
}

export function WellInputForm({
  params,
  onChange,
  onCalculate,
  loading,
  presets,
  onSelectPreset,
}: WellInputFormProps) {
  const [activeTab, setActiveTab] = useState<'form' | 'json'>('form')
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const physicalWarnings = validateWellPhysics(params)
  const fieldErrors = getWellFieldErrors(params)

  // Синхронизация JSON текста при изменении params извне
  useEffect(() => {
    setJsonText(JSON.stringify(params, null, 2))
    setJsonError(null)
  }, [params])

  const handleJsonChange = (text: string) => {
    setJsonText(text)
    try {
      const parsed = JSON.parse(text)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        setJsonError('Ожидается JSON-объект со структурой { "ipr": {...}, "vlp": {...} }')
        return
      }
      const missing: string[] = []
      const iprObj = parsed.ipr as Record<string, unknown> | undefined
      const vlpObj = parsed.vlp as Record<string, unknown> | undefined
      if (!iprObj || typeof iprObj !== 'object') {
        missing.push('ipr')
      } else {
        for (const key of ['p_res', 'wct', 'pi', 'pb']) {
          if (typeof iprObj[key] !== 'number' || !Number.isFinite(iprObj[key] as number)) missing.push(`ipr.${key}`)
        }
      }
      if (!vlpObj || typeof vlpObj !== 'object') {
        missing.push('vlp')
      } else {
        for (const sub of ['inclinometry', 'casing', 'tubing', 'pvt']) {
          if (!vlpObj[sub] || typeof vlpObj[sub] !== 'object') missing.push(`vlp.${sub}`)
        }
        for (const key of ['p_wh', 'geo_grad', 'h_res']) {
          if (typeof vlpObj[key] !== 'number' || !Number.isFinite(vlpObj[key] as number)) missing.push(`vlp.${key}`)
        }
      }
      if (missing.length > 0) {
        setJsonError(`Неполный JSON — отсутствуют поля: ${missing.join(', ')}. Без согласия значения не подставляются.`)
        return
      }
      onChange(parsed as WellParams)
      setJsonError(null)
    } catch {
      setJsonError('Некорректный JSON синтаксис')
    }
  }

  // Обновление полей IPR
  const updateIpr = (field: string, value: number) => {
    onChange({
      ...params,
      ipr: {
        ...params.ipr,
        [field]: value,
      },
      // Синхронизируем wct в PVT, если меняется в IPR
      vlp: {
        ...params.vlp,
        pvt: {
          ...params.vlp?.pvt,
          ...(field === 'wct' ? { wct: value } : {}),
        },
      },
    })
  }

  // Обновление полей VLP
  const updateVlp = (field: string, value: unknown) => {
    onChange({
      ...params,
      vlp: {
        ...params.vlp,
        [field]: value,
      },
    })
  }

  // Обновление вложенных полей VLP
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

  return (
    <div className="well-input-card">
      <div className="card-header">
        <div className="title-row">
          <span className="eyebrow">ПАРАМЕТРЫ СКВАЖИНЫ</span>
          <h3>Модель притока и лифта</h3>
        </div>

        <div className="tab-buttons">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'form' ? 'active' : ''}`}
            onClick={() => setActiveTab('form')}
          >
            Форма
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'json' ? 'active' : ''}`}
            onClick={() => setActiveTab('json')}
          >
            JSON
          </button>
        </div>
      </div>

      {/* Быстрые пресеты */}
      <div className="preset-bar">
        <span className="preset-label">Пресеты:</span>
        <div className="preset-chips">
          {presets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="preset-chip"
              onClick={() => onSelectPreset(preset)}
              title={preset.description}
            >
              {preset.name.split('(')[0].trim()}
            </button>
          ))}
        </div>
      </div>

      <div className="form-content">
        {physicalWarnings.length > 0 && (
          <div className="form-physics-warnings" role="alert">
            <strong>Внимание: физическая ошибка во входных данных</strong>
            <ul>
              {physicalWarnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        {activeTab === 'form' ? (
          <div className="sections-accordion">
            {/* Секция 1: Пласт и приток (IPR) */}
            <div className="input-group-section">
              <div className="section-title">
                <span className="section-dot" /> 1. Пласт и приток (IPR)
              </div>
              <div className="fields-grid">
                <div className={`field ${fieldErrors.p_res ? 'field-has-warning' : ''}`}>
                  <label htmlFor="p_res">P_res (пластовое), атм</label>
                  <input
                    id="p_res"
                    type="number"
                    step="any"
                    value={params.ipr?.p_res ?? 200}
                    onChange={(e) => updateIpr('p_res', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.p_res && <span className="field-warn-hint">{fieldErrors.p_res}</span>}
                </div>
                <div className={`field ${fieldErrors.pb ? 'field-has-warning' : ''}`}>
                  <label htmlFor="pb">P_b (насыщения), атм</label>
                  <input
                    id="pb"
                    type="number"
                    step="any"
                    value={params.ipr?.pb ?? 150}
                    onChange={(e) => updateIpr('pb', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.pb && <span className="field-warn-hint">{fieldErrors.pb}</span>}
                </div>
                <div className={`field ${fieldErrors.pi ? 'field-has-warning' : ''}`}>
                  <label htmlFor="pi">PI (продуктивность), м³/(сут·атм)</label>
                  <input
                    id="pi"
                    type="number"
                    step="any"
                    value={params.ipr?.pi ?? 1}
                    onChange={(e) => updateIpr('pi', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.pi && <span className="field-warn-hint">{fieldErrors.pi}</span>}
                </div>
                <div className={`field ${fieldErrors.wct ? 'field-has-warning' : ''}`}>
                  <label htmlFor="wct">WCT (обводненность), %</label>
                  <input
                    id="wct"
                    type="number"
                    step="any"
                    min="0"
                    max="100"
                    value={params.ipr?.wct ?? 50}
                    onChange={(e) => updateIpr('wct', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.wct && <span className="field-warn-hint">{fieldErrors.wct}</span>}
                </div>
              </div>
            </div>

            {/* Секция 2: Конструкция ствола (VLP) */}
            <div className="input-group-section">
              <div className="section-title">
                <span className="section-dot" /> 2. Конструкция ствола (VLP)
              </div>
              <div className="fields-grid">
                <div className="field">
                  <label htmlFor="h_res">Глубина пласта H_res, м</label>
                  <input
                    id="h_res"
                    type="number"
                    step="any"
                    value={params.vlp?.h_res ?? 1500}
                    onChange={(e) => updateVlp('h_res', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className={`field ${fieldErrors.h_mes ? 'field-has-warning' : ''}`}>
                  <label htmlFor="h_mes">Спуск НКТ H_mes, м</label>
                  <input
                    id="h_mes"
                    type="number"
                    step="any"
                    value={params.vlp?.tubing?.h_mes ?? 1000}
                    onChange={(e) => updateVlpNested('tubing', 'h_mes', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.h_mes && <span className="field-warn-hint">{fieldErrors.h_mes}</span>}
                </div>
                <div className={`field ${fieldErrors.tub_d ? 'field-has-warning' : ''}`}>
                  <label htmlFor="tub_d">Диаметр НКТ d, м</label>
                  <input
                    id="tub_d"
                    type="number"
                    step="any"
                    value={params.vlp?.tubing?.d ?? 0.062}
                    onChange={(e) => updateVlpNested('tubing', 'd', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.tub_d && <span className="field-warn-hint">{fieldErrors.tub_d}</span>}
                </div>
                <div className="field">
                  <label htmlFor="cas_d">Диаметр колонны d, м</label>
                  <input
                    id="cas_d"
                    type="number"
                    step="any"
                    value={params.vlp?.casing?.d ?? 0.1}
                    onChange={(e) => updateVlpNested('casing', 'd', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="roughness">Шероховатость ε (отн.)</label>
                  <input
                    id="roughness"
                    type="number"
                    step="any"
                    value={params.vlp?.roughness ?? 0.0001}
                    onChange={(e) => updateVlp('roughness', parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>
            </div>

            {/* Секция 3: Термодинамика и PVT */}
            <div className="input-group-section">
              <div className="section-title">
                <span className="section-dot" /> 3. Термодинамика и PVT
              </div>
              <div className="fields-grid">
                <div className={`field ${fieldErrors.p_wh ? 'field-has-warning' : ''}`}>
                  <label htmlFor="p_wh">Устьевое давление P_wh, атм</label>
                  <input
                    id="p_wh"
                    type="number"
                    step="any"
                    value={params.vlp?.p_wh ?? 10}
                    onChange={(e) => updateVlp('p_wh', parseFloat(e.target.value) || 0)}
                  />
                  {fieldErrors.p_wh && <span className="field-warn-hint">{fieldErrors.p_wh}</span>}
                </div>
                <div className="field">
                  <label htmlFor="t_res">Температура пласта T_res, °C</label>
                  <input
                    id="t_res"
                    type="number"
                    step="any"
                    value={params.vlp?.t_res ?? params.vlp?.pvt?.t_res ?? 90}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value) || 0
                      onChange({
                        ...params,
                        vlp: {
                          ...params.vlp,
                          t_res: v,
                          pvt: {
                            ...params.vlp?.pvt,
                            t_res: v,
                          },
                        },
                      })
                    }}
                  />
                </div>
                <div className="field">
                  <label htmlFor="geo_grad">Геотерм. градиент, °C/100м</label>
                  <input
                    id="geo_grad"
                    type="number"
                    step="any"
                    value={params.vlp?.geo_grad ?? 3}
                    onChange={(e) => updateVlp('geo_grad', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="rp">Газовый фактор Rp, м³/т</label>
                  <input
                    id="rp"
                    type="number"
                    step="any"
                    value={params.vlp?.pvt?.rp ?? 100}
                    onChange={(e) => updateVlpNested('pvt', 'rp', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="gamma_oil">Плотность нефти γ_oil</label>
                  <input
                    id="gamma_oil"
                    type="number"
                    step="any"
                    value={params.vlp?.pvt?.gamma_oil ?? 0.8}
                    onChange={(e) => updateVlpNested('pvt', 'gamma_oil', parseFloat(e.target.value) || 0)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="gamma_gas">Плотность газа γ_gas</label>
                  <input
                    id="gamma_gas"
                    type="number"
                    step="any"
                    value={params.vlp?.pvt?.gamma_gas ?? 0.7}
                    onChange={(e) => updateVlpNested('pvt', 'gamma_gas', parseFloat(e.target.value) || 0)}
                  />
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="json-editor-wrap">
            <textarea
              className="json-textarea"
              value={jsonText}
              onChange={(e) => handleJsonChange(e.target.value)}
              placeholder="Вставьте JSON параметры скважины..."
              rows={16}
              spellCheck={false}
            />
            {jsonError && <div className="json-error">{jsonError}</div>}
          </div>
        )}
      </div>

      <div className="card-footer">
        <button
          type="button"
          className="btn-calculate"
          disabled={loading || Boolean(jsonError)}
          onClick={onCalculate}
        >
          {loading ? (
            <>
              <span className="spinner" /> Выполняется расчет...
            </>
          ) : (
            'Рассчитать модель скважины'
          )}
        </button>
      </div>
    </div>
  )
}
