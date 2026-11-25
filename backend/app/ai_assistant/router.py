"""HTTP API for optional assistant features, streaming, and stored files."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .agent import run_agent, run_agent_stream
from .llm_client import LLMConfig
from .parsers import parse_message_parameters, parse_upload, parse_upload_with_vision
from .schemas import ChatRequest, ChatResponse, ChatStatus, UploadResponse
from .storage import list_server_files, read_server_file, save_uploaded_file
from .tools import validate_well_params

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


def _extract_llm_override(
    body_cfg: Any = None,
    x_llm_base_url: str | None = None,
    x_llm_model: str | None = None,
    x_llm_api_key: str | None = None,
) -> dict[str, str | None] | None:
    cfg: dict[str, str | None] = {}
    if body_cfg is not None:
        cfg["base_url"] = getattr(body_cfg, "base_url", None)
        cfg["model"] = getattr(body_cfg, "model", None)
        cfg["api_key"] = getattr(body_cfg, "api_key", None)
    if x_llm_base_url:
        cfg["base_url"] = x_llm_base_url
    if x_llm_model:
        cfg["model"] = x_llm_model
    if x_llm_api_key:
        cfg["api_key"] = x_llm_api_key
    return cfg if any(v and str(v).strip() for v in cfg.values()) else None


@router.get("/status", response_model=ChatStatus)
async def chat_status(
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
):
    override = _extract_llm_override(None, x_llm_base_url, x_llm_model, x_llm_api_key)
    config = LLMConfig.from_env(override)
    if not config.available:
        return ChatStatus(available=False, message="ИИ-ассистент не настроен (отсутствует ключ LLM)")
    return ChatStatus(available=True)


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
):
    override = _extract_llm_override(request.llm_config, x_llm_base_url, x_llm_model, x_llm_api_key)
    params = request.params or parse_message_parameters(request.message)
    validation = validate_well_params(params) if params is not None else None
    if validation is not None and not validation["valid"]:
        return ChatResponse(
            available=LLMConfig.from_env(override).available,
            text="Не хватает обязательных данных или есть противоречия. Уточните параметры: "
            + "; ".join(validation["missing"] + validation["errors"]),
            session_id=request.session_id or str(uuid.uuid4()),
            tool_trace=[],
            calculation_result={"validation": validation, "operating_point": None},
        )
    return await run_agent(
        request.message,
        params=params,
        calculate=_calculate,
        session_id=request.session_id,
        llm_override=override,
    )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
):
    override = _extract_llm_override(request.llm_config, x_llm_base_url, x_llm_model, x_llm_api_key)
    params = request.params or parse_message_parameters(request.message)
    validation = validate_well_params(params) if params is not None else None

    async def event_generator():
        if validation is not None and not validation["valid"]:
            payload = {
                "type": "done",
                "available": LLMConfig.from_env(override).available,
                "text": "Не хватает обязательных данных или есть противоречия. Уточните параметры: "
                + "; ".join(validation["missing"] + validation["errors"]),
                "session_id": request.session_id or str(uuid.uuid4()),
                "tool_trace": [],
                "calculation_result": {"validation": validation, "operating_point": None},
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            return

        async for event in run_agent_stream(
            request.message,
            params=params,
            calculate=_calculate,
            session_id=request.session_id,
            llm_override=override,
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
async def upload(
    file: UploadFile = File(...),
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
):
    override = _extract_llm_override(None, x_llm_base_url, x_llm_model, x_llm_api_key)
    filename = file.filename or "upload.txt"
    try:
        content = await file.read(10 * 1024 * 1024 + 1)
        parsed = await parse_upload_with_vision(filename, content, llm_override=override)
        save_uploaded_file(filename, content, parsed)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Не удалось разобрать файл: {exc}") from exc
    return UploadResponse(filename=filename, **parsed)


@router.post("/upload/calculate")
async def upload_and_calculate(
    file: UploadFile = File(...),
    x_llm_base_url: str | None = Header(default=None),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
):
    """Extract explicitly provided parameters and calculate; missing fields are never guessed."""
    override = _extract_llm_override(None, x_llm_base_url, x_llm_model, x_llm_api_key)
    filename = file.filename or "upload.txt"
    try:
        content = await file.read(10 * 1024 * 1024 + 1)
        parsed = await parse_upload_with_vision(filename, content, llm_override=override)
        save_uploaded_file(filename, content, parsed)
        params = parsed.get("parsed_params") or parse_message_parameters(parsed["text"])
        if params is None:
            raise ValueError("Не удалось извлечь явные параметры из файла")
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await run_agent(
        f"Рассчитай модель по явно указанным данным из файла {filename}",
        params=params,
        calculate=_calculate,
        llm_override=override,
    )
    result["sources"] = parsed["sources"]
    result["extracted_values"] = parsed["extracted_values"]
    return result


@router.get("/files")
async def get_server_files():
    """Список сохранённых загруженных файлов и эталонных файлов samples на сервере."""
    return {"files": list_server_files()}


@router.get("/files/{folder}/{name:path}")
async def get_server_file_details(folder: str, name: str):
    """Чтение извлечённых данных сохранённого файла на сервере."""
    try:
        return read_server_file(name, folder=folder)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
