"""Improvement 12: Пакетный расчет и сводный отчет (Параллельный расчет пула скважин и выгрузка сводки)."""

from __future__ import annotations

import asyncio
import io
from datetime import datetime
from typing import Any, Callable, Dict, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


async def run_batch_calculation(
    wells: List[Dict[str, Any]],
    calculate: Callable[[Dict[str, Any]], Any]
) -> Dict[str, Any]:
    """
    Параллельный расчет гидродинамических моделей для пула скважин (месторождение / куст).
    """
    async def _calc_single(item: Dict[str, Any]) -> Dict[str, Any]:
        well_id = item.get("id") or item.get("name") or "well"
        name = item.get("name") or well_id
        params = item.get("params") or item

        try:
            res = await calculate(params)
            op = res.get("operating_point")
            wct = float(params.get("ipr", {}).get("wct", 50.0))

            if op:
                q_liq = round(float(op["q_liq"]), 2)
                p_wf = round(float(op["p_wf"]), 2)
                # Дебит нефти по формуле: q_oil = q_liq * (1 - wct / 100)
                q_oil = round(q_liq * (1.0 - wct / 100.0), 2)
                return {
                    "id": well_id,
                    "name": name,
                    "status": "flowing",
                    "q_liq_m3_day": q_liq,
                    "q_oil_m3_day": q_oil,
                    "p_wf_atm": p_wf,
                    "wct_pct": wct,
                    "error": None
                }
            else:
                return {
                    "id": well_id,
                    "name": name,
                    "status": "killed",
                    "q_liq_m3_day": 0.0,
                    "q_oil_m3_day": 0.0,
                    "p_wf_atm": None,
                    "wct_pct": wct,
                    "error": "Срыв фонтанирования (нет пересечения)"
                }
        except Exception as exc:
            return {
                "id": well_id,
                "name": name,
                "status": "error",
                "q_liq_m3_day": 0.0,
                "q_oil_m3_day": 0.0,
                "p_wf_atm": None,
                "wct_pct": 0.0,
                "error": str(exc)
            }

    tasks = [_calc_single(w) for w in wells]
    results = await asyncio.gather(*tasks)

    # Вычисление агрегированных показателей фонда
    total_wells = len(results)
    flowing_wells = sum(1 for r in results if r["status"] == "flowing")
    killed_wells = sum(1 for r in results if r["status"] == "killed")
    error_wells = sum(1 for r in results if r["status"] == "error")

    total_q_liq = round(sum(r["q_liq_m3_day"] for r in results), 2)
    total_q_oil = round(sum(r["q_oil_m3_day"] for r in results), 2)

    flowing_pwfs = [r["p_wf_atm"] for r in results if r["p_wf_atm"] is not None]
    avg_p_wf = round(sum(flowing_pwfs) / len(flowing_pwfs), 2) if flowing_pwfs else None

    return {
        "status": "success",
        "batch_time": datetime.now().isoformat(),
        "summary": {
            "total_wells": total_wells,
            "flowing_wells": flowing_wells,
            "killed_wells": killed_wells,
            "error_wells": error_wells,
            "flowing_factor_pct": round((flowing_wells / total_wells) * 100.0, 1) if total_wells else 0.0,
            "total_q_liq_m3_day": total_q_liq,
            "total_q_oil_m3_day": total_q_oil,
            "average_flowing_p_wf_atm": avg_p_wf
        },
        "wells_data": results
    }


def generate_batch_excel_report(batch_result: Dict[str, Any]) -> bytes:
    """Экспорт сводной таблицы фонда скважин в Excel."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сводный отчет по фонду"

    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True, color="111827")

    ws["A1"] = "СВОДНЫЙ ОТЧЕТ УЗЛОВОГО АНАЛИЗА ПО ФОНДУ СКВАЖИН"
    ws["A1"].font = title_font
    ws["A2"] = f"Дата расчета: {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    summary = batch_result.get("summary", {})
    ws["A4"] = f"Всего скважин: {summary.get('total_wells')}"
    ws["B4"] = f"Фонтанирующих: {summary.get('flowing_wells')}"
    ws["C4"] = f"Суммарный Qж: {summary.get('total_q_liq_m3_day')} м³/сут"
    ws["D4"] = f"Суммарная Qн: {summary.get('total_q_oil_m3_day')} м³/сут"

    headers = [
        "№", "Скважина", "Статус", "Дебит жидкости (м³/сут)",
        "Дебит нефти (м³/сут)", "Забойное давление (атм)", "Обводненность (%)", "Примечание"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=6, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    wells = batch_result.get("wells_data", [])
    for idx, w in enumerate(wells, 1):
        row_num = idx + 6
        ws.cell(row=row_num, column=1, value=idx)
        ws.cell(row=row_num, column=2, value=w.get("name"))
        ws.cell(row=row_num, column=3, value=w.get("status"))
        ws.cell(row=row_num, column=4, value=w.get("q_liq_m3_day"))
        ws.cell(row=row_num, column=5, value=w.get("q_oil_m3_day"))
        ws.cell(row=row_num, column=6, value=w.get("p_wf_atm"))
        ws.cell(row=row_num, column=7, value=w.get("wct_pct"))
        ws.cell(row=row_num, column=8, value=w.get("error") or "Штатный режим")

    for col in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        ws.column_dimensions[col].width = 22

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
