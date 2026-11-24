import math
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator


class Inclinometry(BaseModel):
    MD: List[float] = Field(..., description="Измеренная глубина по стволу, м")
    TVD: List[float] = Field(..., description="Вертикальная глубина, м")

    @model_validator(mode="after")
    def validate_inclinometry(self):
        if len(self.MD) != len(self.TVD):
            raise ValueError("Массивы MD и TVD должны быть одинаковой длины")
        if len(self.MD) < 2:
            raise ValueError("Инклинометрия должна содержать минимум 2 точки")
        for i in range(len(self.MD) - 1):
            if not math.isfinite(self.MD[i]) or not math.isfinite(self.TVD[i]):
                raise ValueError(f"Точка инклинометрии #{i} содержит NaN/Inf")
            if self.MD[i] >= self.MD[i + 1]:
                raise ValueError(f"MD должно строго возрастать: MD[{i}]={self.MD[i]} >= MD[{i+1}]={self.MD[i+1]}")
            if self.TVD[i] > self.TVD[i + 1]:
                raise ValueError(f"TVD не должно убывать: TVD[{i}]={self.TVD[i]} > TVD[{i+1}]={self.TVD[i+1]}")
        if not math.isfinite(self.MD[-1]) or not math.isfinite(self.TVD[-1]):
            raise ValueError("Последняя точка инклинометрии содержит NaN/Inf")
        return self


class Casing(BaseModel):
    d: float = Field(..., description="Внутренний диаметр эксплуатационной колонны, м")

    @field_validator("d")
    @classmethod
    def validate_d(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("casing.d должно быть положительным числом")
        return v


class Tubing(BaseModel):
    d: float = Field(..., description="Внутренний диаметр НКТ, м")
    h_mes: float = Field(..., description="Глубина спуска башмака НКТ по стволу, м")

    @field_validator("d")
    @classmethod
    def validate_d(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("tubing.d должно быть положительным числом")
        return v

    @field_validator("h_mes")
    @classmethod
    def validate_h_mes(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("tubing.h_mes должно быть положительным числом")
        return v


class PVTData(BaseModel):
    wct: float = Field(..., description="Обводненность, %")
    rp: float = Field(..., description="Газовый фактор, м3/т")
    gamma_oil: float = Field(..., description="Относительная плотность нефти")
    gamma_gas: float = Field(..., description="Относительная плотность газа к воздуху")
    gamma_wat: float = Field(..., description="Относительная плотность воды")
    t_res: Optional[float] = Field(None, description="Пластовая температура, °C")

    @field_validator("wct")
    @classmethod
    def validate_wct(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0 or v > 100:
            raise ValueError("pvt.wct должно быть в диапазоне от 0 до 100")
        return v

    @field_validator("rp", "gamma_oil", "gamma_gas", "gamma_wat")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("Параметры PVT (rp, gamma_oil, gamma_gas, gamma_wat) должны быть > 0")
        return v


class VLPRequest(BaseModel):
    inclinometry: Inclinometry
    casing: Casing
    tubing: Tubing
    pvt: PVTData
    p_wh: float = Field(..., description="Буферное (устьевое) давление, атм")
    geo_grad: float = Field(..., description="Геотермический градиент, °C/100м")
    h_res: float = Field(..., description="Глубина пласта по стволу, м")
    t_res: Optional[float] = Field(None, description="Пластовая температура, °C")
    roughness: Optional[float] = Field(0.0001, description="Относительная шероховатость, по умолчанию 0.0001")
    q_max: Optional[float] = Field(400.0, description="Максимальный дебит, м3/сут, по умолчанию 400")
    points: Optional[int] = Field(21, description="Число точек, по умолчанию 21")

    @model_validator(mode="before")
    @classmethod
    def normalize_t_res(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Если t_res внутри pvt, продублируем на верхний уровень и наоборот
            pvt_dict = data.get("pvt")
            if isinstance(pvt_dict, dict):
                if "t_res" in pvt_dict and "t_res" not in data:
                    data["t_res"] = pvt_dict["t_res"]
                elif "t_res" in data and "t_res" not in pvt_dict:
                    pvt_dict["t_res"] = data["t_res"]
        return data

    @model_validator(mode="after")
    def validate_vlp(self):
        # Проверка диаметров: casing.d > tubing.d
        if self.casing.d <= self.tubing.d:
            raise ValueError(
                f"Диаметр эксплуатационной колонны casing.d ({self.casing.d}) должен быть строго больше tubing.d ({self.tubing.d})"
            )

        # Проверка глубин: h_mes < h_res <= max(MD)
        max_md = max(self.inclinometry.MD)
        if self.tubing.h_mes >= self.h_res:
            raise ValueError(
                f"Глубина спуска НКТ tubing.h_mes ({self.tubing.h_mes}) должна быть строго меньше глубины пласта h_res ({self.h_res})"
            )
        if self.h_res > max_md:
            raise ValueError(
                f"Глубина пласта h_res ({self.h_res}) не может превышать максимальную глубину по инклинометрии ({max_md})"
            )

        # Проверка устьевого давления
        if not math.isfinite(self.p_wh) or self.p_wh <= 0:
            raise ValueError("Устьевое давление p_wh должно быть строго больше 0")

        # Проверка t_res
        resolved_t_res = self.t_res if self.t_res is not None else self.pvt.t_res
        if resolved_t_res is None or not math.isfinite(resolved_t_res):
            raise ValueError("Параметр t_res (пластовая температура) обязателен и должен быть числом")

        # Проверка roughness
        r = self.roughness if self.roughness is not None else 0.0001
        if not math.isfinite(r) or r <= 0:
            raise ValueError("roughness должно быть положительным числом")

        # Проверка q_max
        qm = self.q_max if self.q_max is not None else 400.0
        if not math.isfinite(qm) or qm <= 0:
            raise ValueError("q_max должно быть положительным числом")

        # Проверка points
        pts = self.points if self.points is not None else 21
        if pts < 2 or pts > 201:
            raise ValueError("points должно быть в диапазоне от 2 до 201")

        return self

    def get_resolved_t_res(self) -> float:
        if self.t_res is not None:
            return self.t_res
        if self.pvt.t_res is not None:
            return self.pvt.t_res
        return 90.0


class VLPResponse(BaseModel):
    q_liq: List[float] = Field(..., description="Дебиты жидкости, м3/сут")
    p_wf: List[float] = Field(..., description="Забойные давления, атм")


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "vlp"


class ErrorResponse(BaseModel):
    message: str
    description: str
    detail: Optional[str] = None
