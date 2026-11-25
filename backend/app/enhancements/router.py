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
from app.enhancements.economics import calculate_unit_economics
from app.enhancements.flow_assurance import evaluate_flow_assurance
from app.enhancements.vfm import estimate_virtual_flow
from app.enhancements.monte_carlo import run_monte_carlo_analysis
from app.enhancements.gtm_generator import generate_gtm_application

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


class EconomicsRequest(BaseModel):
    base_params: Dict[str, Any]
    base_result: Optional[Dict[str, Any]] = None
    opt_params: Optional[Dict[str, Any]] = None
    opt_result: Optional[Dict[str, Any]] = None
    oil_price_rub: float = 35000.0
    ndpi_rub: float = 18000.0
    transport_rub: float = 2500.0
    water_treatment_rub: float = 150.0
    workover_cost_rub: float = 1800000.0


class FlowAssuranceRequest(BaseModel):
    params: Dict[str, Any]
    calculation_result: Optional[Dict[str, Any]] = None


class VFMRequest(BaseModel):
    params: Dict[str, Any]
    p_wh_observed: float
    t_wh_observed: Optional[float] = None


class MonteCarloRequest(BaseModel):
    params: Dict[str, Any]
    n_iterations: int = 100
    p_res_std_pct: float = 8.0
    pi_std_pct: float = 12.0
    p_wh_std_pct: float = 6.0
    wct_std_pct: float = 5.0
    seed: Optional[int] = 42


class GTMRequest(BaseModel):
    well_name: str = "Скважина 01"
    params: Dict[str, Any]
    calculation_result: Optional[Dict[str, Any]] = None
    measured_q_liq: Optional[float] = None
    measured_p_wf: Optional[float] = None
    skin_factor: Optional[float] = None
    enterprise_name: str = "ООО «Башнефть-Добыча»"
    field_name: str = "Арланское месторождение"
    reservoir_name: str = "Пласт C-I"


async def _calc_wrapper(params: Dict[str, Any]) -> Dict[str, Any]:
    """Внутренний вызов ядра через calc_client с поддержкой как вложенных, так и плоских словарей."""
    ipr = dict(params.get("ipr", {}))
    vlp = dict(params.get("vlp", {}))

    # Если параметры переданы плоским словарем (например из чата или формы)
    if not ipr or "p_res" not in ipr:
        ipr = {
            "p_res": float(params.get("p_res") or params.get("P_res") or 200.0),
            "wct": float(params.get("wct") or params.get("WCT") or 50.0),
            "pi": float(params.get("pi") or params.get("PI") or 1.0),
            "pb": float(params.get("pb") or params.get("P_b") or 150.0),
            "points": 21
        }

    if not vlp or "inclinometry" not in vlp:
        h_res = float(params.get("h_res") or params.get("H_res") or 1500.0)
        h_mes = float(params.get("h_mes") or params.get("H_mes") or 1000.0)
        d_tubing = float(params.get("d") or params.get("d_tubing") or 0.062)
        d_casing = float(params.get("d_casing") or 0.1)
        wct = float(params.get("wct") or params.get("WCT") or 50.0)
        rp = float(params.get("rp") or params.get("Rp") or 100.0)
        t_res = float(params.get("t_res") or params.get("T_res") or 90.0)
        p_wh = float(params.get("p_wh") or params.get("P_wh") or 10.0)

        vlp = {
            "inclinometry": {
                "MD": [0.0, h_mes, h_res],
                "TVD": [0.0, h_mes, min(h_res, h_mes + max(100.0, (h_res - h_mes) * 0.8))]
            },
            "casing": {"d": d_casing},
            "tubing": {"d": d_tubing, "h_mes": h_mes},
            "pvt": {
                "wct": wct,
                "rp": rp,
                "gamma_oil": float(params.get("gamma_oil") or 0.8),
                "gamma_gas": float(params.get("gamma_gas") or 0.7),
                "gamma_wat": 1.0,
                "t_res": t_res
            },
            "p_wh": p_wh,
            "geo_grad": float(params.get("geo_grad") or 3.0),
            "h_res": h_res,
            "roughness": float(params.get("roughness") or 0.0001),
            "q_max": 400.0,
            "points": 21
        }

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


# =====================================================================
# KILLER FEATURE 1: ЭКОНОМИЧЕСКИЙ КАЛЬКУЛЯТОР ЭФФЕКТА (Unit Economics)
# =====================================================================
@router.post("/economics")
async def economics_endpoint(req: EconomicsRequest):
    """Killer Feature 1: Расчет юнит-экономики, чистой прибыли в рублях и окупаемости ТКРС."""
    base_res = req.base_result
    if not base_res:
        base_res = await _calc_wrapper(req.base_params)

    opt_res = req.opt_result
    if not opt_res and req.opt_params:
        opt_res = await _calc_wrapper(req.opt_params)

    return calculate_unit_economics(
        base_params=req.base_params,
        base_result=base_res,
        opt_params=req.opt_params,
        opt_result=opt_res,
        oil_price_rub=req.oil_price_rub,
        ndpi_rub=req.ndpi_rub,
        transport_rub=req.transport_rub,
        water_treatment_rub=req.water_treatment_rub,
        workover_cost_rub=req.workover_cost_rub,
    )


# =====================================================================
# KILLER FEATURE 2: САМОЗАДАВЛИВАНИЕ (TURNER) И ЭРОЗИЯ (API RP 14E)
# =====================================================================
@router.post("/flow-assurance")
async def flow_assurance_endpoint(req: FlowAssuranceRequest):
    """Killer Feature 2: Диагностика Liquid Loading по Тернеру и эрозионной безопасности по API 14E."""
    calc_res = req.calculation_result
    if not calc_res:
        calc_res = await _calc_wrapper(req.params)

    return evaluate_flow_assurance(
        params=req.params,
        calculation_result=calc_res
    )


# =====================================================================
# KILLER FEATURE 3: «ВИРТУАЛЬНЫЙ РАСХОДОМЕР» (Virtual Flow Meter, VFM)
# =====================================================================
@router.post("/vfm")
async def vfm_endpoint(req: VFMRequest):
    """Killer Feature 3: Бездатчиковое динамическое восстановление дебита по буферному давлению."""
    return await estimate_virtual_flow(
        params=req.params,
        p_wh_observed=req.p_wh_observed,
        t_wh_observed=req.t_wh_observed,
        calc_fn=_calc_wrapper
    )


# =====================================================================
# KILLER FEATURE 4: АНАЛИЗ НЕОПРЕДЕЛЕННОСТЕЙ МОНТЕ-КАРЛО (P10 / P50 / P90)
# =====================================================================
@router.post("/monte-carlo")
async def monte_carlo_endpoint(req: MonteCarloRequest):
    """Killer Feature 4: 100 микро-симуляций методом Монте-Карло с расчетом P10, P50, P90."""
    return await run_monte_carlo_analysis(
        params=req.params,
        calc_fn=_calc_wrapper,
        n_iterations=req.n_iterations,
        p_res_std_pct=req.p_res_std_pct,
        pi_std_pct=req.pi_std_pct,
        p_wh_std_pct=req.p_wh_std_pct,
        wct_std_pct=req.wct_std_pct,
        seed=req.seed
    )


# =====================================================================
# KILLER FEATURE 5: АВТО-ГЕНЕРАТОР ЗАЯВКИ НА ГТМ (ОПЗ / ГРП / ТКРС)
# =====================================================================
@router.post("/gtm")
async def gtm_endpoint(req: GTMRequest):
    """Killer Feature 5: Авто-генерация официального бланка-заявки на ГТМ по форме НГДУ."""
    calc_res = req.calculation_result
    if not calc_res:
        calc_res = await _calc_wrapper(req.params)

    return generate_gtm_application(
        well_name=req.well_name,
        params=req.params,
        calculation_result=calc_res,
        measured_q_liq=req.measured_q_liq,
        measured_p_wf=req.measured_p_wf,
        skin_factor=req.skin_factor,
        enterprise_name=req.enterprise_name,
        field_name=req.field_name,
        reservoir_name=req.reservoir_name
    )
