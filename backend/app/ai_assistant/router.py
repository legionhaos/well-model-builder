from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.config import settings

router = APIRouter(prefix="/api/chat", tags=["AI Assistant"])


class ChatStatusResponse(BaseModel):
    available: bool
    model: str
    message: str


class SimpleChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"


class SimpleChatResponse(BaseModel):
    text: str
    available: bool
    tool_trace: list = []
    calculation_result: Optional[Dict[str, Any]] = None


@router.get("/status", response_model=ChatStatusResponse)
async def get_chat_status():
    """
    Проверка доступности модуля ИИ-ассистента.
    """
    if settings.is_llm_enabled:
        return ChatStatusResponse(
            available=True,
            model=settings.llm_model,
            message="ИИ-ассистент готов к работе"
        )
    return ChatStatusResponse(
        available=False,
        model=settings.llm_model,
        message="ИИ-ассистент работает в автономном режиме без LLM-ключа (ручной расчет активен)"
    )


@router.post("", response_model=SimpleChatResponse)
async def chat_stub(req: SimpleChatRequest):
    """
    Заглушка чата для автономного режима (до полной реализации Роли 3).
    """
    if not settings.is_llm_enabled:
        return SimpleChatResponse(
            text="ИИ-ассистент работает в автономном режиме без внешнего ключа LLM. Вы можете загрузить эталонные данные well_01 или ввести параметры вручную.",
            available=False
        )
    return SimpleChatResponse(
        text="Модуль ИИ-ассистента подключен. Каркас готов к реализации расширенного tool calling (Роль 3).",
        available=True
    )
