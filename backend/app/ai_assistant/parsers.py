"""Safe text extraction for supported engineering input files."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".csv", ".json", ".xlsx", ".docx", ".pdf"}


def parse_upload(filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Неподдерживаемый формат файла: {suffix or 'без расширения'}")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Размер файла превышает 10 MiB")
    if not content:
        raise ValueError("Файл пуст")

    sources: list[str] = []
    if suffix in {".txt", ".json"}:
        text = content.decode("utf-8-sig")
        sources.append(filename)
    elif suffix == ".csv":
        raw_csv = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(raw_csv)))
        lines: list[str] = []
        for row in rows:
            cells = [c.strip() for c in row if c is not None and c.strip() != ""]
            if len(cells) >= 2 and cells[0].lower() not in {"параметр", "parameter", "key", "name"}:
                unit = f" {cells[2]}" if len(cells) >= 3 else ""
                lines.append(f"{cells[0]}: {cells[1]}{unit}")
            elif cells:
                lines.append(", ".join(cells))
        text = "\n".join(lines)
        sources.extend(f"{filename}:строка {i}" for i in range(1, len(rows) + 1))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        blocks = []
        for sheet in workbook.worksheets:
            sources.append(f"{filename}:лист {sheet.title}")
            blocks.append(f"[{sheet.title}]\n" + "\n".join("\t".join("" if v is None else str(v) for v in row) for row in sheet.iter_rows(values_only=True)))
        text = "\n".join(blocks)
    elif suffix == ".docx":
        from docx import Document

        document = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in document.paragraphs)
        sources.append(f"{filename}:документ")
        for index, table in enumerate(document.tables, start=1):
            sources.append(f"{filename}:таблица {index}")
            text += "\n" + "\n".join("\t".join(cell.text for cell in row.cells) for row in table.rows)
    else:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=True)
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            pages.append(page.extract_text() or "")
            sources.append(f"{filename}:страница {number}")
        text = "\n".join(pages)

    parsed_params = parse_message_parameters(text)
    return {
        "text": text[:100_000],
        "sources": sources,
        "extracted_values": extract_values(text),
        "parsed_params": parsed_params,
    }


def _merge_param_dicts(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _merge_param_dicts(merged[k], v)
        elif v is not None:
            merged[k] = v
    return merged


async def parse_upload_with_vision(
    filename: str,
    content: bytes,
    llm_override: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Parse uploaded file and, for PDFs with sparse/empty text, OCR embedded images via multimodal Vision."""
    result = parse_upload(filename, content)
    suffix = Path(filename).suffix.lower()
    if suffix != ".pdf":
        return result

    has_params = bool(result.get("parsed_params"))
    text_len = len((result.get("text") or "").strip())
    if has_params and text_len >= 40:
        return result

    try:
        from pypdf import PdfReader
        from app.enhancements.vision import extract_parameters_from_image

        reader = PdfReader(io.BytesIO(content), strict=False)
        merged_params: dict[str, Any] = dict(result.get("parsed_params") or {})
        extra_texts: list[str] = []
        extra_sources: list[str] = []
        processed = 0

        for page_num, page in enumerate(reader.pages, start=1):
            images = getattr(page, "images", None) or []
            for img_idx, img in enumerate(images, start=1):
                img_bytes = getattr(img, "data", b"") or b""
                if len(img_bytes) < 1024:
                    continue
                img_name = getattr(img, "name", None) or f"page_{page_num}_img_{img_idx}.png"
                vision_res = await extract_parameters_from_image(img_name, img_bytes, llm_override=llm_override)
                processed += 1
                if vision_res.get("extracted_params"):
                    merged_params = _merge_param_dicts(merged_params, vision_res["extracted_params"])
                    extra_sources.append(f"{filename}:страница {page_num} (Vision: {img_name})")
                if vision_res.get("raw_text"):
                    extra_texts.append(f"[Страница {page_num}, изображение {img_name}]\n{vision_res['raw_text']}")
                if processed >= 3:
                    break
            if processed >= 3:
                break

        if merged_params:
            result["parsed_params"] = merged_params
        if extra_sources:
            result["sources"] = [*result.get("sources", []), *extra_sources]
        if extra_texts:
            combined_text = "\n\n".join(filter(None, [result.get("text", ""), *extra_texts]))
            result["text"] = combined_text[:100_000]
            if not result.get("extracted_values"):
                result["extracted_values"] = extract_values(combined_text)
    except Exception:
        pass

    return result


VALUE_RE = re.compile(r"(?im)^\s*([a-zа-я_][\wа-я. ]*?)\s*[:=]\s*(-?\d+(?:[.,]\d+)?)\s*([a-zа-я³/%°]+)?")
ARRAY_RE = re.compile(r"(?im)^\s*(MD|TVD)\s*[:=]\s*\[([^\]]+)\]")


def _extract_inclinometry(text: str) -> dict[str, list[float]] | None:
    inc: dict[str, list[float]] = {}
    for key, raw_list in ARRAY_RE.findall(text):
        nums: list[float] = []
        for item in raw_list.split(","):
            try:
                nums.append(float(item.strip().replace(",", ".")))
            except ValueError:
                pass
        if nums:
            inc[key.upper()] = nums
    return inc if "MD" in inc and "TVD" in inc else None


def parse_message_parameters(text: str) -> dict[str, Any] | None:
    """Parse a JSON object or explicit key/value lines, converting pressure units to atm."""
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            if "ipr" in payload or "vlp" in payload:
                return payload
            vlp_keys = {"inclinometry", "casing", "tubing", "pvt", "p_wh", "geo_grad", "h_res", "t_res", "roughness", "q_max"}
            ipr_keys = {"p_res", "pi", "pb", "wct"}
            has_vlp = any(k in payload for k in vlp_keys)
            has_ipr = any(k in payload for k in ipr_keys - {"wct"})
            if has_vlp and not has_ipr:
                return {"vlp": payload}
            if has_ipr and not has_vlp:
                return {"ipr": payload}
            if has_ipr and has_vlp:
                ipr_part = {k: payload[k] for k in ipr_keys if k in payload}
                vlp_part = {k: v for k, v in payload.items() if k not in (ipr_keys - {"wct"})}
                return {"ipr": ipr_part, "vlp": vlp_part}
    except (json.JSONDecodeError, TypeError):
        pass
    values = extract_values(text)
    inclinometry = _extract_inclinometry(text)
    if not values and not inclinometry:
        return None
    aliases = {
        "p_res": ("p_res", "pres", "пластовое_давление", "ipr.p_res"),
        "p_wh": ("p_wh", "устьевое_давление", "буферное_давление", "vlp.p_wh"),
        "pb": ("pb", "давление_насыщения", "ipr.pb"),
        "wct": ("wct", "обводненность", "обводнённость", "ipr.wct", "pvt.wct"),
        "pi": ("pi", "продуктивность", "коэффициент_продуктивности", "ipr.pi"),
        "rp": ("rp", "газовый_фактор", "pvt.rp"),
        "h_res": ("h_res", "глубина_забоя", "глубина_пласта", "vlp.h_res"),
        "h_mes": ("h_mes", "глубина_спуска", "спуск_нкт", "tubing.h_mes"),
        "tubing_d": ("tubing.d", "tubing_d", "диаметр_нкт"),
        "casing_d": ("casing.d", "casing_d", "диаметр_эк"),
        "gamma_oil": ("pvt.gamma_oil", "gamma_oil", "плотность_нефти"),
        "gamma_gas": ("pvt.gamma_gas", "gamma_gas", "плотность_газа"),
        "gamma_wat": ("pvt.gamma_wat", "gamma_wat", "плотность_воды"),
        "t_res": ("pvt.t_res", "t_res", "температура_пласта", "температура"),
        "geo_grad": ("geo_grad", "геотермический_градиент", "vlp.geo_grad"),
    }
    picked: dict[str, dict[str, Any]] = {}
    for field, names in aliases.items():
        item = next((values[name] for name in names if name in values), None)
        if item is None:
            continue
        number, unit = item["value"], (item["unit"] or "").lower()
        if field in {"p_res", "p_wh", "pb"}:
            if unit in {"mpa", "мпа"}:
                number *= 9.869232667
            elif unit in {"bar", "бар"}:
                number *= 0.986923267
            elif unit in {"kpa", "кпа"}:
                number *= 0.00986923267
            elif unit and unit not in {"атм", "atm"}:
                continue
        elif field in {"tubing_d", "casing_d"}:
            if unit in {"mm", "мм"} or number > 1.0:
                number /= 1000.0
        picked[field] = {"value": number, "unit": "атм" if field in {"p_res", "p_wh", "pb"} else unit or None}
    if not picked and not inclinometry:
        return None
    ipr: dict[str, Any] = {}
    vlp: dict[str, Any] = {}
    pvt: dict[str, Any] = {}
    tubing: dict[str, Any] = {}
    casing: dict[str, Any] = {}
    for key, item in picked.items():
        val = item["value"]
        if key in {"p_res", "pb", "wct", "pi"}:
            ipr[key] = val
            if key == "wct":
                pvt["wct"] = val
        elif key in {"p_wh", "h_res", "geo_grad"}:
            vlp[key] = val
        elif key == "h_mes":
            tubing["h_mes"] = val
        elif key == "tubing_d":
            tubing["d"] = val
        elif key == "casing_d":
            casing["d"] = val
        else:
            pvt[key] = val
    if tubing:
        vlp["tubing"] = tubing
    if casing:
        vlp["casing"] = casing
    if pvt:
        vlp["pvt"] = pvt
    if inclinometry:
        vlp["inclinometry"] = inclinometry
    return {"ipr": ipr, "vlp": vlp}


def extract_values(text: str) -> dict[str, Any]:
    """Extract explicit key/value pairs only; never infer missing values."""
    result: dict[str, Any] = {}
    for key, raw, unit in VALUE_RE.findall(text):
        normalized = raw.replace(",", ".")
        try:
            value: Any = float(normalized)
        except ValueError:
            continue
        normalized_key = re.sub(r"\s+", "_", key.strip().lower())
        result[normalized_key] = {"value": value, "unit": unit or None}
    return result
