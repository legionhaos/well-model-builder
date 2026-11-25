"""Feature 02: Оценка риска самозадавливания и эрозии (Критерии Turner и API 14E).

Физическая диагностика гидродинамики ствола скважины:
- Критерий Тернера (Turner Droplet Model) на вынос капель жидкости и риск Liquid Loading.
- Стандарт API RP 14E на эрозионный предел скорости смеси для защиты НКТ и арматуры.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional


def evaluate_flow_assurance(
    params: Dict[str, Any],
    calculation_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Анализ гидродинамической стабильности и эрозионной безопасности потока в НКТ.
    
    :param params: технологические параметры скважины (d, p_wh, t_res, rp, wct, gamma_oil, gamma_gas)
    :param calculation_result: расчетная рабочая точка (q_liq, p_wf)
    """
    # 1. Считываем параметры
    d_tubing = float(params.get("d") or params.get("d_tubing") or 0.062) # диаметр НКТ, м
    p_wh = float(params.get("p_wh") or params.get("P_wh") or 10.0) # устьевое давление, атм
    wct = float(params.get("wct") or params.get("WCT") or 50.0) # обводненность, %
    rp = float(params.get("rp") or params.get("Rp") or 100.0) # газовый фактор, м3/т
    t_res = float(params.get("t_res") or params.get("T_res") or 90.0) # пластовая темп, °C

    gamma_oil = float(params.get("gamma_oil") or params.get("pvt", {}).get("gamma_oil") or 0.86)
    gamma_gas = float(params.get("gamma_gas") or params.get("pvt", {}).get("gamma_gas") or 0.8)

    # Дебит жидкости в рабочей точке
    q_liq = 0.0
    if calculation_result:
        op = calculation_result.get("operating_point") or {}
        q_liq = float(op.get("q_liq") or 0.0)

    # 2. Термобарические условия на устье
    # Оценка температуры устья (охлаждение по стволу ~ 20-30°C)
    t_wh_c = max(15.0, t_res - 35.0)
    t_wh_k = t_wh_c + 273.15
    p_wh_pa = p_wh * 101325.0

    # Плотности компонентов
    rho_oil = gamma_oil * 1000.0 # кг/м3
    rho_water = 1000.0 # кг/м3
    rho_liq = rho_oil * (1.0 - wct / 100.0) + rho_water * (wct / 100.0) # кг/м3

    # Плотность газа на устье (уравнение Менделеева-Клапейрона с z~0.9)
    m_gas_mol = gamma_gas * 0.02897 # кг/моль (воздух ~ 28.97 г/моль)
    z_factor = 0.90
    r_gas_const = 8.314
    rho_gas_wh = (p_wh_pa * m_gas_mol) / (z_factor * r_gas_const * t_wh_k) # кг/м3

    # Площадь проходного сечения НКТ
    a_tubing = math.pi * (d_tubing ** 2) / 4.0 # м2

    # Объемный расход газа на устье в рабочих условиях
    # Массовый расход нефти и объемный расход газа при ст.усл.
    q_oil_tons_day = q_liq * (1.0 - wct / 100.0) * gamma_oil
    q_gas_std_day = q_oil_tons_day * rp # м3(ст.усл.)/сут
    q_gas_std_sec = q_gas_std_day / 86400.0

    # Объем газа при P_wh, T_wh
    p_std_pa = 101325.0
    t_std_k = 293.15
    q_gas_wh_sec = q_gas_std_sec * (p_std_pa / p_wh_pa) * (t_wh_k / t_std_k) * z_factor
    q_liq_sec = (q_liq / 86400.0)

    # Фактическая скорость газа и смеси на устье
    v_gas_actual = q_gas_wh_sec / a_tubing if a_tubing > 0 else 0.0
    v_mix_actual = (q_gas_wh_sec + q_liq_sec) / a_tubing if a_tubing > 0 else 0.0

    # =========================================================================
    # А. КРИТЕРИЙ ТЕРНЕРА (Turner Droplet Model) — Самозадавливание скважины
    # =========================================================================
    # v_crit = 1.593 * [ sigma * (rho_L - rho_g) / (rho_g^2) ]^(0.25)
    # Поверхностное натяжение нефть/вода-газ sigma ~ 0.025 Н/м
    sigma = 0.025
    delta_rho = max(1.0, rho_liq - rho_gas_wh)
    v_turner_crit = 1.593 * ((sigma * delta_rho) / (rho_gas_wh ** 2)) ** 0.25 # м/с

    # Запас до захлебывания (Liquid Loading Margin)
    if v_turner_crit > 0:
        turner_margin_percent = round(((v_gas_actual - v_turner_crit) / v_turner_crit) * 100.0, 1)
    else:
        turner_margin_percent = 0.0

    is_liquid_loading = v_gas_actual < v_turner_crit

    if is_liquid_loading:
        turner_status = "CRITICAL_LIQUID_LOADING"
        turner_recommendation = (
            f"КРИТИЧЕСКИЙ РИСК САМОЗАДАВЛИВАНИЯ: скорость газа ({v_gas_actual:.2f} м/с) ниже "
            f"критической скорости выноса капель по Тернеру ({v_turner_crit:.2f} м/с). "
            f"Капли жидкости падают на забой, скважина захлёбывается. "
            f"Рекомендуется уменьшить диаметр НКТ до 60 мм или перейти на механизированный лифт (ЭЦН/Газлифт)."
        )
    else:
        turner_status = "SAFE_CONTINUOUS_LIFT"
        turner_recommendation = (
            f"Устойчивый вынос жидкости обеспечен: скорость газа ({v_gas_actual:.2f} м/с) превышает "
            f"порог Тернера ({v_turner_crit:.2f} м/с). Запас устойчивости фонтанирования: +{turner_margin_percent}%."
        )

    # =========================================================================
    # Б. СТАНДАРТ API RP 14E — Предел эрозионной скорости потока
    # =========================================================================
    # v_erosional = C / sqrt(rho_mix)
    # C = 122 (SI units для непрерывного потока без песка)
    total_vol_sec = q_gas_wh_sec + q_liq_sec
    if total_vol_sec > 0:
        rho_mix = (rho_liq * q_liq_sec + rho_gas_wh * q_gas_wh_sec) / total_vol_sec
    else:
        rho_mix = rho_liq

    c_api = 122.0
    v_erosional_limit = c_api / math.sqrt(max(1.0, rho_mix)) # м/с

    erosion_ratio_percent = round((v_mix_actual / v_erosional_limit) * 100.0, 1) if v_erosional_limit > 0 else 0.0
    is_erosion_hazard = v_mix_actual > v_erosional_limit

    if is_erosion_hazard:
        erosion_status = "EROSION_HAZARD"
        erosion_recommendation = (
            f"ОПАСНОСТЬ ЭРОЗИИ (API RP 14E): фактическая скорость смеси ({v_mix_actual:.2f} м/с) "
            f"превышает допустимый предел ({v_erosional_limit:.2f} м/с, нагрузка {erosion_ratio_percent}%). "
            f"Высокий риск абразивного износа стенок НКТ и устьевой арматуры. Необходимо штуцирование скважины."
        )
    else:
        erosion_status = "EROSION_SAFE"
        erosion_recommendation = (
            f"Эрозионная безопасность соблюдена (стандарт API RP 14E): скорость смеси "
            f"{v_mix_actual:.2f} м/с находится в пределах нормы (< {v_erosional_limit:.2f} м/с, "
            f"нагрузка {erosion_ratio_percent}% от предела разрушения)."
        )

    return {
        "status": "success",
        "turner_liquid_loading": {
            "status": turner_status,
            "is_risk": is_liquid_loading,
            "actual_gas_velocity_m_s": round(v_gas_actual, 2),
            "critical_turner_velocity_m_s": round(v_turner_crit, 2),
            "loading_margin_percent": turner_margin_percent,
            "recommendation": turner_recommendation,
        },
        "api_14e_erosion": {
            "status": erosion_status,
            "is_hazard": is_erosion_hazard,
            "actual_mixture_velocity_m_s": round(v_mix_actual, 2),
            "erosional_velocity_limit_m_s": round(v_erosional_limit, 2),
            "erosion_load_percent": erosion_ratio_percent,
            "recommendation": erosion_recommendation,
        },
        "thermodynamics": {
            "wellhead_pressure_atm": p_wh,
            "wellhead_temp_c": round(t_wh_c, 1),
            "mixture_density_kg_m3": round(rho_mix, 1),
            "gas_density_wh_kg_m3": round(rho_gas_wh, 2),
            "tubing_area_m2": round(a_tubing, 5),
        },
    }
