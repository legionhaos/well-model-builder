import type { CalculateResponse, WellParams } from '../types/well'

export interface PhysicsValidation {
  warnings: string[]
  fieldErrors: Record<string, string>
}

export function validateWellPhysics(
  params: WellParams,
  result?: CalculateResponse | null,
): PhysicsValidation {
  const warnings: string[] = []
  const fieldErrors: Record<string, string> = {}

  const pRes = Number(params.ipr?.p_res)
  const pb = Number(params.ipr?.pb)
  const pi = Number(params.ipr?.pi)
  const wct = Number(params.ipr?.wct)
  const pvtWct = Number(params.vlp?.pvt?.wct)
  const pWh = Number(params.vlp?.p_wh)
  const hRes = Number(params.vlp?.h_res)
  const hMes = Number(params.vlp?.tubing?.h_mes)
  const tubD = Number(params.vlp?.tubing?.d)
  const casD = Number(params.vlp?.casing?.d)

  if (!Number.isFinite(wct) || wct < 0 || wct > 100) {
    const msg = `Некорректная обводнённость WCT = ${Number.isFinite(wct) ? wct : '—'}% (допустимо 0–100%).`
    warnings.push(msg)
    fieldErrors.wct = 'Должно быть от 0 до 100%'
  } else if (wct >= 98) {
    warnings.push(`Критически высокая обводнённость WCT = ${wct}%: добыча чистой нефти близка к нулю.`)
  }

  if (Number.isFinite(wct) && Number.isFinite(pvtWct) && Math.abs(wct - pvtWct) > 0.5) {
    warnings.push(`Обводнённость в IPR (${wct}%) и PVT (${pvtWct}%) различается.`)
  }

  if (!Number.isFinite(pRes) || pRes <= 0) {
    warnings.push(`Пластовое давление P_res должно быть > 0 (сейчас ${Number.isFinite(pRes) ? pRes : '—'} атм).`)
    fieldErrors.p_res = 'Должно быть > 0'
  }

  if (!Number.isFinite(pi) || pi <= 0) {
    warnings.push(`Коэффициент продуктивности PI = ${Number.isFinite(pi) ? pi : '—'} (при PI <= 0 приток невозможен).`)
    fieldErrors.pi = 'Должен быть > 0'
  }

  if (Number.isFinite(pWh) && pWh < 0) {
    warnings.push(`Устьевое давление P_wh = ${pWh} атм не может быть отрицательным.`)
    fieldErrors.p_wh = 'Должно быть >= 0'
  }

  if (Number.isFinite(pWh) && Number.isFinite(pRes) && pRes > 0 && pWh >= pRes) {
    warnings.push(`Устьевое давление P_wh (${pWh} атм) >= пластового P_res (${pRes} атм): приток невозможен (дебит <= 0).`)
    fieldErrors.p_wh = 'Выше или равно P_res'
  }

  if (Number.isFinite(pb) && Number.isFinite(pRes) && pRes > 0 && pb > pRes) {
    warnings.push(`Давление насыщения P_b (${pb} атм) выше пластового P_res (${pRes} атм).`)
    fieldErrors.pb = 'Выше P_res'
  }

  if (Number.isFinite(tubD) && Number.isFinite(casD) && tubD >= casD) {
    warnings.push(`Диаметр НКТ (${tubD} м) больше или равен диаметру колонны (${casD} м).`)
    fieldErrors.tub_d = 'Больше диаметра ЭК'
  }

  if (Number.isFinite(hMes) && Number.isFinite(hRes) && hMes > hRes) {
    warnings.push(`Спуск НКТ (${hMes} м) превышает глубину пласта (${hRes} м).`)
    fieldErrors.h_mes = 'Глубже H_res'
  }

  if (result) {
    const op = result.operating_point
    if (op && op.q_liq <= 0) {
      warnings.push(`Отрицательный или нулевой расчётный дебит q_liq = ${op.q_liq.toFixed(2)} м³/сут.`)
    }
    if (op && Number.isFinite(pRes) && op.p_wf > pRes) {
      warnings.push(`Забойное давление p_wf (${op.p_wf.toFixed(2)} атм) выше пластового P_res (${pRes} атм).`)
    }
    if (result.ipr?.q_liq?.some((q) => q < 0)) {
      warnings.push('Кривая IPR содержит отрицательные значения дебита.')
    }
    for (const backendWarn of result.warnings ?? []) {
      if (backendWarn && !warnings.includes(backendWarn)) {
        warnings.push(backendWarn)
      }
    }
  }

  return { warnings, fieldErrors }
}
