"""HTTP API for optional assistant features."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from .agent import run_agent
from .llm_client import LLMConfig
from .parsers import parse_message_parameters, parse_upload
from .schemas import ChatRequest, ChatResponse, ChatStatus, UploadResponse
from .tools import calculate_well_model, validate_well_params

router = APIRouter(prefix="/api/chat", tags=["ai-assistant"])


async def _calculate(params):
    # Go through the public orchestrator contract; the calculation engine stays authoritative.
    import os

    import httpx

    base_url = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8080").rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{base_url}/api/calculate", json=params)
        response.raise_for_status()
        return response.json()

@router.get("/status", response_model=ChatStatus)
async def chat_status():
    config = LLMConfig.from_env()
    if not config.available:
        return ChatStatus(available=False, message="ИИ-ассистент не настроен (отсутствует ключ LLM)")
    return ChatStatus(available=True)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    params = request.params or parse_message_parameters(request.message)
    validation = validate_well_params(params) if params is not None else None
    if validation is not None and not validation["valid"]:
        # Don't ask an LLM to fill missing engineering inputs; report them directly.
        return ChatResponse(
            available=LLMConfig.from_env().available,
            text="Не хватает обязательных данных или есть противоречия. Уточните параметры: "
            + "; ".join(validation["missing"] + validation["errors"]),
            session_id=request.session_id or str(uuid.uuid4()),
            tool_trace=[],
            calculation_result={"validation": validation, "operating_point": None},
        )
    return await run_agent(request.message, params=params, calculate=_calculate, session_id=request.session_id)


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    try:
        content = await file.read(10 * 1024 * 1024 + 1)
        parsed = parse_upload(file.filename or "upload.txt", content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Не удалось разобрать файл: {exc}") from exc
    return UploadResponse(filename=file.filename or "upload.txt", **parsed)


@router.post("/upload/calculate")
async def upload_and_calculate(file: UploadFile = File(...)):
    """Extract explicitly provided parameters and calculate; missing fields are never guessed."""
    try:
        content = await file.read(10 * 1024 * 1024 + 1)
        parsed = parse_upload(file.filename or "upload.txt", content)
        params = parse_message_parameters(parsed["text"])
        if params is None:
            raise ValueError("Не удалось извлечь явные параметры из файла")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await run_agent(
        f"Рассчитай модель по явно указанным данным из файла {file.filename}",
        params=params,
        calculate=_calculate,
    )
    result["sources"] = parsed["sources"]
    result["extracted_values"] = parsed["extracted_values"]
    return result
