import math
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class IPRRequest(BaseModel):
    p_res: float = Field(..., description="Пластовое давление, атм")
    wct: float = Field(..., description="Обводненность, %")
    pi: float = Field(..., description="Коэффициент продуктивности, м3/(сут*атм)")
    pb: float = Field(..., description="Давление насыщения, атм")
    points: Optional[int] = Field(21, description="Количество расчетных точек, по умолчанию 21")

    @field_validator("p_res")
    @classmethod
    def validate_p_res(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("p_res должно быть конечным числом")
        if v <= 0:
            raise ValueError("p_res должен быть больше 0")
        return v

    @field_validator("wct")
    @classmethod
    def validate_wct(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("wct должно быть конечным числом")
        if v < 0 or v > 100:
            raise ValueError("wct должно быть в диапазоне от 0 до 100")
        return v

    @field_validator("pi")
    @classmethod
    def validate_pi(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("pi должно быть конечным числом")
        if v < 0:
            raise ValueError("pi должно быть неотрицательным")
        return v

    @field_validator("pb")
    @classmethod
    def validate_pb(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("pb должно быть конечным числом")
        if v < 0:
            raise ValueError("pb должно быть неотрицательным")
        return v

    @field_validator("points")
    @classmethod
    def validate_points(cls, v: Optional[int]) -> int:
        if v is None:
            return 21
        if v < 2 or v > 201:
            raise ValueError("points должно быть в диапазоне от 2 до 201")
        return v


class IPRResponse(BaseModel):
    q_liq: List[float] = Field(..., description="Суммарный дебит жидкости, м3/сут")
    p_wf: List[float] = Field(..., description="Забойное давление, атм")


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "ipr"


class ErrorResponse(BaseModel):
    message: str
    description: str
    detail: Optional[str] = None
