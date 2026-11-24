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
        text = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        text = "\n".join(", ".join(row) for row in rows)
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

    return {"text": text[:100_000], "sources": sources, "extracted_values": extract_values(text)}


VALUE_RE = re.compile(r"(?im)^\s*([a-zа-я_][\wа-я. ]*?)\s*[:=]\s*(-?\d+(?:[.,]\d+)?)\s*([a-zа-я³/%]+)?")


def parse_message_parameters(text: str) -> dict[str, Any] | None:
    """Parse a JSON object or explicit key/value lines, converting pressure units to atm."""
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and ("ipr" in payload or "vlp" in payload):
            return payload
    except (json.JSONDecodeError, TypeError):
        pass
    values = extract_values(text)
    if not values:
        return None
    aliases = {
        "p_res": ("p_res", "pres", "пластовое_давление"),
        "p_wh": ("p_wh", "устьевое_давление"),
        "pb": ("pb", "давление_насыщения"),
        "wct": ("wct", "обводненность", "обводнённость"),
        "pi": ("pi", "продуктивность"),
        "rp": ("rp", "газовый_фактор"),
        "h_res": ("h_res", "глубина_забоя"),
        "h_mes": ("h_mes", "глубина_спуска"),
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
        picked[field] = {"value": number, "unit": "атм" if field in {"p_res", "p_wh", "pb"} else unit or None}
    if not picked:
        return None
    ipr: dict[str, Any] = {}
    vlp: dict[str, Any] = {}
    pvt: dict[str, Any] = {}
    for key, item in picked.items():
        target = ipr if key in {"p_res", "pb", "wct", "pi"} else vlp if key in {"p_wh", "h_res", "h_mes"} else pvt
        if key == "rp":
            target = pvt
        target[key] = item["value"]
    if pvt:
        vlp["pvt"] = pvt
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
