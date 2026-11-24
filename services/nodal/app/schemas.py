import math
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class CurveData(BaseModel):
    q_liq: List[float] = Field(..., description="Дебиты жидкости, м3/сут")
    p_wf: List[float] = Field(..., description="Забойные давления, атм")

    @model_validator(mode="after")
    def validate_curve(self):
        if len(self.q_liq) != len(self.p_wf):
            raise ValueError("Массивы q_liq и p_wf должны быть одинаковой длины")
        if len(self.q_liq) < 2:
            raise ValueError("В кривой должно быть минимум 2 точки")
        for i, (q, p) in enumerate(zip(self.q_liq, self.p_wf)):
            if not (math.isfinite(q) and math.isfinite(p)):
                raise ValueError(f"Точка #{i} содержит некорректное число (NaN/Inf)")
            if q < 0:
                raise ValueError(f"q_liq в точке #{i} не может быть отрицательным: {q}")
            if p <= 0:
                raise ValueError(f"p_wf в точке #{i} должно быть строго положительным: {p}")
        return self


class NodalRequest(BaseModel):
    ipr: CurveData
    vlp: CurveData


class NodalPoint(BaseModel):
    q_liq: float = Field(..., description="Дебит жидкости в рабочей точке, м3/сут")
    p_wf: float = Field(..., description="Забойное давление в рабочей точке, атм")


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "nodal"


class ErrorResponse(BaseModel):
    message: str
    description: str
    detail: Optional[str] = None
