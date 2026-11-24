from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .schemas import VLPRequest, VLPResponse, HealthResponse, ErrorResponse
from .pvt import BlackOilPVT
from .model import calculate_vlp

app = FastAPI(
    title="VLP Calculation Service",
    description="Микросервис расчета кривой вертикального подъема жидкости (VLP) со встроенным Black-Oil PVT",
    version="3.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_err = errors[0] if errors else {}
    msg = first_err.get("msg", "Ошибка валидации входных данных")
    loc = " -> ".join(str(l) for l in first_err.get("loc", []))
    description = f"{loc}: {msg}" if loc else msg
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "message": "Ошибка валидации",
            "description": description,
            "detail": description
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = str(exc.detail) if exc.detail else "Ошибка обработки запроса"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "message": "Ошибка расчета VLP",
            "description": detail,
            "detail": detail
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "message": "Некорректный запрос",
            "description": str(exc),
            "detail": str(exc)
        }
    )


@app.get("/vlp/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Проверка статуса здоровья VLP сервиса"""
    return HealthResponse(status="ok", service="vlp")


@app.post("/vlp/calc", response_model=VLPResponse, tags=["Calculation"])
async def calc_vlp(req: VLPRequest):
    """
    Расчет кривой подъема VLP.
    """
    try:
        pvt = BlackOilPVT(
            wct=req.pvt.wct,
            rp_m3_t=req.pvt.rp,
            gamma_oil=req.pvt.gamma_oil,
            gamma_gas=req.pvt.gamma_gas,
            gamma_wat=req.pvt.gamma_wat
        )

        resolved_t_res = req.get_resolved_t_res()

        q_liq, p_wf = calculate_vlp(
            md_list=req.inclinometry.MD,
            tvd_list=req.inclinometry.TVD,
            casing_d=req.casing.d,
            tubing_d=req.tubing.d,
            tubing_h_mes=req.tubing.h_mes,
            pvt=pvt,
            p_wh=req.p_wh,
            geo_grad=req.geo_grad,
            h_res=req.h_res,
            t_res=resolved_t_res,
            roughness=req.roughness or 0.0001,
            q_max=req.q_max or 400.0,
            points=req.points or 21
        )

        return VLPResponse(q_liq=q_liq, p_wf=p_wf)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ошибка численного интегрирования VLP: {str(e)}"
        )
