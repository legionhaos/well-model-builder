"""Improvement 02: Распознавание фото и сканов (Vision/OCR паспортов скважин и таблиц)."""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict
import httpx

from app.config import settings
from app.ai_assistant.parsers import parse_message_parameters

VISION_PROMPT = """Ты — инженерный модуль оптического распознавания документов (OCR/Vision) системы Well Model Builder.
Твоя задача: найти на предоставленном фото/скане паспорта скважины, журнала исследований или таблицы ТОЛЬКО реально присутствующие на изображении физические параметры нефтяной/газовой скважины:
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

СТРОГИЕ ПРАВИЛА:
1. Если на изображении НЕТ данных о нефтяной скважине (например, посторонний слайд, школьный текст, мем, пустой лист или параметры неразличимы) — ВЕРНИ СТРОГО `{}`.
2. ЗАПРЕЩЕНО придумывать значения или додумывать отсутствующие поля; включай только те ключи, числа для которых явно видны на изображении.

Формат ответа (только чистый JSON без markdown-обёрток):
{
  "ipr": {"p_res": "<число>", "wct": "<число>", "pi": "<число>", "pb": "<число>"},
  "vlp": {
    "p_wh": "<число>",
    "h_res": "<число>",
    "tubing": {"d": "<число>", "h_mes": "<число>"},
    "casing": {"d": "<число>"},
    "pvt": {"wct": "<число>", "rp": "<число>", "t_res": "<число>"}
  }
}
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


def _has_numeric_well_fields(params: Any) -> bool:
    if not isinstance(params, dict):
        return False
    for section_key in ("ipr", "vlp"):
        sec = params.get(section_key)
        if not isinstance(sec, dict):
            continue
        for val in sec.values():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                return True
            if isinstance(val, dict) and any(isinstance(sub, (int, float)) and not isinstance(sub, bool) for sub in val.values()):
                return True
    return False


async def extract_parameters_from_image(
    filename: str,
    image_bytes: bytes,
    *,
    llm_overrides: Dict[str, Any] | None = None,
    allow_offline_stub: bool = False,
) -> Dict[str, Any]:
    """
    Распознавание параметров скважины с фото или скана документа через Vision LLM и/или Tesseract OCR.
    Никогда не подменяет нераспознанную или постороннюю картинку фиктивными параметрами.
    """
    _ = allow_offline_stub  # Параметр оставлен для обратной совместимости сигнатуры
    ov = llm_overrides or {}
    api_key = str(ov.get("api_key") or settings.llm_api_key or "").strip()
    base_url = str(ov.get("base_url") or settings.llm_base_url or "https://api.deepseek.com/v1").strip()
    model = str(ov.get("model") or settings.llm_model or "deepseek-flash").strip()

    vision_error: str | None = None

    # 1. Если настроен LLM-шлюз, отправляем как multimodal Vision запрос
    if api_key:
        try:
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            ext = filename.split(".")[-1].lower() if "." in filename else "jpeg"
            mime_type = "image/png" if ext == "png" else "image/webp" if ext == "webp" else "image/jpeg"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
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

            async with httpx.AsyncClient(timeout=18.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        params = _prune_nulls(json.loads(match.group(0))) or {}
                        if _has_numeric_well_fields(params):
                            return {
                                "status": "success",
                                "method": "multimodal_llm_vision",
                                "filename": filename,
                                "extracted_params": params,
                                "raw_text": content,
                                "sources": [f"{filename}: оптическое распознавание (Vision, {model})"],
                            }
                else:
                    vision_error = f"HTTP {resp.status_code}"
        except Exception as exc:
            vision_error = str(exc)

    # 2. Автономный режим через Tesseract OCR (rus+eng)
    ocr_text = ""
    try:
        import io
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        ocr_text = pytesseract.image_to_string(img, lang="rus+eng").strip()
        if ocr_text:
            ocr_params = parse_message_parameters(ocr_text)
            if _has_numeric_well_fields(ocr_params):
                return {
                    "status": "success",
                    "method": "tesseract_ocr",
                    "filename": filename,
                    "extracted_params": ocr_params,
                    "raw_text": ocr_text[:4000],
                    "sources": [f"{filename}: Tesseract OCR (rus+eng)"],
                }
    except Exception:
        pass

    # 3. Честный отказ без вымышленного шаблона well_01
    if ocr_text:
        snippet = " ".join(ocr_text.split())[:220]
        msg = f"На изображении «{filename}» параметры скважины не найдены. Распознанный текст: «{snippet}»."
        status_label = "not_found"
    elif api_key:
        detail = f" (Vision-запрос вернул {vision_error})" if vision_error else ""
        msg = f"На изображении «{filename}» не удалось обнаружить параметры скважины{detail}."
        status_label = "not_found"
    else:
        msg = f"На изображении «{filename}» параметры скважины не обнаружены (Tesseract OCR не нашёл полей, а ключ Vision LLM не настроен)."
        status_label = "unavailable"

    return {
        "status": status_label,
        "method": "tesseract_ocr" if ocr_text else "none",
        "filename": filename,
        "extracted_params": {},
        "raw_text": ocr_text[:4000],
        "message": msg,
        "sources": [],
    }
