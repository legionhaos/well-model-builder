"""Improvement 10: Сравнение с фактическим замером (History Matching, диагностика невязок и адаптация)."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional


async def compare_with_field_measurement(
    base_params: Dict[str, Any],
    measured_q_liq: float,
    measured_p_wf: Optional[float],
    calculate: Callable[[Dict[str, Any]], Any]
) -> Dict[str, Any]:
    """
    Сравнение смоделированной рабочей точки с фактическими замерами гидродинамических исследований (ГДИ)
    или замерной установки (АГЗУ).
    """
    model_res = await calculate(base_params)
    model_op = model_res.get("operating_point")

    if not model_op:
        return {
            "status": "error",
            "message": "Модель скважины не находит рабочую точку при текущих параметрах.",
            "measured": {"q_liq": measured_q_liq, "p_wf": measured_p_wf},
            "model": None
        }

    q_mod = float(model_op["q_liq"])
    p_mod = float(model_op["p_wf"])

    delta_q = round(measured_q_liq - q_mod, 2)
    delta_q_pct = round((delta_q / q_mod) * 100.0, 2) if q_mod > 0 else 0.0

    delta_p = round((measured_p_wf - p_mod), 2) if measured_p_wf is not None else None
    delta_p_pct = round((delta_p / p_mod) * 100.0, 2) if (delta_p is not None and p_mod > 0) else None

    # Экспертная диагностика причин расхождения
    diagnosis = []
    recommendations = []

    p_res = float(base_params.get("ipr", {}).get("p_res", 200.0))
    current_pi = float(base_params.get("ipr", {}).get("pi", 1.0))

    # 1. Анализ по дебиту
    if abs(delta_q_pct) <= 5.0:
        diagnosis.append("Высокая сходимость модели и факта (погрешность по дебиту менее 5%). Модель верифицирована.")
    elif delta_q < 0:
        # Факт меньше модели
        drop_pct = abs(delta_q_pct)
        diagnosis.append(
            f"Фактический дебит ниже расчетного на {abs(delta_q)} м³/сут ({drop_pct}%). "
            f"Возможные причины: кольматация призабойной зоны (положительный скин-фактор S > 0), "
            f"снижение пластового давления относительно проектного либо парафиногидратные отложения в стволе НКТ."
        )
        recommendations.append("Рекомендуется запланировать гидродинамические исследования (КВД) для определения скин-фактора и очистку НКТ от АСПО.")
    else:
        # Факт больше модели
        diagnosis.append(
            f"Фактический дебит выше расчетного на {delta_q} м³/сут (+{delta_q_pct}%). "
            f"Возможные причины: трещиноватость пласта, супер-проницаемые пропластки или занижение проектного коэффициента продуктивности."
        )
        recommendations.append("Рекомендуется пересчитать продуктивность пласта по новым замерам дебита.")

    # 2. Анализ по забойному давлению
    if measured_p_wf is not None:
        if delta_p and delta_p > 5.0:
            diagnosis.append(
                f"Фактическое забойное давление выше расчетного на {delta_p} атм. "
                f"Это указывает на повышенные потери давления в стволе (высокое гидравлическое сопротивление, стесненное сечение НКТ)."
            )
            recommendations.append("Проверить проходимость скребка по стволу НКТ и фактическую температуру на устье.")
        elif delta_p and delta_p < -5.0:
            diagnosis.append(
                f"Фактическое забойное давление ниже расчетного на {abs(delta_p)} атм. "
                f"Энергия пласта срабатывается интенсивнее прогноза."
            )

    # 3. Адаптация модели (калибровка продуктивности)
    calibrated_pi = None
    if measured_p_wf and (p_res - measured_p_wf) > 0:
        calibrated_pi = round(measured_q_liq / (p_res - measured_p_wf), 3)

    return {
        "status": "success",
        "comparison": {
            "measured": {"q_liq": measured_q_liq, "p_wf": measured_p_wf},
            "model": {"q_liq": q_mod, "p_wf": p_mod},
            "deltas": {
                "delta_q_liq_m3_day": delta_q,
                "delta_q_liq_percent": delta_q_pct,
                "delta_p_wf_atm": delta_p,
                "delta_p_wf_percent": delta_p_pct
            }
        },
        "diagnosis": diagnosis,
        "recommendations": recommendations,
        "calibrated_parameters": {
            "base_pi": current_pi,
            "recommended_pi": calibrated_pi,
            "formula": "J_calibrated = q_meas / (p_res - p_wf_meas)" if calibrated_pi else None
        }
    }
