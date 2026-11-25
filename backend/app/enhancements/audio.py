"""Improvement 03: Голосовой ввод и транскрибация через Whisper API или мультимодальную модель."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict

import httpx

from app.ai_assistant.llm_client import LLMConfig
from app.ai_assistant.parsers import parse_message_parameters


async def transcribe_audio_file(
    filename: str,
    audio_bytes: bytes,
    llm_override: dict[str, str | None] | None = None,
) -> Dict[str, Any]:
    """
    Транскрибация аудиозаписи инженерного сообщения через /audio/transcriptions (Whisper)
    или мультимодальную LLM (input_audio) без фиктивных заглушек.
    """
    config = LLMConfig.from_env(llm_override)
    transcript_text = ""
    method = "none"

    if config.available:
        headers = {"Authorization": f"Bearer {config.api_key}"}

        # 1. Whisper endpoint на OpenAI-совместимом шлюзе
        try:
            files = {"file": (filename, io.BytesIO(audio_bytes), "audio/wav")}
            data = {"model": "whisper-1", "language": "ru"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{config.base_url.rstrip('/')}/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                )
                if resp.status_code == 200:
                    transcript_text = (resp.json().get("text") or "").strip()
                    if transcript_text:
                        method = "whisper_api"
        except Exception:
            pass

        # 2. Fallback на мультимодальную модель с input_audio
        if not transcript_text:
            try:
                ext = Path(filename).suffix.lstrip(".").lower() or "wav"
                if ext == "oga":
                    ext = "ogg"
                b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
                payload = {
                    "model": config.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Дословно расшифруй это русскоязычное голосовое сообщение инженера. Верни только текст расшифровки без пояснений.",
                                },
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": b64_audio, "format": ext},
                                },
                            ],
                        }
                    ],
                    "temperature": 0.0,
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{config.base_url.rstrip('/')}/chat/completions",
                        headers={**headers, "Content-Type": "application/json"},
                        json=payload,
                    )
                    if resp.status_code == 200:
                        transcript_text = (resp.json()["choices"][0]["message"]["content"] or "").strip()
                        if transcript_text:
                            method = "multimodal_llm_audio"
            except Exception:
                pass

    if not transcript_text:
        return {
            "status": "unavailable",
            "method": method,
            "filename": filename,
            "transcript": "",
            "extracted_parameters": None,
            "message": "Не удалось расшифровать аудио: проверьте API-ключ и поддержку Whisper/аудио у выбранной модели в настройках.",
        }

    params = parse_message_parameters(transcript_text)
    return {
        "status": "success",
        "method": method,
        "filename": filename,
        "transcript": transcript_text,
        "extracted_parameters": params,
    }
