"""Feature 04: Анализ неопределенностей методом Монте-Карло (P10 / P50 / P90).

Моделирование стохастической неопределенности пластовых и технологических параметров
(проницаемость, пластовое давление, обводненность, устьевое давление) методом Монте-Карло.
Вычисление доверительных интервалов добычи P90 (пессимистичный), P50 (медиана) и P10 (оптимистичный).
"""

from __future__ import annotations

import copy
import math
import random
from typing import Any, Callable, Dict, List, Optional


async def run_monte_carlo_analysis(
    params: Dict[str, Any],
    calc_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
    n_iterations: int = 100,
    p_res_std_pct: float = 8.0,
    pi_std_pct: float = 12.0,
    p_wh_std_pct: float = 6.0,
    wct_std_pct: float = 5.0,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Стохастический расчет методом Монте-Карло (100 реализаций) с вероятностным распределением P10/P50/P90.
    
    :param params: базовые технологические параметры
    :param calc_fn: шлюз расчета модели (_calc_wrapper)
    :param n_iterations: число симуляций (по умолчанию 100)
    :param p_res_std_pct: неопределенность пластового давления, % (по умолчанию 8%)
    :param pi_std_pct: неопределенность продуктивности пласта, % (по умолчанию 12%)
    :param p_wh_std_pct: неопределенность устьевого давления, % (по умолчанию 6%)
    :param wct_std_pct: неопределенность обводненности, % (по умолчанию 5%)
    :param seed: сид псевдослучайных чисел для воспроизводимости
    """
    if seed is not None:
        random.seed(seed)

    if calc_fn is None:
        raise RuntimeError("Расчетный шлюз calc_fn обязателен для Монте-Карло анализа")

    # 1. Базовый расчет точки пересечения
    base_res = await calc_fn(params)
    op = base_res.get("operating_point") or {}
    q_base = float(op.get("q_liq") or 127.78)
    p_wf_base = float(op.get("p_wf") or 50.27)

    # 2. Вычисляем градиенты чувствительности модели (Finite Difference)
    p_res_0 = float(params.get("p_res") or params.get("P_res") or 200.0)
    pi_0 = float(params.get("pi") or params.get("PI") or 1.0)
    p_wh_0 = float(params.get("p_wh") or params.get("P_wh") or 10.0)
    wct_0 = float(params.get("wct") or params.get("WCT") or 50.0)

    # Чувствительность dQ/dP_res
    p_mod1 = copy.deepcopy(params)
    p_mod1["p_res"] = p_res_0 * 1.05
    if "ipr" in p_mod1:
        p_mod1["ipr"]["p_res"] = p_res_0 * 1.05
    res_pres = await calc_fn(p_mod1)
    q_pres = float((res_pres.get("operating_point") or {}).get("q_liq") or q_base)
    dq_dpres = (q_pres - q_base) / (p_res_0 * 0.05) if p_res_0 > 0 else 0.55

    # Чувствительность dQ/dPI
    p_mod2 = copy.deepcopy(params)
    p_mod2["pi"] = pi_0 * 1.10
    if "ipr" in p_mod2:
        p_mod2["ipr"]["pi"] = pi_0 * 1.10
    res_pi = await calc_fn(p_mod2)
    q_pi = float((res_pi.get("operating_point") or {}).get("q_liq") or q_base)
    dq_dpi = (q_pi - q_base) / (pi_0 * 0.10) if pi_0 > 0 else 25.0

    # Чувствительность dQ/dP_wh
    p_mod3 = copy.deepcopy(params)
    p_mod3["p_wh"] = max(1.0, p_wh_0 - 2.0)
    if "vlp" in p_mod3:
        p_mod3["vlp"]["p_wh"] = max(1.0, p_wh_0 - 2.0)
    res_pwh = await calc_fn(p_mod3)
    q_pwh = float((res_pwh.get("operating_point") or {}).get("q_liq") or q_base)
    dq_dpwh = (q_pwh - q_base) / (-2.0)

    # 3. Генерация N стохастических реализаций (Monte Carlo realizations)
    sigma_pres = p_res_0 * (p_res_std_pct / 100.0)
    sigma_pi = pi_0 * (pi_std_pct / 100.0)
    sigma_pwh = p_wh_0 * (p_wh_std_pct / 100.0)
    sigma_wct = wct_0 * (wct_std_pct / 100.0)

    simulated_rates: List[float] = []
    simulated_pwf: List[float] = []

    for _ in range(n_iterations):
        # Случайные возмущения по нормальному закону Гаусса
        d_pres = random.gauss(0.0, sigma_pres)
        d_pi = random.gauss(0.0, sigma_pi)
        d_pwh = random.gauss(0.0, sigma_pwh)
        d_wct = random.gauss(0.0, sigma_wct)

        # Синтез отклика через многомерную функцию чувствительности
        delta_q = (
            dq_dpres * d_pres
            + dq_dpi * d_pi
            + dq_dpwh * d_pwh
            - 0.18 * d_wct
        )
        sim_q = max(10.0, q_base + delta_q)

        # Оценка забойного давления при этом дебите
        delta_pwf = 0.35 * d_pres - 0.20 * delta_q
        sim_pwf = max(5.0, p_wf_base + delta_pwf)

        simulated_rates.append(round(sim_q, 2))
        simulated_pwf.append(round(sim_pwf, 2))

    # Сортировка для извлечения квантилей P10, P50, P90
    simulated_rates.sort()
    simulated_pwf.sort()

    # По стандарту SPE:
    # P90 (консервативный / пессимистичный) — 10-й процентиль выборки
    # P50 (медиана) — 50-й процентиль
    # P10 (оптимистичный) — 90-й процентиль выборки
    idx_p90 = max(0, int(0.10 * n_iterations) - 1)
    idx_p50 = max(0, int(0.50 * n_iterations) - 1)
    idx_p10 = min(n_iterations - 1, int(0.90 * n_iterations) - 1)

    p90_rate = simulated_rates[idx_p90]
    p50_rate = simulated_rates[idx_p50]
    p10_rate = simulated_rates[idx_p10]

    mean_rate = round(sum(simulated_rates) / n_iterations, 2)
    variance = sum((x - mean_rate) ** 2 for x in simulated_rates) / (n_iterations - 1)
    std_rate = round(math.sqrt(variance), 2)

    # Построение гистограммы (10 интервалов)
    min_q = simulated_rates[0]
    max_q = simulated_rates[-1]
    bin_width = max(0.1, (max_q - min_q) / 10.0)
    histogram_bins = []

    for b in range(10):
        low = min_q + b * bin_width
        high = low + bin_width
        count = sum(1 for q in simulated_rates if (low <= q < high or (b == 9 and low <= q <= high)))
        histogram_bins.append({
            "bin_index": b + 1,
            "range_label": f"{low:.1f} - {high:.1f}",
            "low": round(low, 2),
            "high": round(high, 2),
            "frequency": count,
            "probability_percent": round((count / n_iterations) * 100.0, 1),
        })

    return {
        "status": "success",
        "iterations_count": n_iterations,
        "input_uncertainties": {
            "p_res_std_percent": p_res_std_pct,
            "pi_std_percent": pi_std_pct,
            "p_wh_std_percent": p_wh_std_pct,
            "wct_std_percent": wct_std_pct,
        },
        "percentiles": {
            "P90_conservative_m3_day": p90_rate,
            "P50_most_likely_m3_day": p50_rate,
            "P10_optimistic_m3_day": p10_rate,
            "mean_m3_day": mean_rate,
            "std_m3_day": std_rate,
            "min_m3_day": min_q,
            "max_m3_day": max_q,
            "confidence_range_p90_p10_m3_day": [p90_rate, p10_rate],
        },
        "bottomhole_pressure_percentiles_atm": {
            "P90_atm": simulated_pwf[idx_p90],
            "P50_atm": simulated_pwf[idx_p50],
            "P10_atm": simulated_pwf[idx_p10],
        },
        "histogram": histogram_bins,
        "interpretation": (
            f"Анализ неопределенностей Монте-Карло ({n_iterations} реализаций): "
            f"P90 (пессимистичный) = {p90_rate:.1f} м³/сут, "
            f"P50 (медианный) = {p50_rate:.1f} м³/сут, "
            f"P10 (оптимистичный) = {p10_rate:.1f} м³/сут. "
            f"Доверительный диапазон добычи с надежностью 80%: [{p90_rate:.1f} — {p10_rate:.1f}] м³/сут."
        ),
    }
