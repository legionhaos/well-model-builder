"""Improvement 05: Отчет по результатам (Генерация отчетов в Markdown, HTML и Excel)."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


def generate_markdown_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> str:
    """Генерация структурированного инженерного отчета в формате Markdown."""
    ipr_in = params.get("ipr", {})
    vlp_in = params.get("vlp", {})
    op = calculation_result.get("operating_point")

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    md = f"""# ИНЖЕНЕРНЫЙ ОТЧЕТ: Узловой анализ скважины «{well_name}»
**Дата формирования:** {date_str}  
**Система:** Well Model Builder v3.1  
**Статус расчета:** {'УСПЕШНО' if op else 'Срыв потока / нет пересечения'}

---

## 1. Исходные параметры объекта

### Пласт и пластовые флюиды (IPR / PVT)
- **Пластовое давление (p_res):** {ipr_in.get('p_res')} атм
- **Давление насыщения (p_b):** {ipr_in.get('pb')} атм
- **Коэффициент продуктивности (π):** {ipr_in.get('pi')} м³/(сут·атм)
- **Обводненность продукции (wct):** {ipr_in.get('wct')}%
- **Пластовая температура (t_res):** {vlp_in.get('pvt', {}).get('t_res', 90)} °C
- **Газовый фактор (rp):** {vlp_in.get('pvt', {}).get('rp', 100)} м³/т

### Конструкция скважины и гидравлика (VLP)
- **Глубина пласта (h_res):** {vlp_in.get('h_res')} м
- **Глубина спуска НКТ (h_mes):** {vlp_in.get('tubing', {}).get('h_mes', vlp_in.get('h_mes'))} м
- **Диаметр НКТ (d):** {vlp_in.get('tubing', {}).get('d', vlp_in.get('tubing_d'))} м
- **Диаметр ЭК (d):** {vlp_in.get('casing', {}).get('d', vlp_in.get('casing_d'))} м
- **Буферное давление (p_wh):** {vlp_in.get('p_wh')} атм
- **Геотермический градиент:** {vlp_in.get('geo_grad')} °C/100м

---

## 2. Результаты узлового анализа

"""
    if op:
        q_val = op.get("q_liq")
        p_val = op.get("p_wf")
        p_res = float(ipr_in.get('p_res', 200.0))
        drawdown = round(p_res - p_val, 2)
        md += f"""### Установившийся технологический режим:
| Показатель | Значение | Ед. изм. |
| :--- | :---: | :---: |
| **Дебит жидкости (q_liq)** | **{q_val}** | **м³/сут** |
| **Забойное давление (p_wf)** | **{p_val}** | **атм** |
| Депрессия на пласт (ΔP) | {drawdown} | атм |
| Режим движения в пласте | {'Двухфазный (Вогель)' if p_val < float(ipr_in.get('pb', 150)) else 'Однофазный (Дарси)'} | - |

---

## 3. Заключение и технологические выводы
1. Скважина работает в устойчивом фонтанном режиме с дебитом жидкости **{q_val} м³/сут**.
2. Забойное давление составляет **{p_val} атм**, что обеспечивает баланс между энергией пласта и гидравлическими потерями в лифте.
3. Для оптимизации добычи возможно применение сценария снижения буферного давления либо оптимизации типоразмера лифтовой колонны НКТ.
"""
    else:
        md += """### ВНИМАНИЕ: Рабочая точка не найдена!
Кривая притока IPR не пересекается с кривой подъема VLP. Скважина не способна фонтанировать в заданных термобарических условиях.
Рекомендуется:
- Снизить устьевое давление p_wh;
- Проверить герметичность и проходимость НКТ;
- Рассмотреть перевод на механизированную добычу (УЭЦН / ШГН).
"""
    return md


def generate_excel_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> bytes:
    """Генерация структурированного отчета в формате Microsoft Excel (.xlsx)."""
    wb = openpyxl.Workbook()
    
    # 1. Лист «Сводка»
    ws_summary = wb.active
    ws_summary.title = "Сводка"
    
    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True, color="111827")
    accent_font = Font(name="Arial", size=11, bold=True, color="0284C7")
    
    ws_summary["A1"] = f"УЗЛОВОЙ АНАЛИЗ СКВАЖИНЫ: {well_name}"
    ws_summary["A1"].font = title_font
    ws_summary["A2"] = f"Дата расчета: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    headers = ["Параметр", "Значение", "Единица измерения"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws_summary.cell(row=4, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        
    ipr = params.get("ipr", {})
    vlp = params.get("vlp", {})
    op = calculation_result.get("operating_point") or {}
    
    rows = [
        ("Пластовое давление (p_res)", ipr.get("p_res"), "атм"),
        ("Давление насыщения (p_b)", ipr.get("pb"), "атм"),
        ("Коэффициент продуктивности (pi)", ipr.get("pi"), "м³/(сут·атм)"),
        ("Обводненность (wct)", ipr.get("wct"), "%"),
        ("Буферное давление (p_wh)", vlp.get("p_wh"), "атм"),
        ("Глубина пласта (h_res)", vlp.get("h_res"), "м"),
        ("Глубина спуска НКТ (h_mes)", vlp.get("tubing", {}).get("h_mes", vlp.get("h_mes")), "м"),
        ("Диаметр НКТ (d)", vlp.get("tubing", {}).get("d", vlp.get("tubing_d")), "м"),
        ("Диаметр колонны ЭК (d)", vlp.get("casing", {}).get("d", vlp.get("casing_d")), "м"),
        ("Дебит жидкости в рабочей точке (q_liq)", op.get("q_liq", "Не найдена"), "м³/сут"),
        ("Забойное давление в рабочей точке (p_wf)", op.get("p_wf", "Не найдена"), "атм"),
    ]
    
    for r_idx, (p_name, p_val, p_unit) in enumerate(rows, 5):
        ws_summary.cell(row=r_idx, column=1, value=p_name)
        val_cell = ws_summary.cell(row=r_idx, column=2, value=p_val)
        if "рабочей точке" in p_name:
            val_cell.font = accent_font
        ws_summary.cell(row=r_idx, column=3, value=p_unit)
        
    ws_summary.column_dimensions["A"].width = 42
    ws_summary.column_dimensions["B"].width = 18
    ws_summary.column_dimensions["C"].width = 20
    
    # 2. Лист «Кривые IPR и VLP»
    ws_curves = wb.create_sheet(title="Кривые IPR и VLP")
    c_headers = ["Точка", "q_liq IPR (м³/сут)", "p_wf IPR (атм)", "q_liq VLP (м³/сут)", "p_wf VLP (атм)"]
    for col_idx, h in enumerate(c_headers, 1):
        cell = ws_curves.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        
    ipr_data = calculation_result.get("ipr", {})
    vlp_data = calculation_result.get("vlp", {})
    ipr_q = ipr_data.get("q_liq", [])
    ipr_p = ipr_data.get("p_wf", [])
    vlp_q = vlp_data.get("q_liq", [])
    vlp_p = vlp_data.get("p_wf", [])
    
    max_len = max(len(ipr_q), len(vlp_q))
    for i in range(max_len):
        r_num = i + 2
        ws_curves.cell(row=r_num, column=1, value=i + 1)
        ws_curves.cell(row=r_num, column=2, value=ipr_q[i] if i < len(ipr_q) else None)
        ws_curves.cell(row=r_num, column=3, value=ipr_p[i] if i < len(ipr_p) else None)
        ws_curves.cell(row=r_num, column=4, value=vlp_q[i] if i < len(vlp_q) else None)
        ws_curves.cell(row=r_num, column=5, value=vlp_p[i] if i < len(vlp_p) else None)
        
    ws_curves.column_dimensions["A"].width = 10
    ws_curves.column_dimensions["B"].width = 22
    ws_curves.column_dimensions["C"].width = 20
    ws_curves.column_dimensions["D"].width = 22
    ws_curves.column_dimensions["E"].width = 20
    
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
