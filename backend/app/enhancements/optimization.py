"""Improvement 09: Подбор параметров режима (Оптимизация НКТ, p_wh и критической обводненности)."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

# Стандартный сортамент НКТ по ГОСТ 633-80 (внутренние диаметры в метрах)
STANDARD_TUBING_DIAMETERS = [
    {"name": "НКТ 48 мм", "d": 0.0403},
    {"name": "НКТ 60 мм", "d": 0.0503},
    {"name": "НКТ 73 мм (базовый)", "d": 0.0620},
    {"name": "НКТ 89 мм", "d": 0.0759},
    {"name": "НКТ 102 мм", "d": 0.0880},
    {"name": "НКТ 114 мм", "d": 0.1000},
]


async def optimize_tubing_diameter(
    base_params: Dict[str, Any],
    calculate: Callable[[Dict[str, Any]], Any],
    custom_diameters: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Подбор оптимального диаметра НКТ для максимизации дебита жидкости при соблюдении
    геометрических ограничений (d_tubing < d_casing).
    """
    casing_d = base_params.get("vlp", {}).get("casing", {}).get("d", 0.12)
    diameters = custom_diameters or STANDARD_TUBING_DIAMETERS

    results = []
    best_opt = None
    best_d = None
    best_name = None

    async def _eval_diameter(item: Dict[str, Any]) -> Dict[str, Any]:
        d_val = float(item["d"])
        name = item["name"]

        if d_val >= casing_d:
            return {
                "tubing_name": name,
                "d_m": d_val,
                "status": "incompatible",
                "reason": f"Диаметр НКТ ({d_val} м) больше или равен ЭК ({casing_d} м)",
                "operating_point": None
            }

        test_params = deepcopy(base_params)
        if "tubing" in test_params.get("vlp", {}):
            test_params["vlp"]["tubing"]["d"] = d_val
        if "tubing_d" in test_params.get("vlp", {}):
            test_params["vlp"]["tubing_d"] = d_val

        try:
            res = await calculate(test_params)
            op = res.get("operating_point")
            if op:
                q_liq = op.get("q_liq", 0.0)
                p_wf = op.get("p_wf", 0.0)
                return {
                    "tubing_name": name,
                    "d_m": d_val,
                    "status": "success",
                    "operating_point": {"q_liq": q_liq, "p_wf": p_wf}
                }
            else:
                return {
                    "tubing_name": name,
                    "d_m": d_val,
                    "status": "no_intersection",
                    "reason": "Срыв фонтанирования",
                    "operating_point": None
                }
        except Exception as exc:
            return {
                "tubing_name": name,
                "d_m": d_val,
                "status": "error",
                "reason": str(exc),
                "operating_point": None
            }

    results = list(await asyncio.gather(*[_eval_diameter(item) for item in diameters]))

    for r in results:
        op = r.get("operating_point")
        if op and r.get("status") == "success":
            q_liq = op.get("q_liq", 0.0)
            if best_opt is None or q_liq > best_opt["q_liq"]:
                best_opt = op
                best_d = r.get("d_m")
                best_name = r.get("tubing_name")

    recommendation = ""
    if best_opt:
        recommendation = (
            f"Рекомендуется использовать типоразмер {best_name} (d = {best_d} м), "
            f"обеспечивающий максимальный дебит q_liq = {best_opt['q_liq']} м³/сут "
            f"при забойном давлении p_wf = {best_opt['p_wf']} атм."
        )
    else:
        recommendation = "Ни один из рассмотренных диаметров НКТ не обеспечивает условий фонтанирования."

    return {
        "analysis_type": "tubing_diameter_optimization",
        "best_tubing": {
            "name": best_name,
            "d_m": best_d,
            "operating_point": best_opt
        },
        "recommendation": recommendation,
        "scenarios": results
    }


async def find_critical_wct(
    base_params: Dict[str, Any],
    calculate: Callable[[Dict[str, Any]], Any],
    step_pct: float = 10.0
) -> Dict[str, Any]:
    """
    Определение критической обводненности (WCT_crit), при превышении которой
    гидростатическое давление тяжелого столба воды глушит скважину (срыв фонтанирования).
    """
    current_wct = float(base_params.get("ipr", {}).get("wct", 50.0))
    wct_test = current_wct
    history = []
    crit_wct = None

    while wct_test <= 95.0:
        test_params = deepcopy(base_params)
        if "ipr" in test_params:
            test_params["ipr"]["wct"] = wct_test
        if "vlp" in test_params and "pvt" in test_params["vlp"]:
            test_params["vlp"]["pvt"]["wct"] = wct_test

        try:
            res = await calculate(test_params)
            op = res.get("operating_point")
            if op:
                history.append({
                    "wct": wct_test,
                    "status": "flowing",
                    "q_liq": op.get("q_liq"),
                    "p_wf": op.get("p_wf")
                })
            else:
                crit_wct = wct_test
                history.append({
                    "wct": wct_test,
                    "status": "killed",
                    "reason": "Гидростатический столб воды превысил пластовую энергию"
                })
                break
        except Exception:
            crit_wct = wct_test
            history.append({
                "wct": wct_test,
                "status": "killed",
                "reason": "Расчетная ошибка / срыв"
            })
            break

        wct_test += step_pct

    summary = ""
    if crit_wct is not None:
        summary = (
            f"Критическая обводненность скважины составляет WCT_crit ≈ {crit_wct:.1f}%. "
            f"При дальнейшем росте обводнения фонтанирование прекратится — потребуется механизированная добыча (ЭЦН/ШГН)."
        )
    else:
        summary = "Скважина способна сохранять фонтанный режим даже при обводненности свыше 95%."

    return {
        "analysis_type": "critical_wct_analysis",
        "current_wct": current_wct,
        "critical_wct": crit_wct,
        "summary": summary,
        "curve": history
    }


async def optimize_wellhead_pressure(
    base_params: Dict[str, Any],
    calculate: Callable[[Dict[str, Any]], Any],
    min_p_wh: float = 2.0,
    max_p_wh: float = 30.0,
    steps: int = 7
) -> Dict[str, Any]:
    """
    Анализ чувствительности дебита к устьевому давлению (подбор штуцера / противодавления).
    """
    step_val = (max_p_wh - min_p_wh) / max(1, steps - 1)
    curve = []
    max_q = 0.0
    best_p_wh = min_p_wh

    for i in range(steps):
        p_val = round(min_p_wh + i * step_val, 1)
        test_params = deepcopy(base_params)
        if "vlp" in test_params:
            test_params["vlp"]["p_wh"] = p_val

        try:
            res = await calculate(test_params)
            op = res.get("operating_point")
            if op:
                q = op.get("q_liq", 0.0)
                curve.append({"p_wh": p_val, "q_liq": q, "p_wf": op.get("p_wf"), "status": "ok"})
                if q > max_q:
                    max_q = q
                    best_p_wh = p_val
            else:
                curve.append({"p_wh": p_val, "status": "no_flow", "reason": "Давление устья превысило предел подъема"})
        except Exception as exc:
            curve.append({"p_wh": p_val, "status": "error", "reason": str(exc)})

    return {
        "analysis_type": "wellhead_pressure_sensitivity",
        "optimal_p_wh": best_p_wh,
        "max_flow_rate": max_q,
        "sensitivity_curve": curve,
        "recommendation": f"Снижение устьевого давления до {best_p_wh} атм позволяет достичь максимального дебита {max_q} м³/сут."
    }
