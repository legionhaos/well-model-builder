import type { CalculateResponse, WellParams } from '../types/well'

function fmtNum(val: number): string {
  return Number(val.toPrecision(6)).toString()
}

export function validateWellPhysics(params: WellParams | null | undefined): string[] {
  if (!params) return []
  const warnings: string[] = []
  const wctIpr = Number(params.ipr?.wct)
  const wctPvt = Number(params.vlp?.pvt?.wct)
  const pRes = Number(params.ipr?.p_res)
  const pi = Number(params.ipr?.pi)
  const pb = Number(params.ipr?.pb)
  const pWh = Number(params.vlp?.p_wh)
  const hRes = Number(params.vlp?.h_res)
  const hMes = Number(params.vlp?.tubing?.h_mes)
  const dTubing = Number(params.vlp?.tubing?.d)
  const dCasing = Number(params.vlp?.casing?.d)

  if (Number.isFinite(wctIpr) && (wctIpr < 0 || wctIpr > 100)) {
    warnings.push(`Обводнённость WCT = ${fmtNum(wctIpr)}% указана некорректно (допустимо 0–100%). Расчёт нефизичен.`)
  } else if (Number.isFinite(wctIpr) && wctIpr >= 98) {
    warnings.push(`Критически высокая обводнённость WCT = ${fmtNum(wctIpr)}%: доля нефти близка к нулю.`)
  }
  if (Number.isFinite(wctPvt) && (wctPvt < 0 || wctPvt > 100)) {
    warnings.push(`Обводнённость PVT = ${fmtNum(wctPvt)}% выходит за пределы 0–100%.`)
  }
  if (Number.isFinite(wctIpr) && Number.isFinite(wctPvt) && Math.abs(wctIpr - wctPvt) > 0.1) {
    warnings.push(`Рассогласование обводнённости: IPR (${fmtNum(wctIpr)}%) != PVT (${fmtNum(wctPvt)}%).`)
  }
  if (Number.isFinite(pRes) && pRes <= 0) {
    warnings.push(`Пластовое давление P_res = ${fmtNum(pRes)} атм <= 0 — приток невозможен.`)
  }
  if (Number.isFinite(pb) && pb < 0) {
    warnings.push(`Давление насыщения P_b (${fmtNum(pb)} атм) не может быть отрицательным.`)
  } else if (Number.isFinite(pb) && Number.isFinite(pRes) && pRes > 0 && pb > pRes) {
    warnings.push(`Давление насыщения P_b (${fmtNum(pb)} атм) превышает пластовое P_res (${fmtNum(pRes)} атм).`)
  }
  if (Number.isFinite(pi) && pi <= 0) {
    warnings.push(`Продуктивность PI = ${fmtNum(pi)} <= 0 — приток отсутствует.`)
  }
  if (Number.isFinite(pWh) && pWh < 0) {
    warnings.push(`Устьевое давление P_wh = ${fmtNum(pWh)} атм < 0 — нефизичное значение.`)
  } else if (Number.isFinite(pWh) && Number.isFinite(pRes) && pRes > 0 && pWh >= pRes) {
    warnings.push(`Устьевое давление P_wh (${fmtNum(pWh)} атм) >= пластового P_res (${fmtNum(pRes)} атм) — фонтанирование невозможно.`)
  }
  if (Number.isFinite(dTubing) && Number.isFinite(dCasing) && dTubing >= dCasing) {
    warnings.push(`Нарушена геометрия ствола: диаметр НКТ (${fmtNum(dTubing)} м) >= ЭК (${fmtNum(dCasing)} м).`)
  }
  if (Number.isFinite(hMes) && Number.isFinite(hRes) && hMes > hRes) {
    warnings.push(`Спуск НКТ (${fmtNum(hMes)} м) больше глубины пласта (${fmtNum(hRes)} м).`)
  }
  return warnings
}

export type WellFieldErrorMap = Partial<Record<'p_res' | 'pb' | 'pi' | 'wct' | 'h_mes' | 'tub_d' | 'p_wh', string>>

export function getWellFieldErrors(params: WellParams | null | undefined): WellFieldErrorMap {
  if (!params) return {}
  const errs: WellFieldErrorMap = {}
  const pRes = Number(params.ipr?.p_res)
  const pb = Number(params.ipr?.pb)
  const pi = Number(params.ipr?.pi)
  const wct = Number(params.ipr?.wct)
  const pWh = Number(params.vlp?.p_wh)
  const hRes = Number(params.vlp?.h_res)
  const hMes = Number(params.vlp?.tubing?.h_mes)
  const dTubing = Number(params.vlp?.tubing?.d)
  const dCasing = Number(params.vlp?.casing?.d)

  if (Number.isFinite(pRes) && pRes <= 0) errs.p_res = 'P_res должно быть > 0 атм'
  if (Number.isFinite(pb) && pb < 0) errs.pb = 'P_b не может быть < 0'
  else if (Number.isFinite(pb) && Number.isFinite(pRes) && pRes > 0 && pb > pRes) errs.pb = 'P_b > P_res'
  if (Number.isFinite(pi) && pi <= 0) errs.pi = 'PI должен быть > 0'
  if (Number.isFinite(wct) && (wct < 0 || wct > 100)) errs.wct = 'Допустимо строго 0–100%'
  if (Number.isFinite(pWh) && pWh < 0) errs.p_wh = 'P_wh не может быть < 0'
  else if (Number.isFinite(pWh) && Number.isFinite(pRes) && pRes > 0 && pWh >= pRes) errs.p_wh = 'P_wh ≥ P_res (нет притока)'
  if (Number.isFinite(dTubing) && Number.isFinite(dCasing) && dTubing >= dCasing) errs.tub_d = 'd_НКТ должен быть < d_ЭК'
  if (Number.isFinite(hMes) && Number.isFinite(hRes) && hMes >= hRes) errs.h_mes = 'H_mes должно быть < H_res'
  return errs
}

export function inspectCalculationPhysics(
  calc: CalculateResponse | null | undefined,
  params?: WellParams | null,
): { isPhysical: boolean; warnings: string[] } {
  const warnings: string[] = []
  if (params) {
    for (const w of validateWellPhysics(params)) {
      if (!warnings.includes(w)) warnings.push(w)
    }
  }
  if (!calc) {
    return { isPhysical: warnings.length === 0, warnings }
  }
  if (Array.isArray(calc.meta?.warnings)) {
    for (const w of calc.meta.warnings) {
      const txt = String(w).trim()
      if (txt && !warnings.includes(txt)) warnings.push(txt)
    }
  }
  const op = calc.operating_point
  if (op) {
    if (op.q_liq <= 0) {
      warnings.push(
        `Отрицательный или нулевой расчётный дебит жидкости (q_liq = ${op.q_liq.toFixed(2)} м³/сут) — рабочий приток отсутствует.`,
      )
    }
    if (op.p_wf <= 0) {
      warnings.push(
        `Получено неположительное забойное давление (p_wf = ${op.p_wf.toFixed(2)} атм). Проверьте входные параметры.`,
      )
    }
  }
  const hasNegativeCurve =
    (calc.ipr?.q_liq?.some((q) => q < 0) ?? false) || (calc.vlp?.q_liq?.some((q) => q < 0) ?? false)
  if (hasNegativeCurve) {
    warnings.push('Кривая IPR/VLP содержит отрицательные значения дебита (< 0 м³/сут).')
  }
  const isPhysical = calc.meta?.is_physical !== false && warnings.length === 0
  return { isPhysical, warnings }
}
