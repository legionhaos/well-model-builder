"""Improvement 02: Распознавание фото и сканов (Vision/OCR паспортов скважин и таблиц)."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict
import httpx

from app.ai_assistant.llm_client import LLMConfig
from app.ai_assistant.parsers import parse_message_parameters

VISION_PROMPT = """Ты — инженерный модуль оптического распознавания документов (OCR/Vision) системы Well Model Builder.
Твоя задача: найти на предоставленном фото/скане паспорта скважины, журнала исследований или таблицы все физические параметры:
- p_res (пластовое давление, атм)
- wct (обводненность, %)
- pi (коэффициент продуктивности, м3/сут/атм)
- pb (давление насыщения, атм)
- p_wh (буферное/устьевое давление, атм)
- h_res (глубина пласта, м)
- tubing.d (диаметр НКТ, м)
- casing.d (диаметр эксплуатационной колонны, м)
- tubing.h_mes (глубина спуска НКТ, м)
- pvt.rp (газовый фактор, м3/т)
- pvt.t_res (температура пласта, °C)

ВЕРНИ ТОЛЬКО ЧИСТЫЙ JSON-ОБЪЕКТ вида:
{
  "ipr": {"p_res": 200.0, "wct": 50.0, "pi": 1.0, "pb": 150.0},
  "vlp": {
    "p_wh": 10.0,
    "h_res": 1500.0,
    "tubing": {"d": 0.062, "h_mes": 1000.0},
    "casing": {"d": 0.1},
    "pvt": {"wct": 50.0, "rp": 100.0, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90.0}
  }
}
Никакого вводного текста или markdown-блоков, только JSON.
"""


def _prune_nulls(obj: Any) -> Any:
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            pv = _prune_nulls(v)
            if pv is not None and pv != {}:
                cleaned[k] = pv
        return cleaned
    if isinstance(obj, list):
        return [v for v in obj if v is not None]
    return obj


async def extract_parameters_from_image(
    filename: str,
    image_bytes: bytes,
    llm_override: dict[str, str | None] | None = None,
) -> Dict[str, Any]:
    """
    Распознавание параметров скважины с фото или скана документа через мультимодальную модель.
    """
    config = LLMConfig.from_env(llm_override)
    if config.available:
        try:
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            ext = filename.split(".")[-1].lower() if "." in filename else "jpeg"
            mime_type = "image/png" if ext == "png" else "image/webp" if ext == "webp" else "image/jpeg"

            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{b64_img}"},
                            },
                        ],
                    }
                ],
                "temperature": 0.0,
            }

            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(
                    f"{config.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        params = _prune_nulls(json.loads(match.group(0))) or {}
                        return {
                            "status": "success",
                            "method": "multimodal_llm_vision",
                            "filename": filename,
                            "extracted_params": params,
                            "raw_text": content,
                            "sources": [f"{filename}: оптическое распознавание (Vision, {config.model})"],
                        }
        except Exception as exc:
            return {
                "status": "error",
                "method": "multimodal_llm_vision",
                "filename": filename,
                "extracted_params": None,
                "message": f"Ошибка обращения к мультимодальной модели: {exc}",
                "sources": [],
            }

    return {
        "status": "unavailable",
        "method": "none",
        "filename": filename,
        "extracted_params": None,
        "message": "Распознавание изображений требует настроенного API-ключа и мультимодальной модели в настройках.",
        "sources": [],
    }
