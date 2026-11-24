"""FastAPI router for all 12 Presentation Enhancements."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from app.orchestrator.client import calc_client
from app.ai_assistant.tools import validate_well_params
from app.enhancements.optimization import (
    optimize_tubing_diameter,
    optimize_wellhead_pressure,
    find_critical_wct
)
from app.enhancements.matching import compare_with_field_measurement
from app.enhancements.report import (
    generate_markdown_report,
    generate_excel_report,
    generate_html_report,
    generate_csv_report,
    generate_json_report,
)
from app.enhancements.scanner import scan_directory_for_wells
from app.enhancements.batch import run_batch_calculation, generate_batch_excel_report
from app.enhancements.vision import extract_parameters_from_image
from app.enhancements.audio import transcribe_audio_file
from app.enhancements.protocol import generate_meeting_protocol

router = APIRouter(prefix="/api/enhancements", tags=["Presentation Enhancements (All 12)"])


# DTO Schemas
class OptimizeRequest(BaseModel):
    params: Dict[str, Any]
    optimization_type: str = Field("all", description="'tubing', 'wellhead', 'wct', or 'all'")


class MatchRequest(BaseModel):
    params: Dict[str, Any]
    measured_q_liq: float = Field(..., description="Фактический дебит жидкости, м3/сут")
    measured_p_wf: Optional[float] = Field(None, description="Фактическое забойное давление, атм")


class ReportRequest(BaseModel):
    well_name: str = "Скважина 01"
    params: Dict[str, Any]
    calculation_result: Dict[str, Any]


class ScanRequest(BaseModel):
    folder_path: str = "samples"
    recursive: bool = True


class BatchRequest(BaseModel):
    wells: List[Dict[str, Any]]


class ProtocolRequest(BaseModel):
    transcript: str


async def _calc_wrapper(params: Dict[str, Any]) -> Dict[str, Any]:
    """Внутренний вызов ядра через calc_client."""
    # Нормализуем vlp и ipr
    ipr = params.get("ipr", {})
    vlp = params.get("vlp", {})
    return await calc_client.run_full_calculation(ipr, vlp)


# =====================================================================
# 02. РАСПОЗНАВАНИЕ ФОТО И СКАНОВ
# =====================================================================
@router.post("/vision")
async def vision_endpoint(file: UploadFile = File(...)):
    """Улучшение 02: Распознавание фото и сканов паспортов/таблиц."""
    try:
        content = await file.read(10 * 1024 * 1024)
        return await extract_parameters_from_image(file.filename or "image.jpg", content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ошибка обработки изображения: {exc}")


# =====================================================================
# 03. ГОЛОСОВОЙ ВВОД
# =====================================================================
@router.post("/audio")
async def audio_endpoint(file: UploadFile = File(...)):
    """Улучшение 03: Голосовой ввод и транскрибация инженерных команд."""
    try:
        content = await file.read(25 * 1024 * 1024)
        return await transcribe_audio_file(file.filename or "audio.wav", content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ошибка обработки аудио: {exc}")


# =====================================================================
# 05. ОТЧЕТ ПО РЕЗУЛЬТАТАМ
# =====================================================================
@router.post("/report/markdown")
async def report_markdown_endpoint(req: ReportRequest):
    """Улучшение 05: Генерация Markdown-отчета."""
    md = generate_markdown_report(req.well_name, req.params, req.calculation_result)
    return {"well_name": req.well_name, "markdown": md}


@router.post("/report/excel")
async def report_excel_endpoint(req: ReportRequest):
    """Улучшение 05: Выгрузка отчета в формате Microsoft Excel (.xlsx)."""
    excel_bytes = generate_excel_report(req.well_name, req.params, req.calculation_result)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=well_report.xlsx"}
    )


@router.post("/report/html")
async def report_html_endpoint(req: ReportRequest):
    """Улучшение 05: Автономный интерактивный HTML-паспорт с ключевыми KPI и SVG-графиком."""
    html_content = generate_html_report(req.well_name, req.params, req.calculation_result)
    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "inline; filename=well_report.html"}
    )


@router.post("/report/csv")
async def report_csv_endpoint(req: ReportRequest):
    """Улучшение 05: Выгрузка данных и расчетных точек в формате CSV."""
    csv_content = generate_csv_report(req.well_name, req.params, req.calculation_result)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=well_report.csv"}
    )


@router.post("/report/json")
async def report_json_endpoint(req: ReportRequest):
    """Улучшение 05: Экспорт паспорта и метрик в структурированном JSON."""
    return generate_json_report(req.well_name, req.params, req.calculation_result)



# =====================================================================
# 06. ПОИСК ФАЙЛОВ В УКАЗАННОЙ ПАПКЕ
# =====================================================================
@router.post("/scan")
async def scan_endpoint(req: ScanRequest):
    """Улучшение 06: Поиск и авто-индексация файлов скважин в указанной директории."""
    return scan_directory_for_wells(req.folder_path, req.recursive)


# =====================================================================
# 09. ПОДБОР ПАРАМЕТРОВ РЕЖИМА
# =====================================================================
@router.post("/optimize")
async def optimize_endpoint(req: OptimizeRequest):
    """Улучшение 09: Оптимизация диаметра НКТ, давления устья и расчет WCT_crit."""
    opt_type = req.optimization_type.lower()
    res = {}

    if opt_type in {"tubing", "all"}:
        res["tubing_optimization"] = await optimize_tubing_diameter(req.params, _calc_wrapper)
    if opt_type in {"wellhead", "all"}:
        res["wellhead_sensitivity"] = await optimize_wellhead_pressure(req.params, _calc_wrapper)
    if opt_type in {"wct", "all"}:
        res["critical_wct"] = await find_critical_wct(req.params, _calc_wrapper)

    return {"status": "success", "results": res}


# =====================================================================
# 10. СРАВНЕНИЕ С ФАКТИЧЕСКИМ ЗАМЕРОМ
# =====================================================================
@router.post("/match")
async def match_endpoint(req: MatchRequest):
    """Улучшение 10: Сравнение расчетной рабочей точки с фактическим замером ГДИ/АГЗУ."""
    return await compare_with_field_measurement(
        req.params,
        req.measured_q_liq,
        req.measured_p_wf,
        _calc_wrapper
    )


# =====================================================================
# 11. ПРОТОКОЛ ОБСУЖДЕНИЯ ПО АУДИО/ТЕКСТУ
# =====================================================================
@router.post("/protocol")
async def protocol_endpoint(req: ProtocolRequest):
    """Улучшение 11: Формирование протокола технического совещания."""
    return generate_meeting_protocol(req.transcript)


# =====================================================================
# 12. ПАКЕТНЫЙ РАСЧЕТ И СВОДНЫЙ ОТЧЕТ
# =====================================================================
@router.post("/batch")
async def batch_endpoint(req: BatchRequest):
    """Улучшение 12: Пакетный расчет группы скважин и сводная статистика фонда."""
    return await run_batch_calculation(req.wells, _calc_wrapper)


@router.post("/batch/excel")
async def batch_excel_endpoint(req: BatchRequest):
    """Улучшение 12: Выгрузка сводной таблицы фонда скважин в Excel."""
    batch_res = await run_batch_calculation(req.wells, _calc_wrapper)
    excel_bytes = generate_batch_excel_report(batch_res)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=field_summary_report.xlsx"}
    )
