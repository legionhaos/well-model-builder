from typing import List
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .schemas import NodalRequest, NodalPoint, HealthResponse, ErrorResponse
from .solver import solve_nodal_intersection

app = FastAPI(
    title="Nodal Analysis Service",
    description="Микросервис узлового анализа для нахождения рабочей точки пересечения кривых IPR и VLP",
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
            "message": "Ошибка узлового анализа",
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


@app.get("/nodal/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Проверка статуса здоровья Nodal сервиса"""
    return HealthResponse(status="ok", service="nodal")


@app.post("/nodal/calc", response_model=List[NodalPoint], tags=["Calculation"])
async def calc_nodal(req: NodalRequest):
    """
    Расчет рабочей точки узлового анализа (пересечение IPR и VLP).
    Возвращает массив ровно из одного элемента [ {q_liq, p_wf} ].
    Если пересечение отсутствует, возвращает структурированную ошибку 422 JSON.
    """
    points = solve_nodal_intersection(
        ipr_q=req.ipr.q_liq,
        ipr_p=req.ipr.p_wf,
        vlp_q=req.vlp.q_liq,
        vlp_p=req.vlp.p_wf
    )

    if not points:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Точка пересечения кривых IPR и VLP не найдена в заданном диапазоне"
        )

    # По ТЗ multi-intersection не тестируется, берем первую точку
    q_res, p_res = points[0]

    return [
        NodalPoint(
            q_liq=round(q_res, 2),
            p_wf=round(p_res, 2)
        )
    ]
