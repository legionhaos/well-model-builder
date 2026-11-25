"""Feature 01: Экономический калькулятор эффекта (Unit Economics в рублях).

Расчет финансового эффекта оптимизации скважины:
- Чистый прирост добычи нефти (т/сут и м3/сут)
- Маржинальная прибыль с учетом НДПИ, транспорта и подготовки попутной воды
- Годовой экономический эффект (млн руб./год)
- Срок окупаемости смены лифта / операции ТКРС (в днях)
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def calculate_unit_economics(
    base_params: Dict[str, Any],
    base_result: Optional[Dict[str, Any]] = None,
    opt_params: Optional[Dict[str, Any]] = None,
    opt_result: Optional[Dict[str, Any]] = None,
    oil_price_rub: float = 35000.0,
    ndpi_rub: float = 18000.0,
    transport_rub: float = 2500.0,
    water_treatment_rub: float = 150.0,
    workover_cost_rub: float = 1800000.0,
) -> Dict[str, Any]:
    """
    Расчет юнит-экономики эксплуатации скважины и эффекта от геолого-технических мероприятий / подбора НКТ.
    
    :param base_params: базовые параметры скважины (WCT, PVT gamma_oil и т.д.)
    :param base_result: результат базового расчета (дебит жидкости q_liq, забойное давление p_wf)
    :param opt_params: оптимизированные параметры (опционально)
    :param opt_result: результат оптимизированного расчета (опционально)
    :param oil_price_rub: цена реализации нефти на внутреннем рынке, руб./т (по умолчанию 35 000)
    :param ndpi_rub: ставка НДПИ на тонну нефти, руб./т (по умолчанию 18 000)
    :param transport_rub: тариф на транспортировку и диспетчеризацию нефти, руб./т (по умолчанию 2 500)
    :param water_treatment_rub: затраты на сбор, сепарацию и утилизацию подтоварной воды, руб./м3 (по умолчанию 150)
    :param workover_cost_rub: стоимость операции ТКРС по замене НКТ, руб. (по умолчанию 1 800 000)
    """
    # 1. Извлекаем базовые технологические показатели
    base_wct = float(base_params.get("wct") or base_params.get("WCT") or 50.0)
    gamma_oil = float(
        base_params.get("gamma_oil")
        or base_params.get("pvt", {}).get("gamma_oil")
        or 0.86
    )

    base_q_liq = 0.0
    if base_result:
        op = base_result.get("operating_point") or {}
        base_q_liq = float(op.get("q_liq") or 0.0)

    # Дебит нефти и воды в базе
    base_q_oil_m3 = base_q_liq * (1.0 - base_wct / 100.0)
    base_q_oil_tons = base_q_oil_m3 * gamma_oil
    base_q_water_m3 = base_q_liq * (base_wct / 100.0)

    # Чистая маржа с 1 тонны нефти после вычета НДПИ и транспорта
    net_oil_margin_rub_ton = max(0.0, oil_price_rub - ndpi_rub - transport_rub)

    # Базовая суточная чистая прибыль (OPEX воды вычитается)
    base_daily_profit_rub = (base_q_oil_tons * net_oil_margin_rub_ton) - (base_q_water_m3 * water_treatment_rub)
    base_annual_profit_rub = base_daily_profit_rub * 365.0

    # 2. Оптимизированный режим (если передан)
    opt_wct = base_wct
    if opt_params:
        opt_wct = float(opt_params.get("wct") or opt_params.get("WCT") or base_wct)

    opt_q_liq = base_q_liq
    if opt_result:
        op_opt = opt_result.get("operating_point") or {}
        opt_q_liq = float(op_opt.get("q_liq") or base_q_liq)

    opt_q_oil_m3 = opt_q_liq * (1.0 - opt_wct / 100.0)
    opt_q_oil_tons = opt_q_oil_m3 * gamma_oil
    opt_q_water_m3 = opt_q_liq * (opt_wct / 100.0)

    opt_daily_profit_rub = (opt_q_oil_tons * net_oil_margin_rub_ton) - (opt_q_water_m3 * water_treatment_rub)
    opt_annual_profit_rub = opt_daily_profit_rub * 365.0

    # Дельты (приросты)
    delta_q_liq = opt_q_liq - base_q_liq
    delta_q_oil_m3 = opt_q_oil_m3 - base_q_oil_m3
    delta_q_oil_tons = opt_q_oil_tons - base_q_oil_tons
    delta_daily_profit_rub = opt_daily_profit_rub - base_daily_profit_rub
    delta_annual_profit_rub = delta_daily_profit_rub * 365.0

    # Срок окупаемости затрат на смену лифта (ТКРС)
    if delta_daily_profit_rub > 10.0:
        payback_days = round(workover_cost_rub / delta_daily_profit_rub, 1)
        payback_status = f"{payback_days} дней"
    elif delta_daily_profit_rub <= 0.0 and opt_result:
        payback_days = None
        payback_status = "Окупаемость не достигается (прирост прибыли отсутствует)"
    else:
        payback_days = 0.0
        payback_status = "Текущий режим (без инвестиций на замену оборудования)"

    # Формируем итоговую карточку инвестора
    executive_summary = (
        f"Оптимизация режима: прирост нефти {delta_q_oil_tons:+.2f} т/сут "
        f"({delta_q_oil_m3:+.2f} м³/сут). "
        f"Чистый экономический эффект: {delta_daily_profit_rub:+,.0f} руб./сутки "
        f"({delta_annual_profit_rub / 1_000_000:+.2f} млн руб./год). "
        f"Срок окупаемости смены лифта: {payback_status}."
    )

    return {
        "status": "success",
        "inputs": {
            "oil_price_rub_ton": oil_price_rub,
            "ndpi_rub_ton": ndpi_rub,
            "transport_rub_ton": transport_rub,
            "water_treatment_rub_m3": water_treatment_rub,
            "workover_cost_rub": workover_cost_rub,
            "net_margin_rub_ton": net_oil_margin_rub_ton,
        },
        "base_regime": {
            "q_liq_m3_day": round(base_q_liq, 2),
            "q_oil_m3_day": round(base_q_oil_m3, 2),
            "q_oil_tons_day": round(base_q_oil_tons, 2),
            "q_water_m3_day": round(base_q_water_m3, 2),
            "daily_profit_rub": round(base_daily_profit_rub, 0),
            "annual_profit_million_rub": round(base_annual_profit_rub / 1_000_000.0, 2),
        },
        "optimized_regime": {
            "q_liq_m3_day": round(opt_q_liq, 2),
            "q_oil_m3_day": round(opt_q_oil_m3, 2),
            "q_oil_tons_day": round(opt_q_oil_tons, 2),
            "q_water_m3_day": round(opt_q_water_m3, 2),
            "daily_profit_rub": round(opt_daily_profit_rub, 0),
            "annual_profit_million_rub": round(opt_annual_profit_rub / 1_000_000.0, 2),
        },
        "deltas": {
            "delta_q_liq_m3_day": round(delta_q_liq, 2),
            "delta_q_oil_m3_day": round(delta_q_oil_m3, 2),
            "delta_q_oil_tons_day": round(delta_q_oil_tons, 2),
            "delta_daily_profit_rub": round(delta_daily_profit_rub, 0),
            "delta_annual_profit_million_rub": round(delta_annual_profit_rub / 1_000_000.0, 2),
            "payback_period_days": payback_days,
            "payback_status": payback_status,
        },
        "executive_summary": executive_summary,
    }
