"""Improvement 06: Поиск файлов в указанной папке (Автоматическое сканирование и индексация скважин)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from app.ai_assistant.parsers import parse_upload, parse_message_parameters
from app.ai_assistant.tools import validate_well_params

ALLOWED_EXTENSIONS = {".txt", ".csv", ".json", ".xlsx", ".docx", ".pdf"}


def scan_directory_for_wells(
    target_path: str = "samples",
    recursive: bool = True
) -> Dict[str, Any]:
    """
    Сканирует локальную папку на сервере, находит все файлы паспортов/таблиц,
    извлекает параметры скважин и проверяет их готовность к расчету.
    """
    path = Path(target_path)
    if not path.is_absolute():
        # Если путь относительный, отсчитываем от корня проекта
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        path = repo_root / target_path

    if not path.exists():
        return {
            "status": "error",
            "message": f"Папка не найдена: {path}",
            "scanned_directory": str(path),
            "wells": []
        }

    pattern = "**/*" if recursive else "*"
    found_wells: List[Dict[str, Any]] = []

    for file_path in path.glob(pattern):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        try:
            content = file_path.read_bytes()
            parsed = parse_upload(file_path.name, content)
            params = parse_message_parameters(parsed.get("text", ""))

            validation = validate_well_params(params) if params else {"valid": False, "missing": ["все параметры"], "errors": []}

            well_name = file_path.stem.replace("_", " ").title()

            found_wells.append({
                "filename": file_path.name,
                "relative_path": str(file_path.relative_to(path)),
                "well_name": well_name,
                "format": file_path.suffix.lower(),
                "size_bytes": len(content),
                "is_ready_for_calc": validation.get("valid", False),
                "validation_status": "Готов к расчету" if validation.get("valid") else f"Не хватает: {', '.join(validation.get('missing', []))}",
                "extracted_parameters": params,
                "sources": parsed.get("sources", [])
            })
        except Exception as exc:
            found_wells.append({
                "filename": file_path.name,
                "relative_path": str(file_path.relative_to(path)),
                "well_name": file_path.stem,
                "format": file_path.suffix.lower(),
                "size_bytes": 0,
                "is_ready_for_calc": False,
                "validation_status": f"Ошибка чтения: {exc}",
                "extracted_parameters": None,
                "sources": []
            })

    ready_count = sum(1 for w in found_wells if w["is_ready_for_calc"])

    return {
        "status": "success",
        "scanned_directory": str(path),
        "total_files_found": len(found_wells),
        "ready_for_calculation": ready_count,
        "wells": found_wells
    }
