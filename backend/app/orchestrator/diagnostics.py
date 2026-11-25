"""Physical sanity diagnostics without blocking calculation."""

from __future__ import annotations

from typing import Any, Dict, List


def collect_physics_warnings(
    ipr_payload: Dict[str, Any] | None,
    vlp_payload: Dict[str, Any] | None,
    calc_result: Dict[str, Any] | None = None,
) -> List[str]:
    """Collect explicit non-blocking warnings for negative flow, invalid WCT, or anomalous inputs."""
    warnings: List[str] = []
    ipr = ipr_payload or {}
    vlp = vlp_payload or {}
    pvt = vlp.get("pvt") or {}
    tubing = vlp.get("tubing") or {}
    casing = vlp.get("casing") or {}
    res = calc_result or {}

    def _num(val: Any) -> float | None:
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    p_res = _num(ipr.get("p_res"))
    pb = _num(ipr.get("pb"))
    pi = _num(ipr.get("pi"))
    wct = _num(ipr.get("wct"))
    pvt_wct = _num(pvt.get("wct"))
    p_wh = _num(vlp.get("p_wh"))
    h_res = _num(vlp.get("h_res"))
    h_mes = _num(tubing.get("h_mes"))
    tub_d = _num(tubing.get("d"))
    cas_d = _num(casing.get("d"))

    if wct is not None and (wct < 0 or wct > 100):
        warnings.append(f"Некорректная обводнённость WCT = {wct}% (физически допустимо от 0% до 100%).")
    elif wct is not None and wct >= 98:
        warnings.append(f"Критически высокая обводнённость WCT = {wct}%: доля нефти близка к нулю.")

    if wct is not None and pvt_wct is not None and abs(wct - pvt_wct) > 0.5:
        warnings.append(f"Обводнённость в IPR ({wct}%) и PVT ({pvt_wct}%) не совпадает.")

    if p_res is not None and p_res <= 0:
        warnings.append(f"Некорректное пластовое давление P_res = {p_res} атм (должно быть > 0).")

    if pi is not None and pi <= 0:
        warnings.append(f"Нулевой или отрицательный коэффициент продуктивности PI = {pi}.")

    if p_wh is not None and p_res is not None and p_wh >= p_res:
        warnings.append(f"Устьевое давление P_wh ({p_wh} атм) >= пластового P_res ({p_res} атм): приток на поверхность невозможен.")

    if pb is not None and p_res is not None and pb > p_res:
        warnings.append(f"Давление насыщения P_b ({pb} атм) превышает пластовое P_res ({p_res} атм).")

    if tub_d is not None and cas_d is not None and tub_d >= cas_d:
        warnings.append(f"Диаметр НКТ ({tub_d} м) больше или равен диаметру колонны ({cas_d} м).")

    if h_mes is not None and h_res is not None and h_mes > h_res:
        warnings.append(f"Глубина спуска НКТ ({h_mes} м) превышает глубину пласта ({h_res} м).")

    op = res.get("operating_point")
    if isinstance(op, dict):
        q_liq = _num(op.get("q_liq"))
        p_wf = _num(op.get("p_wf"))
        if q_liq is not None and q_liq <= 0:
            warnings.append(f"Отрицательный или нулевой расчётный дебит q_liq = {q_liq:.2f} м³/сут (рабочий приток отсутствует).")
        if p_wf is not None and p_res is not None and p_wf > p_res:
            warnings.append(f"Забойное давление p_wf ({p_wf:.2f} атм) превышает пластовое P_res ({p_res} атм) — обратный ток в пласт.")

    ipr_q = (res.get("ipr") or {}).get("q_liq") or []
    if any((_num(q) is not None and _num(q) < 0) for q in ipr_q):
        warnings.append("Кривая IPR содержит отрицательные значения дебита.")

    return warnings
