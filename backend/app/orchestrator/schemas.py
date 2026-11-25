import math
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, model_validator


class InclinometryDTO(BaseModel):
    MD: List[float]
    TVD: List[float]


class CasingDTO(BaseModel):
    d: float


class TubingDTO(BaseModel):
    d: float
    h_mes: float


class PVTDTO(BaseModel):
    wct: float
    rp: float
    gamma_oil: float
    gamma_gas: float
    gamma_wat: float
    t_res: Optional[float] = None


class IPRInputDTO(BaseModel):
    p_res: float
    wct: float
    pi: float
    pb: float
    points: Optional[int] = 21


class VLPInputDTO(BaseModel):
    inclinometry: InclinometryDTO
    casing: CasingDTO
    tubing: TubingDTO
    pvt: PVTDTO
    p_wh: float
    geo_grad: float
    h_res: float
    t_res: Optional[float] = None
    roughness: Optional[float] = 0.0001
    q_max: Optional[float] = 400.0
    points: Optional[int] = 21


class CalculateRequest(BaseModel):
    """
    Запрос на полный расчет скважины.
    Поддерживает как структуру с разделением {'ipr': {...}, 'vlp': {...}},
    так и единую структуру параметров скважины.
    """
    ipr: Optional[IPRInputDTO] = None
    vlp: Optional[VLPInputDTO] = None

    # Поля для плоского формата (удобно для фронтенда и ИИ)
    p_res: Optional[float] = None
    wct: Optional[float] = None
    pi: Optional[float] = None
    pb: Optional[float] = None
    inclinometry: Optional[InclinometryDTO] = None
    casing: Optional[CasingDTO] = None
    tubing: Optional[TubingDTO] = None
    pvt: Optional[PVTDTO] = None
    p_wh: Optional[float] = None
    geo_grad: Optional[float] = None
    h_res: Optional[float] = None
    t_res: Optional[float] = None
    roughness: Optional[float] = 0.0001
    q_max: Optional[float] = 400.0
    points: Optional[int] = 21

    @model_validator(mode="after")
    def assemble_requests(self):
        # Если ipr не задан, но переданы плоские поля
        if self.ipr is None:
            if None not in (self.p_res, self.wct, self.pi, self.pb):
                self.ipr = IPRInputDTO(
                    p_res=self.p_res,
                    wct=self.wct,
                    pi=self.pi,
                    pb=self.pb,
                    points=self.points or 21
                )
            else:
                raise ValueError("Не переданы обязательные параметры IPR (p_res, wct, pi, pb)")

        # Если vlp не задан, но переданы плоские поля
        if self.vlp is None:
            if (
                self.inclinometry is not None
                and self.casing is not None
                and self.tubing is not None
                and self.p_wh is not None
                and self.geo_grad is not None
                and self.h_res is not None
            ):
                # Сборка PVT: если pvt передан явно, берем его, иначе собираем из wct и дефолтов
                pvt_obj = self.pvt
                if pvt_obj is None:
                    pvt_obj = PVTDTO(
                        wct=self.wct if self.wct is not None else 50.0,
                        rp=100.0,
                        gamma_oil=0.8,
                        gamma_gas=0.7,
                        gamma_wat=1.0,
                        t_res=self.t_res or 90.0
                    )
                self.vlp = VLPInputDTO(
                    inclinometry=self.inclinometry,
                    casing=self.casing,
                    tubing=self.tubing,
                    pvt=pvt_obj,
                    p_wh=self.p_wh,
                    geo_grad=self.geo_grad,
                    h_res=self.h_res,
                    t_res=self.t_res or pvt_obj.t_res or 90.0,
                    roughness=self.roughness or 0.0001,
                    q_max=self.q_max or 400.0,
                    points=self.points or 21
                )
            else:
                raise ValueError("Не переданы обязательные параметры VLP (inclinometry, casing, tubing, p_wh, etc.)")

        return self


class CurveDataDTO(BaseModel):
    q_liq: List[float]
    p_wf: List[float]


class OperatingPointDTO(BaseModel):
    q_liq: float
    p_wf: float


class MetaInfoDTO(BaseModel):
    calc_time_ms: float
    message: str
    is_physical: bool = True
    warnings: List[str] = Field(default_factory=list)


class CalculateResponse(BaseModel):
    status: str = Field(..., description="'success' или 'no_intersection'")
    ipr: CurveDataDTO
    vlp: CurveDataDTO
    operating_point: Optional[OperatingPointDTO] = None
    meta: MetaInfoDTO


class PresetItem(BaseModel):
    id: str
    name: str
    description: str
    data: Dict[str, Any]
