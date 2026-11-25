from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status

from app.orchestrator.schemas import (
    CalculateRequest,
    CalculateResponse,
    PresetItem
)
from app.orchestrator.presets import PRESETS
from app.orchestrator.client import calc_client

router = APIRouter(prefix="/api", tags=["Orchestration"])


def inspect_physical_warnings(
    ipr_payload: Dict[str, Any],
    vlp_payload: Dict[str, Any],
    calc_res: Dict[str, Any],
) -> List[str]:
    """Проверка физической корректности входных данных и полученной рабочей точки."""
    warnings: List[str] = []
    wct = float(ipr_payload.get("wct", 0.0))
    pvt_wct = vlp_payload.get("pvt", {}).get("wct")
    p_res = float(ipr_payload.get("p_res", 0.0))
    pi = float(ipr_payload.get("pi", 0.0))
    p_wh = float(vlp_payload.get("p_wh", 0.0))
    tub_d = float(vlp_payload.get("tubing", {}).get("d", 0.0))
    cas_d = float(vlp_payload.get("casing", {}).get("d", 0.0))
    h_mes = float(vlp_payload.get("tubing", {}).get("h_mes", 0.0))
    h_res = float(vlp_payload.get("h_res", 0.0))

    if wct < 0.0 or wct > 100.0:
        warnings.append(f"Обводнённость WCT = {wct:g}% указана некорректно (допустимо 0–100%). Расчёт нефизичен.")
    if pvt_wct is not None:
        pvt_w = float(pvt_wct)
        if pvt_w < 0.0 or pvt_w > 100.0:
            warnings.append(f"Обводнённость PVT = {pvt_w:g}% выходит за пределы 0–100%.")
        elif abs(wct - pvt_w) > 0.1:
            warnings.append(f"Рассогласование обводнённости: IPR ({wct:g}%) != PVT ({pvt_w:g}%).")
    if p_res <= 0.0:
        warnings.append(f"Пластовое давление P_res = {p_res:g} атм <= 0 — приток невозможен.")
    if pi <= 0.0:
        warnings.append(f"Продуктивность PI = {pi:g} <= 0 — приток отсутствует.")
    if p_wh < 0.0:
        warnings.append(f"Устьевое давление P_wh = {p_wh:g} атм < 0 — нефизичное значение.")
    if tub_d <= 0.0 or cas_d <= 0.0 or tub_d >= cas_d:
        warnings.append(f"Нарушена геометрия ствола: диаметр НКТ ({tub_d:g} м) >= ЭК ({cas_d:g} м).")
    if h_mes > h_res:
        warnings.append(f"Спуск НКТ ({h_mes:g} м) больше глубины пласта ({h_res:g} м).")

    op = calc_res.get("operating_point")
    if isinstance(op, dict):
        q_liq = float(op.get("q_liq", 0.0))
        p_wf = float(op.get("p_wf", 0.0))
        if q_liq <= 0.0:
            warnings.append(f"Отрицательный или нулевой дебит q_liq = {q_liq:.2f} м³/сут — модель неработоспособна.")
        if p_wf < 0.0:
            warnings.append(f"Отрицательное забойное давление p_wf = {p_wf:.2f} атм — нефизичная точка.")

    ipr_curve = calc_res.get("ipr") or {}
    vlp_curve = calc_res.get("vlp") or {}
    if any(float(q) < 0.0 for q in ipr_curve.get("q_liq", []) + vlp_curve.get("q_liq", [])):
        warnings.append("Обнаружен отрицательный дебит на расчётной кривой (значение исключается из основного графика).")
    if any(float(p) < 0.0 for p in ipr_curve.get("p_wf", []) + vlp_curve.get("p_wf", [])):
        warnings.append("Обнаружено отрицательное забойное давление на расчётной кривой.")

    return warnings


@router.post("/calculate", response_model=CalculateResponse)
async def calculate_well(req: CalculateRequest):
    """
    Единая точка входа для расчета модели скважины:
    1. Валидация входных данных;
    2. Параллельный расчет IPR и VLP;
    3. Поиск точки пересечения в Nodal;
    4. Проверка физической корректности и возврат предупреждений.
    """
    ipr_payload = req.ipr.model_dump()
    vlp_payload = req.vlp.model_dump()

    res = await calc_client.run_full_calculation(
        ipr_payload=ipr_payload,
        vlp_payload=vlp_payload
    )
    warnings = inspect_physical_warnings(ipr_payload, vlp_payload, res)
    meta = res.setdefault("meta", {})
    meta["warnings"] = warnings
    meta["is_physical"] = len(warnings) == 0
    return res


@router.get("/presets", response_model=List[PresetItem])
async def get_presets():
    """
    Получение списка готовых пресетов скважин (well_01, высокая обводненность, кейс без пересечения).
    """
    return PRESETS


@router.get("/presets/{preset_id}", response_model=PresetItem)
async def get_preset_by_id(preset_id: str):
    """
    Получение конкретного пресета по его ID.
    """
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Пресет '{preset_id}' не найден"
    )
