from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .schemas import IPRRequest, IPRResponse, HealthResponse, ErrorResponse
from .model import calculate_ipr

app = FastAPI(
    title="IPR Calculation Service",
    description="Микросервис расчета индикаторной диаграммы притока (IPR) по методике Composite IPR (Brown, 1984)",
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
            "message": "Ошибка выполнения расчета",
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


@app.get("/ipr/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Проверка статуса здоровья IPR сервиса"""
    return HealthResponse(status="ok", service="ipr")


@app.post("/ipr/calc", response_model=IPRResponse, tags=["Calculation"])
async def calc_ipr(req: IPRRequest):
    """
    Расчет кривой притока IPR.
    """
    try:
        q_liq, p_wf = calculate_ipr(
            p_res=req.p_res,
            wct=req.wct,
            pi=req.pi,
            pb=req.pb,
            points=req.points or 21
        )
        return IPRResponse(q_liq=q_liq, p_wf=p_wf)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ошибка расчета IPR: {str(e)}"
        )
