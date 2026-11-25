import type { CalculateResponse, WellParams } from '../types/well'

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
    warnings.push(`Обводнённость WCT = ${wctIpr}% выходит за допустимые пределы 0–100%. Расчёт будет физически неверным.`)
  }
  if (Number.isFinite(wctPvt) && (wctPvt < 0 || wctPvt > 100)) {
    warnings.push(`Обводнённость PVT WCT = ${wctPvt}% выходит за допустимые пределы 0–100%.`)
  }
  if (Number.isFinite(wctIpr) && Number.isFinite(wctPvt) && Math.abs(wctIpr - wctPvt) > 0.01) {
    warnings.push(`Несогласованность обводнённости: IPR WCT (${wctIpr}%) ≠ PVT WCT (${wctPvt}%).`)
  }
  if (Number.isFinite(pRes) && pRes <= 0) {
    warnings.push(`Пластовое давление P_res (${pRes} атм) должно быть строго больше 0.`)
  }
  if (Number.isFinite(pb) && pb < 0) {
    warnings.push(`Давление насыщения P_b (${pb} атм) не может быть отрицательным.`)
  }
  if (Number.isFinite(pi) && pi <= 0) {
    warnings.push(`Коэффициент продуктивности PI (${pi}) должен быть строго больше 0.`)
  }
  if (Number.isFinite(pWh) && pWh < 0) {
    warnings.push(`Устьевое давление P_wh (${pWh} атм) не может быть отрицательным.`)
  }
  if (Number.isFinite(dTubing) && Number.isFinite(dCasing) && dTubing >= dCasing) {
    warnings.push(`Диаметр НКТ (${dTubing} м) должен быть строго меньше диаметра ЭК (${dCasing} м).`)
  }
  if (Number.isFinite(hMes) && Number.isFinite(hRes) && hMes >= hRes) {
    warnings.push(`Глубина спуска НКТ H_mes (${hMes} м) должна быть меньше глубины пласта H_res (${hRes} м).`)
  }
  return warnings
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
        `Получен отрицательный или нулевой дебит жидкости (Q_liq = ${op.q_liq.toFixed(2)} м³/сут). Поля основных KPI и график не заполнены этим результатом.`,
      )
    }
    if (op.p_wf <= 0) {
      warnings.push(
        `Получено неположительное забойное давление (P_wf = ${op.p_wf.toFixed(2)} атм). Проверьте входные параметры.`,
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
