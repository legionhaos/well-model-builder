"""Safe text extraction for supported engineering input files."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from .guardrails import clean_markdown_text

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SINGLE_DOC_EXTENSIONS = {".txt", ".csv", ".json", ".xlsx", ".docx", ".pdf"}
ALLOWED_EXTENSIONS = SINGLE_DOC_EXTENSIONS | {".zip"}


def _format_table_row(raw_cells: list[Any]) -> str:
    cells = [str(c).strip() for c in raw_cells if c is not None and str(c).strip() != ""]
    if not cells:
        return ""
    if (
        len(cells) >= 2
        and ":" not in cells[0]
        and "=" not in cells[0]
        and cells[0].lower() not in {"параметр", "parameter", "показатель", "key", "name", "наименование"}
    ):
        unit = f" {cells[2]}" if len(cells) >= 3 and re.match(r"^[a-zа-яё³/%°]+$", cells[2], re.I) else ""
        return f"{cells[0]}: {cells[1]}{unit}"
    return "\t".join(cells)


def parse_upload(filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Неподдерживаемый формат файла: {suffix or 'без расширения'}")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Размер файла превышает 10 MiB")
    if not content:
        raise ValueError("Файл пуст")

    if suffix == ".zip":
        wells: list[dict[str, Any]] = []
        sources: list[str] = []
        texts: list[str] = []
        total_uncompressed = 0
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for info in zf.infolist()[:40]:
                if info.is_dir():
                    continue
                inner_path = Path(info.filename)
                if "__MACOSX" in inner_path.parts or any(p.startswith(".") for p in inner_path.parts):
                    continue
                if inner_path.suffix.lower() not in SINGLE_DOC_EXTENSIONS:
                    continue
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_UPLOAD_BYTES * 2:
                    raise ValueError("Суммарный размер файлов в архиве превышает допустимый предел")
                inner_bytes = zf.read(info)
                if not inner_bytes:
                    continue
                try:
                    sub = parse_upload(inner_path.name, inner_bytes)
                except Exception:
                    continue
                sources.extend(f"{inner_path.as_posix()}" if not s.startswith(inner_path.name) else s for s in sub.get("sources", []))
                texts.append(f"[{inner_path.as_posix()}]\n{sub.get('text', '')}")
                if sub.get("parsed_params"):
                    wells.append({
                        "filename": inner_path.as_posix(),
                        "parsed_params": sub["parsed_params"],
                        "extracted_values": sub.get("extracted_values", {}),
                    })
        if not wells and not texts:
            raise ValueError("В архиве не найдено подходящих файлов (.json, .txt, .csv, .xlsx, .docx, .pdf)")
        first_well = wells[0] if wells else {}
        return {
            "text": "\n\n".join(texts)[:100_000],
            "sources": sources,
            "extracted_values": first_well.get("extracted_values", {}),
            "parsed_params": first_well.get("parsed_params"),
            "wells": wells,
        }

    sources: list[str] = []
    if suffix in {".txt", ".json"}:
        text = content.decode("utf-8-sig")
        sources.append(filename)
    elif suffix == ".csv":
        raw_csv = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(raw_csv)))
        lines = [line for line in (_format_table_row(list(row)) for row in rows) if line]
        text = "\n".join(lines)
        sources.extend(f"{filename}:строка {i}" for i in range(1, len(rows) + 1))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        blocks = []
        for sheet in workbook.worksheets:
            sources.append(f"{filename}:лист {sheet.title}")
            sheet_lines = [line for line in (_format_table_row(list(row)) for row in sheet.iter_rows(values_only=True)) if line]
            blocks.append(f"[{sheet.title}]\n" + "\n".join(sheet_lines))
        text = "\n".join(blocks)
    elif suffix == ".docx":
        from docx import Document

        document = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in document.paragraphs)
        sources.append(f"{filename}:документ")
        for index, table in enumerate(document.tables, start=1):
            sources.append(f"{filename}:таблица {index}")
            tbl_lines = [line for line in (_format_table_row([cell.text for cell in row.cells]) for row in table.rows) if line]
            text += "\n" + "\n".join(tbl_lines)
    else:
        text, pdf_sources, ocr_method = _extract_pdf_sync(filename, content)
        sources.extend(pdf_sources)

    parsed_params = parse_message_parameters(text)
    cleaned_text = clean_markdown_text(text[:100_000])
    result_dict: dict[str, Any] = {
        "text": cleaned_text,
        "sources": sources,
        "extracted_values": extract_values(text),
        "parsed_params": parsed_params,
    }
    if suffix == ".pdf":
        result_dict["ocr_method"] = locals().get("ocr_method", "pdf_text")
    return result_dict


def _extract_pdf_sync(filename: str, content: bytes) -> tuple[str, list[str], str]:
    """Extract PDF text via PyMuPDF/pypdf and apply Tesseract OCR to scanned/image pages."""
    sources: list[str] = []
    pages_text: list[str] = []
    method = "pdf_text"

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=content, filetype="pdf")
        for idx, page in enumerate(doc, start=1):
            native_txt = (page.get_text("text") or "").strip()
            has_images = bool(page.get_images(full=False))
            used_ocr = False
            combined_page = native_txt

            # Если страница отсканирована (мало текста) или содержит картинки при малом тексте — запускаем Tesseract
            if (len(native_txt) < 40 or (has_images and len(native_txt) < 120)) and idx <= 8:
                try:
                    import pytesseract
                    from PIL import Image

                    pix = page.get_pixmap(dpi=180)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_txt = pytesseract.image_to_string(img, lang="rus+eng").strip()
                    if ocr_txt:
                        combined_page = f"{native_txt}\n{ocr_txt}".strip() if native_txt else ocr_txt
                        used_ocr = True
                        method = "pdf_text+tesseract_ocr" if native_txt else "tesseract_ocr"
                except Exception:
                    pass

            pages_text.append(combined_page)
            tag = " (Tesseract OCR)" if used_ocr else ""
            sources.append(f"{filename}:страница {idx}{tag}")
        return "\n".join(pages_text), sources, method
    except ImportError:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=True)
        for number, page in enumerate(reader.pages, start=1):
            pages_text.append(page.extract_text() or "")
            sources.append(f"{filename}:страница {number}")
        return "\n".join(pages_text), sources, "pypdf_text"


def render_pdf_page_pngs(content: bytes, *, max_pages: int = 3) -> list[bytes]:
    """Render PDF pages into PNG bytes for multimodal Vision LLM OCR."""
    try:
        import fitz

        doc = fitz.open(stream=content, filetype="pdf")
        pngs: list[bytes] = []
        for idx, page in enumerate(doc):
            if idx >= max_pages:
                break
            pix = page.get_pixmap(dpi=160)
            pngs.append(pix.tobytes("png"))
        return pngs
    except Exception:
        return []


def _merge_partial_params(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any] | None:
    if not extra:
        return base
    if not base:
        return extra
    merged = {
        "ipr": {**(base.get("ipr") or {}), **(extra.get("ipr") or {})},
        "vlp": {**(base.get("vlp") or {})},
    }
    extra_vlp = extra.get("vlp") or {}
    for k, v in extra_vlp.items():
        if isinstance(v, dict) and isinstance(merged["vlp"].get(k), dict):
            merged["vlp"][k] = {**merged["vlp"][k], **v}
        elif v is not None:
            merged["vlp"][k] = v
    return merged


async def parse_upload_smart(
    filename: str,
    content: bytes,
    *,
    llm_overrides: dict[str, Any] | None = None,
    pdf_ocr_mode: str = "auto",
    persist: bool = True,
) -> dict[str, Any]:
    """Enhanced upload parser: PDF Tesseract + optional Multimodal Vision OCR + persistent server save."""
    parsed = parse_upload(filename, content)
    suffix = Path(filename).suffix.lower()
    ocr_method = parsed.pop("ocr_method", "text_parser")

    if suffix == ".pdf":
        parsed_params = parsed.get("parsed_params")
        ipr_keys = len((parsed_params or {}).get("ipr") or {})
        vlp_keys = len((parsed_params or {}).get("vlp") or {})
        needs_vision = pdf_ocr_mode == "vision" or (pdf_ocr_mode == "auto" and (ipr_keys + vlp_keys) < 4)

        if needs_vision:
            from app.enhancements.vision import extract_parameters_from_image

            png_pages = render_pdf_page_pngs(content, max_pages=2)
            for page_idx, png_bytes in enumerate(png_pages, start=1):
                try:
                    vision_res = await extract_parameters_from_image(
                        f"{filename}_page_{page_idx}.png",
                        png_bytes,
                        llm_overrides=llm_overrides,
                        allow_offline_stub=False,
                    )
                    vis_params = vision_res.get("extracted_params")
                    if isinstance(vis_params, dict) and (vis_params.get("ipr") or vis_params.get("vlp")):
                        parsed["parsed_params"] = _merge_partial_params(parsed.get("parsed_params"), vis_params)
                        parsed["sources"].append(f"{filename}:страница {page_idx} (Vision OCR)")
                        ocr_method = f"{ocr_method}+vision_ocr" if ocr_method else "vision_ocr"
                        break
                except Exception:
                    continue

    if persist:
        try:
            from .file_store import save_uploaded_document

            meta = save_uploaded_document(
                filename,
                content,
                extracted_text=parsed.get("text", ""),
                parsed_params=parsed.get("parsed_params"),
                extracted_values=parsed.get("extracted_values"),
                sources=parsed.get("sources"),
                ocr_method=ocr_method,
            )
            parsed["stored_file_id"] = meta.get("id")
        except Exception:
            pass

    parsed["ocr_method"] = ocr_method
    return parsed


VALUE_RE = re.compile(r"(?im)^[ \t]*([a-zа-я_][\wа-я. ]*?)[ \t]*[:=][ \t]*(-?\d+(?:[.,]\d+)?)[ \t]*([a-zа-я³/%°]+)?")
INLINE_VALUE_RE = re.compile(
    r"(?i)(?<![\wа-яё])([a-z][a-z0-9_.]*|пластовое_давление|устьевое_давление|давление_насыщения|обводн[её]нность|продуктивность|газовый_фактор)[ \t]*[:=][ \t]*(-?\d+(?:[.,]\d+)?)[ \t]*([a-zа-я³/%°]+)?"
)
ARRAY_RE = re.compile(r"(?im)^[ \t]*(MD|TVD)[ \t]*[:=][ \t]*\[([^\]]+)\]")


def _extract_embedded_json_dict(text: str) -> dict[str, Any] | None:
    """Find and decode the first JSON object embedded in free-form text or markdown blocks."""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            continue
    return None


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


def contains_explicit_well_payload(text: str) -> bool:
    """Detect whether user message introduces its own well model/JSON rather than modifying form state."""
    embedded = _extract_embedded_json_dict(text)
    if embedded is not None:
        model_keys = {"ipr", "vlp", "p_res", "wct", "pi", "pb", "inclinometry", "casing", "tubing", "pvt", "p_wh", "h_res"}
        if any(k in embedded for k in model_keys):
            return True
    parsed = parse_message_parameters(text)
    if not parsed:
        return False
    lower = text.lower()
    form_modifier_hints = (
        "что если",
        "а если",
        "если помен",
        "если измен",
        "измени ",
        "поменяй ",
        "увеличь",
        "уменьши",
        "подбери",
        "оптимиз",
        "дополни из форм",
        "текущей модели",
    )
    if any(hint in lower for hint in form_modifier_hints):
        return False
    ipr_count = len(parsed.get("ipr") or {})
    vlp_count = len(parsed.get("vlp") or {})
    return (ipr_count + vlp_count) >= 2


def parse_message_parameters(text: str) -> dict[str, Any] | None:
    """Parse a JSON object or explicit key/value lines, converting pressure units to atm."""
    payload = _extract_embedded_json_dict(text)
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
    for pattern in (VALUE_RE, INLINE_VALUE_RE):
        for key, raw, unit in pattern.findall(text):
            normalized = raw.replace(",", ".")
            try:
                value: Any = float(normalized)
            except ValueError:
                continue
            normalized_key = re.sub(r"\s+", "_", key.strip().lower())
            result.setdefault(normalized_key, {"value": value, "unit": unit or None})
    return result
