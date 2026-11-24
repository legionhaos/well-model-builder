from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.orchestrator.client import calc_client
from app.orchestrator.router import router as orchestrator_router
from app.ai_assistant.router import router as chat_router
from app.enhancements.router import router as enhancements_router

app = FastAPI(
    title="Well Model Builder - Backend Orchestrator",
    description="Оркестратор микросервисов узлового анализа и шлюз прикладного слоя (Роль 2)",
    version="3.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

# Настройка CORS для фронтенда (порт 3000)
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
            "message": "Ошибка выполнения запроса",
            "description": detail,
            "detail": detail
        }
    )


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Проверка здоровья бэкенда и доступности всех зависимых микросервисов.
    """
    deps = await calc_client.check_dependencies()
    return {
        "status": "ok",
        "service": "backend",
        "dependencies": deps,
        "ai_enabled": settings.is_llm_enabled
    }


# Подключение роутеров
app.include_router(orchestrator_router)
app.include_router(chat_router)
app.include_router(enhancements_router)
