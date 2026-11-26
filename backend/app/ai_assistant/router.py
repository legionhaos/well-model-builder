"""HTTP API for assistant chat (sync + SSE streaming) and smart document upload."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from .agent import run_agent, run_agent_stream
from .llm_client import LLMConfig
from .parsers import contains_explicit_well_payload, parse_message_parameters, parse_upload_smart
from .schemas import ChatRequest, ChatResponse, ChatStatus, LLMRuntimeConfig, UploadResponse
from .tools import validate_well_params

router = APIRouter(prefix="/api/chat", tags=["ai-assistant"])
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def extract_llm_overrides(request: Request, body_cfg: LLMRuntimeConfig | None = None) -> dict[str, Any]:
    """Merge UI-configured LLM/Audio/OCR overrides from request body and X-LLM-* headers."""
    overrides: dict[str, Any] = {}
    if body_cfg is not None:
        for key, value in body_cfg.model_dump(exclude_none=True).items():
            if isinstance(value, str):
                value = value.strip()
            if value:
                overrides[key] = value
    header_map = {
        "x-llm-api-key": "api_key",
        "x-llm-base-url": "base_url",
        "x-llm-model": "model",
        "x-audio-mode": "audio_mode",
        "x-pdf-ocr-mode": "pdf_ocr_mode",
    }
    for header_name, key in header_map.items():
        val = (request.headers.get(header_name) or "").strip()
        if val and key not in overrides:
            overrides[key] = val
    return overrides


async def _calculate(params: dict[str, Any]) -> dict[str, Any]:
    """Call public orchestrator /api/calculate so physical engine stays single source of truth."""
    base_url = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8080").rstrip("/")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{base_url}/api/calculate", json=params)
        response.raise_for_status()
        return response.json()


def _early_validation_error(
    validation: dict[str, Any] | None,
    llm_available: bool,
) -> str | None:
    if validation is None or validation.get("valid"):
        return None
    missing = validation.get("missing") or []
    errors = validation.get("errors") or []
    if missing:
        return (
            "Не хватает обязательных данных или обнаружены противоречия. "
            "Без вашего согласия значения не подставляю.\n"
            f"Уточните параметры: {'; '.join(missing + errors)}"
        )
    if errors and not llm_available:
        return "ВНИМАНИЕ — физическая ошибка входных параметров: " + "; ".join(errors)
    return None


def _resolve_chat_params(request_params: dict[str, Any] | None, message: str) -> dict[str, Any] | None:
    msg_params = parse_message_parameters(message)
    if msg_params is not None and contains_explicit_well_payload(message):
        return msg_params
    return request_params or msg_params


@router.get("/status", response_model=ChatStatus)
async def chat_status(http_request: Request) -> ChatStatus:
    overrides = extract_llm_overrides(http_request)
    config = LLMConfig.from_env(overrides=overrides)
    if not config.available:
        return ChatStatus(
            available=False,
            message="ИИ-ассистент не настроен: укажите API Key, Base URL и модель в «Настройки» или в `.env`.",
        )
    return ChatStatus(available=True, message=f"Активна модель: {config.model}")


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse | dict[str, Any]:
    overrides = extract_llm_overrides(http_request, request.llm_config)
    config = LLMConfig.from_env(overrides=overrides)
    params = _resolve_chat_params(request.params, request.message)
    validation = validate_well_params(params) if params is not None else None
    early_err = _early_validation_error(validation, config.available)
    if early_err:
        return ChatResponse(
            available=config.available,
            text=early_err,
            session_id=request.session_id or str(uuid.uuid4()),
            tool_trace=[],
            calculation_result={"validation": validation, "operating_point": None},
        )
    return await run_agent(
        request.message,
        params=params,
        calculate=_calculate,
        session_id=request.session_id,
        llm_overrides=overrides,
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint streaming thinking status, tool executions, and tokens."""
    overrides = extract_llm_overrides(http_request, request.llm_config)
    config = LLMConfig.from_env(overrides=overrides)
    params = _resolve_chat_params(request.params, request.message)
    validation = validate_well_params(params) if params is not None else None
    early_err = _early_validation_error(validation, config.available)
    session_id = request.session_id or str(uuid.uuid4())

    async def event_generator():
        if early_err:
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'delta', 'delta': early_err}, ensure_ascii=False)}\n\n"
            done_payload = {
                "type": "done",
                "available": config.available,
                "text": early_err,
                "session_id": session_id,
                "tool_trace": [],
                "calculation_result": {"validation": validation, "operating_point": None},
                "params": None,
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False, default=str)}\n\n"
            return

        async for event in run_agent_stream(
            request.message,
            params=params,
            calculate=_calculate,
            session_id=session_id,
            llm_overrides=overrides,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/upload", response_model=UploadResponse)
async def upload(http_request: Request, file: UploadFile = File(...)) -> UploadResponse:
    overrides = extract_llm_overrides(http_request)
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if not content:
            raise ValueError("Передан пустой файл")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Файл превышает 25 МБ")
        parsed = await parse_upload_smart(
            file.filename or "upload.txt",
            content,
            llm_overrides=overrides,
            pdf_ocr_mode=str(overrides.get("pdf_ocr_mode", "auto")),
            persist=True,
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Не удалось разобрать файл: {exc}") from exc
    return UploadResponse(filename=file.filename or "upload.txt", **parsed)


@router.post("/upload/calculate")
async def upload_and_calculate(http_request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """Extract explicitly provided parameters and calculate; missing fields are never guessed."""
    overrides = extract_llm_overrides(http_request)
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if not content:
            raise ValueError("Передан пустой файл")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Файл превышает 25 МБ")
        parsed = await parse_upload_smart(
            file.filename or "upload.txt",
            content,
            llm_overrides=overrides,
            pdf_ocr_mode=str(overrides.get("pdf_ocr_mode", "auto")),
            persist=True,
        )
        params = parsed.get("parsed_params") or parse_message_parameters(parsed["text"])
        if params is None:
            raise ValueError("Не удалось извлечь явные параметры из файла")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await run_agent(
        f"Рассчитай модель по явно указанным данным из файла {file.filename}",
        params=params,
        calculate=_calculate,
        llm_overrides=overrides,
    )
    result["sources"] = parsed["sources"]
    result["extracted_values"] = parsed["extracted_values"]
    result["stored_file_id"] = parsed.get("stored_file_id")
    result["ocr_method"] = parsed.get("ocr_method")
    return result
