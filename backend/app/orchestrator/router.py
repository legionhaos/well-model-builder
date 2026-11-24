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


@router.post("/calculate", response_model=CalculateResponse)
async def calculate_well(req: CalculateRequest):
    """
    Единая точка входа для расчета модели скважины:
    1. Валидация входных данных;
    2. Параллельный расчет IPR и VLP;
    3. Поиск точки пересечения в Nodal;
    4. Возврат кривых, рабочей точки и времени расчета.
    """
    ipr_payload = req.ipr.model_dump()
    vlp_payload = req.vlp.model_dump()

    res = await calc_client.run_full_calculation(
        ipr_payload=ipr_payload,
        vlp_payload=vlp_payload
    )
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
