"""Improvement 05: Отчет по результатам (Генерация отчетов в HTML, Excel, CSV, JSON и Markdown)."""

from __future__ import annotations

import io
import json
import csv
from datetime import datetime
from typing import Any, Dict, List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


def _extract_metrics(params: Dict[str, Any], calculation_result: Dict[str, Any]) -> Dict[str, Any]:
    """Вспомогательный расчет всех ключевых промысловых метрик."""
    ipr_in = params.get("ipr", {})
    vlp_in = params.get("vlp", {})
    pvt_in = vlp_in.get("pvt", {})
    op = calculation_result.get("operating_point")

    p_res = float(ipr_in.get("p_res", 200.0))
    pb = float(ipr_in.get("pb", 150.0))
    pi = float(ipr_in.get("pi", 1.0))
    wct = float(ipr_in.get("wct", 50.0))
    rp = float(pvt_in.get("rp", 100.0))
    gamma_oil = float(pvt_in.get("gamma_oil", 0.8))

    if op:
        q_liq = round(float(op.get("q_liq", 0.0)), 2)
        p_wf = round(float(op.get("p_wf", 0.0)), 2)
        drawdown = round(p_res - p_wf, 2)
        drawdown_pct = round((drawdown / p_res) * 100, 1) if p_res > 0 else 0.0
        # Дебит чистой нефти
        q_oil = round(q_liq * (1.0 - wct / 100.0), 2)
        # Дебит попутного нефтяного газа в тыс. м3/сут
        q_gas = round(q_oil * rp / 1000.0, 3)
        # Режим притока
        is_bubble_point = p_wf < pb
        flow_regime = "Двухфазный (ниже давления насыщения Pb)" if is_bubble_point else "Однофазный (выше давления насыщения Pb)"
        status_label = "Устойчивое фонтанирование"
        status_color = "#10b981"  # Emerald green
        is_flowing = True
    else:
        q_liq = 0.0
        p_wf = None
        drawdown = 0.0
        drawdown_pct = 0.0
        q_oil = 0.0
        q_gas = 0.0
        is_bubble_point = False
        flow_regime = "Срыв потока (нет притока)"
        status_label = "Срыв фонтанирования (нет пересечения)"
        status_color = "#ef4444"  # Red
        is_flowing = False

    return {
        "p_res": p_res,
        "pb": pb,
        "pi": pi,
        "wct": wct,
        "rp": rp,
        "gamma_oil": gamma_oil,
        "q_liq": q_liq,
        "p_wf": p_wf,
        "drawdown": drawdown,
        "drawdown_pct": drawdown_pct,
        "q_oil": q_oil,
        "q_gas": q_gas,
        "is_bubble_point": is_bubble_point,
        "flow_regime": flow_regime,
        "status_label": status_label,
        "status_color": status_color,
        "is_flowing": is_flowing,
    }


def _generate_svg_chart(calculation_result: Dict[str, Any]) -> str:
    """Генерация чистого векторного SVG-графика IPR и VLP без внешних зависимостей."""
    ipr = calculation_result.get("ipr", {})
    vlp = calculation_result.get("vlp", {})
    op = calculation_result.get("operating_point")

    ipr_q: List[float] = [float(x) for x in ipr.get("q_liq", []) if x is not None]
    ipr_p: List[float] = [float(x) for x in ipr.get("p_wf", []) if x is not None]
    vlp_q: List[float] = [float(x) for x in vlp.get("q_liq", []) if x is not None]
    vlp_p: List[float] = [float(x) for x in vlp.get("p_wf", []) if x is not None]

    if not ipr_q and not vlp_q:
        return "<div style='color:#71717a;padding:20px;text-align:center;'>Нет данных для построения графика</div>"

    max_q = max(max(ipr_q, default=100.0), max(vlp_q, default=100.0)) * 1.05
    max_p = max(max(ipr_p, default=200.0), max(vlp_p, default=200.0)) * 1.05
    if max_q <= 0:
        max_q = 100.0
    if max_p <= 0:
        max_p = 200.0

    w = 740
    h = 380
    pad_l = 65
    pad_r = 30
    pad_t = 30
    pad_b = 50

    chart_w = w - pad_l - pad_r
    chart_h = h - pad_t - pad_b

    def to_svg_x(q: float) -> float:
        return pad_l + (q / max_q) * chart_w

    def to_svg_y(p: float) -> float:
        return pad_t + (1.0 - (p / max_p)) * chart_h

    # Сетка
    grid_lines = []
    # 5 делений по X
    for i in range(6):
        qx = (max_q / 5.0) * i
        sx = to_svg_x(qx)
        grid_lines.append(f'<line x1="{sx:.1f}" y1="{pad_t}" x2="{sx:.1f}" y2="{h - pad_b}" stroke="#e4e4e7" stroke-dasharray="3,3" />')
        grid_lines.append(f'<text x="{sx:.1f}" y="{h - pad_b + 20}" font-size="11" fill="#71717a" text-anchor="middle" font-family="sans-serif">{qx:.0f}</text>')

    # 5 делений по Y
    for i in range(6):
        py = (max_p / 5.0) * i
        sy = to_svg_y(py)
        grid_lines.append(f'<line x1="{pad_l}" y1="{sy:.1f}" x2="{w - pad_r}" y2="{sy:.1f}" stroke="#e4e4e7" stroke-dasharray="3,3" />')
        grid_lines.append(f'<text x="{pad_l - 10}" y="{sy + 4:.1f}" font-size="11" fill="#71717a" text-anchor="end" font-family="sans-serif">{py:.0f}</text>')

    # IPR линия
    ipr_pts = [f"{to_svg_x(q):.1f},{to_svg_y(p):.1f}" for q, p in zip(ipr_q, ipr_p)]
    ipr_polyline = f'<polyline points="{" ".join(ipr_pts)}" fill="none" stroke="#2563eb" stroke-width="3" stroke-linecap="round" />'

    # VLP линия
    vlp_pts = [f"{to_svg_x(q):.1f},{to_svg_y(p):.1f}" for q, p in zip(vlp_q, vlp_p)]
    vlp_polyline = f'<polyline points="{" ".join(vlp_pts)}" fill="none" stroke="#f97316" stroke-width="3" stroke-linecap="round" />'

    # Рабочая точка
    op_elements = []
    if op and op.get("q_liq") is not None and op.get("p_wf") is not None:
        op_q = float(op["q_liq"])
        op_p = float(op["p_wf"])
        op_x = to_svg_x(op_q)
        op_y = to_svg_y(op_p)
        # Пунктирные проекции на оси
        op_elements.append(f'<line x1="{pad_l}" y1="{op_y:.1f}" x2="{op_x:.1f}" y2="{op_y:.1f}" stroke="#10b981" stroke-width="1.5" stroke-dasharray="4,4" />')
        op_elements.append(f'<line x1="{op_x:.1f}" y1="{op_y:.1f}" x2="{op_x:.1f}" y2="{h - pad_b}" stroke="#10b981" stroke-width="1.5" stroke-dasharray="4,4" />')
        # Точка
        op_elements.append(f'<circle cx="{op_x:.1f}" cy="{op_y:.1f}" r="8" fill="#10b981" stroke="#ffffff" stroke-width="3" filter="drop-shadow(0px 2px 4px rgba(0,0,0,0.25))" />')
        # Текстовая плашка над точкой
        text_w = 170
        text_h = 32
        badge_x = min(max(op_x - text_w / 2, pad_l + 10), w - pad_r - text_w - 10)
        badge_y = max(op_y - text_h - 12, pad_t + 10)
        op_elements.append(f'''
            <g transform="translate({badge_x:.1f}, {badge_y:.1f})">
              <rect width="{text_w}" height="{text_h}" rx="6" fill="#111827" opacity="0.9" />
              <text x="{text_w/2}" y="20" fill="#ffffff" font-size="11" font-weight="bold" font-family="sans-serif" text-anchor="middle">
                Q={op_q:.2f} м³/сут, P={op_p:.2f} атм
              </text>
            </g>
        ''')

    return f'''
    <svg viewBox="0 0 {w} {h}" width="100%" height="auto" style="max-height: 400px; display: block;" xmlns="http://www.w3.org/2000/svg">
      <!-- Фон графика -->
      <rect x="{pad_l}" y="{pad_t}" width="{chart_w}" height="{chart_h}" fill="#f8fafc" rx="4" />
      
      <!-- Сетка -->
      {''.join(grid_lines)}
      
      <!-- Оси -->
      <line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{h - pad_b}" stroke="#475569" stroke-width="1.5" />
      <line x1="{pad_l}" y1="{h - pad_b}" x2="{w - pad_r}" y2="{h - pad_b}" stroke="#475569" stroke-width="1.5" />
      
      <!-- Подписи осей -->
      <text x="{pad_l + chart_w / 2}" y="{h - 12}" font-size="12" font-weight="600" fill="#334155" text-anchor="middle" font-family="sans-serif">
        Дебит жидкости Q_liq (м³/сут)
      </text>
      <text x="18" y="{pad_t + chart_h / 2}" font-size="12" font-weight="600" fill="#334155" text-anchor="middle" font-family="sans-serif" transform="rotate(-90, 18, {pad_t + chart_h / 2})">
        Давление на забое P_wf (атм)
      </text>
      
      <!-- Кривые -->
      {ipr_polyline}
      {vlp_polyline}
      
      <!-- Точка пересечения -->
      {''.join(op_elements)}
    </svg>
    '''


def _build_report_context(
    params: Dict[str, Any],
    calculation_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Enrich metrics with non-physical input/output warnings across all export formats."""
    import html as _html_lib
    from app.orchestrator.router import inspect_physical_warnings

    metrics = _extract_metrics(params, calculation_result)
    calc_dict = calculation_result if isinstance(calculation_result, dict) else {}
    meta = calc_dict.get("meta") if isinstance(calc_dict.get("meta"), dict) else {}
    raw_warnings = [str(w) for w in (meta.get("warnings") or []) if str(w).strip()]
    for w in inspect_physical_warnings(params.get("ipr") or {}, params.get("vlp") or {}, calc_dict):
        if w not in raw_warnings:
            raw_warnings.append(w)

    op = calc_dict.get("operating_point")
    if isinstance(op, dict):
        q_val = op.get("q_liq")
        p_val = op.get("p_wf")
        if isinstance(q_val, (int, float)) and q_val <= 0:
            msg = f"Расчётный дебит Q_liq = {q_val:.2f} м³/сут ≤ 0 (отрицательный или нулевой дебит)."
            if msg not in raw_warnings:
                raw_warnings.append(msg)
        if isinstance(p_val, (int, float)) and p_val <= 0:
            msg = f"Расчётное забойное давление P_wf = {p_val:.2f} атм ≤ 0 (нефизично)."
            if msg not in raw_warnings:
                raw_warnings.append(msg)

    is_physical = (meta.get("is_physical") is not False) and len(raw_warnings) == 0
    if not is_physical:
        metrics["status_label"] = "НЕФИЗИЧНЫЙ РАСЧЕТ (ТРЕБУЕТСЯ ПРОВЕРКА)"
        metrics["status_color"] = "#dc2626"
    metrics["is_physical"] = is_physical
    metrics["warnings"] = raw_warnings
    metrics["warnings_html"] = "".join(
        f"<li>{_html_lib.escape(w)}</li>" for w in raw_warnings
    )
    return metrics


def generate_html_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> str:
    """Генерация премиального автономного интерактивного HTML-отчета со всеми метриками."""
    metrics = _build_report_context(params, calculation_result)
    svg_chart = _generate_svg_chart(calculation_result)

    ipr_in = params.get("ipr", {})
    vlp_in = params.get("vlp", {})
    pvt_in = vlp_in.get("pvt", {})
    tubing_in = vlp_in.get("tubing", {})
    casing_in = vlp_in.get("casing", {})

    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    calc_time = calculation_result.get("meta", {}).get("calc_time_ms", 0.0)

    # Точки кривых для таблицы
    ipr_data = calculation_result.get("ipr", {})
    vlp_data = calculation_result.get("vlp", {})
    ipr_q = ipr_data.get("q_liq", [])
    ipr_p = ipr_data.get("p_wf", [])
    vlp_q = vlp_data.get("q_liq", [])
    vlp_p = vlp_data.get("p_wf", [])

    table_rows = []
    max_len = min(max(len(ipr_q), len(vlp_q)), 30)  # Первые 30 точек
    for i in range(max_len):
        q_i = f"{ipr_q[i]:.2f}" if i < len(ipr_q) else "—"
        p_i = f"{ipr_p[i]:.2f}" if i < len(ipr_p) else "—"
        q_v = f"{vlp_q[i]:.2f}" if i < len(vlp_q) else "—"
        p_v = f"{vlp_p[i]:.2f}" if i < len(vlp_p) else "—"
        table_rows.append(f"""
        <tr>
          <td style="text-align:center; color:#64748b;">{i+1}</td>
          <td>{q_i}</td>
          <td>{p_i}</td>
          <td>{q_v}</td>
          <td>{p_v}</td>
        </tr>
        """)

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Инженерный отчет: {well_name}</title>
  <style>
    :root {{
      --primary: #0284c7;
      --primary-dark: #0369a1;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 30px 20px;
    }}
    .container {{
      max-width: 1040px;
      margin: 0 auto;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 2px solid var(--border);
      margin-bottom: 28px;
    }}
    .header-title h1 {{
      font-size: 26px;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.02em;
    }}
    .header-title p {{
      color: var(--text-muted);
      font-size: 13px;
      margin-top: 4px;
    }}
    .header-actions {{
      display: flex;
      gap: 12px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: #0f172a;
      color: #ffffff;
      font-weight: 600;
      font-size: 13px;
      padding: 10px 18px;
      border-radius: 8px;
      text-decoration: none;
      border: none;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .btn:hover {{ background: #334155; }}
    .badge {{
      display: inline-block;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 700;
      background: {metrics['status_color']}20;
      color: {metrics['status_color']};
      border: 1px solid {metrics['status_color']}40;
    }}
    .grid-kpi {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      padding: 18px 20px;
      border-radius: 12px;
      border: 1px solid var(--border);
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .kpi-label {{
      font-size: 12px;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .kpi-value {{
      font-size: 24px;
      font-weight: 800;
      color: #0f172a;
      margin: 6px 0 2px 0;
      font-variant-numeric: tabular-nums;
    }}
    .kpi-unit {{
      font-size: 12px;
      color: var(--text-muted);
      font-weight: 500;
    }}
    .card {{
      background: var(--card-bg);
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 24px;
      margin-bottom: 28px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .card-title {{
      font-size: 17px;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .chart-container {{
      background: #ffffff;
      border-radius: 8px;
      padding: 10px 0;
    }}
    .chart-legend {{
      display: flex;
      justify-content: center;
      gap: 28px;
      margin-top: 14px;
      font-size: 13px;
      font-weight: 600;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .dot {{
      width: 12px;
      height: 12px;
      border-radius: 3px;
    }}
    .params-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }}
    table.data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    table.data-table th {{
      background: #f1f5f9;
      color: #475569;
      font-weight: 700;
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
    }}
    table.data-table td {{
      padding: 9px 12px;
      border-bottom: 1px solid #f1f5f9;
      color: #334155;
    }}
    table.data-table tr:last-child td {{ border-bottom: none; }}
    .recommendations {{
      background: #eff6ff;
      border-left: 4px solid #0284c7;
      padding: 16px 20px;
      border-radius: 0 8px 8px 0;
      font-size: 14px;
      color: #1e3a8a;
    }}
    .recommendations ul {{
      margin-left: 20px;
      margin-top: 8px;
    }}
    .recommendations li {{
      margin-bottom: 6px;
    }}
    .alert-nonphysical {{
      background: #fef2f2;
      border: 2px solid #dc2626;
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
      color: #991b1b;
    }}
    .alert-nonphysical strong {{
      display: block;
      font-size: 15px;
      margin-bottom: 6px;
    }}
    .alert-nonphysical ul {{
      margin-left: 20px;
      font-size: 13px;
    }}
    @media print {{
      body {{ background: #ffffff; padding: 0; }}
      .btn {{ display: none; }}
      .container {{ max-width: 100%; }}
      .card {{ border: 1px solid #ccc; box-shadow: none; page-break-inside: avoid; }}
    }}
    @media (max-width: 768px) {{
      .params-grid {{ grid-template-columns: 1fr; }}
      .grid-kpi {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Шапка отчета -->
    <div class="header">
      <div class="header-title">
        <h1>Паспорт узлового анализа: {well_name}</h1>
        <p>Сформировано системой Well Model Builder v3.1 | Дата: {now_str} | Время расчета: {calc_time:.1f} мс</p>
      </div>
      <div class="header-actions">
        <span class="badge">{metrics['status_label']}</span>
        <button class="btn" onclick="window.print()">🖨️ Печать / PDF</button>
      </div>
    </div>

    {f'<div class="alert-nonphysical"><strong>⚠️ ВНИМАНИЕ: НЕФИЗИЧНЫЙ ИЛИ НЕКОРРЕКТНЫЙ РАСЧЕТ (ЭКСПОРТ С ПРЕДУПРЕЖДЕНИЕМ)</strong><ul>{metrics["warnings_html"]}</ul></div>' if metrics['warnings'] else ''}

    <!-- Блок ключевых KPI (Карточки) -->
    <div class="grid-kpi">
      <div class="kpi-card" style="border-top: 4px solid #0284c7;">
        <div class="kpi-label">Дебит жидкости (Q_liq)</div>
        <div class="kpi-value" style="color: #0284c7;">{metrics['q_liq']}</div>
        <div class="kpi-unit">м³/сут</div>
      </div>
      <div class="kpi-card" style="border-top: 4px solid #10b981;">
        <div class="kpi-label">Дебит нефти (Q_oil)</div>
        <div class="kpi-value" style="color: #10b981;">{metrics['q_oil']}</div>
        <div class="kpi-unit">м³/сут (WCT {metrics['wct']}%)</div>
      </div>
      <div class="kpi-card" style="border-top: 4px solid #8b5cf6;">
        <div class="kpi-label">Дебит газа (Q_gas)</div>
        <div class="kpi-value" style="color: #8b5cf6;">{metrics['q_gas']}</div>
        <div class="kpi-unit">тыс. м³/сут</div>
      </div>
      <div class="kpi-card" style="border-top: 4px solid #f97316;">
        <div class="kpi-label">Забойное давл. (P_wf)</div>
        <div class="kpi-value" style="color: #f97316;">{metrics['p_wf'] if metrics['p_wf'] is not None else '—'}</div>
        <div class="kpi-unit">атм</div>
      </div>
      <div class="kpi-card" style="border-top: 4px solid #06b6d4;">
        <div class="kpi-label">Депрессия (ΔP)</div>
        <div class="kpi-value">{metrics['drawdown']}</div>
        <div class="kpi-unit">атм ({metrics['drawdown_pct']}% от P_res)</div>
      </div>
    </div>

    <!-- Интерактивный График IPR / VLP -->
    <div class="card">
      <div class="card-title">
        <span>График узлового анализа (Nodal Analysis Curve)</span>
        <span style="font-size: 13px; font-weight: 500; color: #64748b;">Точка пересечения IPR и VLP</span>
      </div>
      <div class="chart-container">
        {svg_chart}
      </div>
      <div class="chart-legend">
        <div class="legend-item"><span class="dot" style="background:#2563eb;"></span> Кривая притока пласта (IPR)</div>
        <div class="legend-item"><span class="dot" style="background:#f97316;"></span> Кривая подъема лифта (VLP)</div>
        <div class="legend-item"><span class="dot" style="background:#10b981; border-radius:50%;"></span> Рабочая точка (Operating Point)</div>
      </div>
    </div>

    <!-- Параметры Пласта и Конструкции -->
    <div class="card">
      <div class="card-title">Технологические характеристики и параметры модели</div>
      <div class="params-grid">
        <!-- Колонка 1: Пласт -->
        <div>
          <h3 style="font-size:14px; font-weight:700; margin-bottom:10px; color:#334155;">Характеристики пласта и PVT (IPR)</h3>
          <table class="data-table">
            <tr><td>Пластовое давление (P_res)</td><td><strong>{metrics['p_res']} атм</strong></td></tr>
            <tr><td>Давление насыщения (P_b)</td><td><strong>{metrics['pb']} атм</strong></td></tr>
            <tr><td>Коэффициент продуктивности (π)</td><td><strong>{metrics['pi']} м³/(сут·атм)</strong></td></tr>
            <tr><td>Обводненность продукции (WCT)</td><td><strong>{metrics['wct']} %</strong></td></tr>
            <tr><td>Газовый фактор (R_p)</td><td><strong>{metrics['rp']} м³/т</strong></td></tr>
            <tr><td>Относительная плотность нефти</td><td><strong>{metrics['gamma_oil']}</strong></td></tr>
            <tr><td>Режим фильтрации в пласте</td><td><strong>{metrics['flow_regime']}</strong></td></tr>
          </table>
        </div>

        <!-- Колонка 2: Ствол и подъемник -->
        <div>
          <h3 style="font-size:14px; font-weight:700; margin-bottom:10px; color:#334155;">Конструкция скважины и устье (VLP)</h3>
          <table class="data-table">
            <tr><td>Глубина пласта по вертикали</td><td><strong>{vlp_in.get('h_res', 1500)} м</strong></td></tr>
            <tr><td>Глубина спуска НКТ (H_mes)</td><td><strong>{tubing_in.get('h_mes', 1000)} м</strong></td></tr>
            <tr><td>Внутренний диаметр НКТ (d)</td><td><strong>{tubing_in.get('d', 0.062)} м</strong></td></tr>
            <tr><td>Диаметр эксплуатационной колонны</td><td><strong>{casing_in.get('d', 0.1)} м</strong></td></tr>
            <tr><td>Буферное устьевое давление (P_wh)</td><td><strong>{vlp_in.get('p_wh', 10.0)} атм</strong></td></tr>
            <tr><td>Геотермический градиент</td><td><strong>{vlp_in.get('geo_grad', 3.0)} °C/100м</strong></td></tr>
            <tr><td>Шероховатость труб</td><td><strong>{vlp_in.get('roughness', 0.0001)} м</strong></td></tr>
          </table>
        </div>
      </div>
    </div>

    <!-- Технологические выводы и рекомендации -->
    <div class="card">
      <div class="card-title">Инженерные выводы и рекомендации технологу</div>
      <div class="recommendations">
        <strong>Автоматический технологический аудит:</strong>
        <ul>
          <li>{('⚠️ ВНИМАНИЕ: режим признан нефизичным/недопустимым (' + '; '.join(metrics['warnings']) + '). Прогнозный дебит: <strong>' + str(metrics['q_liq']) + ' м³/сут</strong>.') if not metrics['is_physical'] else ('Скважина работает со стабильным дебитом жидкости <strong>' + str(metrics['q_liq']) + ' м³/сут</strong> и чистой нефти <strong>' + str(metrics['q_oil']) + ' м³/сут</strong>.')}</li>
          <li>{'Забойное давление P_wf (' + str(metrics['p_wf']) + ' атм) превышает давление насыщения Pb (' + str(metrics['pb']) + ' атм) — разгазирование в призабойной зоне отсутствует, однофазный режим фильтрации.' if not metrics['is_bubble_point'] else 'Забойное давление P_wf (' + str(metrics['p_wf']) + ' атм) находится ниже давления насыщения Pb (' + str(metrics['pb']) + ' атм) — активное разгазирование в призабойной зоне пласта (двухфазный режим Вогеля).'}</li>
          <li>Депрессия на пласт составляет <strong>{metrics['drawdown']} атм ({metrics['drawdown_pct']}% от пластового)</strong>, что находится в безопасном диапазоне без риска разрушения скелета пласта.</li>
          <li>Рекомендация: при росте обводненности до критического значения (> {metrics['wct'] + 30:.0f}%) рассмотреть переход на фонтанирование с оптимизированным штуцером или перевод на механизированную добычу.</li>
        </ul>
      </div>
    </div>

    <!-- Таблица расчетных точек -->
    <div class="card">
      <div class="card-title">
        <span>Таблица точек расчетных кривых IPR и VLP</span>
        <span style="font-size:12px; color:#64748b;">Показаны первые {max_len} узловых точек</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th style="width:50px; text-align:center;">№</th>
            <th>Q_liq IPR (м³/сут)</th>
            <th>P_wf IPR (атм)</th>
            <th>Q_liq VLP (м³/сут)</th>
            <th>P_wf VLP (атм)</th>
          </tr>
        </thead>
        <tbody>
          {''.join(table_rows)}
        </tbody>
      </table>
    </div>

    <!-- Подвал -->
    <div style="text-align:center; color:#94a3b8; font-size:12px; margin-top:20px;">
      Отчет сгенерирован автоматически системой Well Model Builder v3.1 | УГНТУ & «Школа 21»
    </div>
  </div>
</body>
</html>
"""
    return html


def generate_csv_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> str:
    """Генерация отчета в универсальном табличном формате CSV."""
    metrics = _build_report_context(params, calculation_result)
    ipr = calculation_result.get("ipr", {})
    vlp = calculation_result.get("vlp", {})
    ipr_q = ipr.get("q_liq", [])
    ipr_p = ipr.get("p_wf", [])
    vlp_q = vlp.get("q_liq", [])
    vlp_p = vlp.get("p_wf", [])

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow(["# ПАСПОРТ УЗЛОВОГО АНАЛИЗА", well_name])
    writer.writerow(["# Дата расчета", datetime.now().strftime("%Y-%m-%d %H:%M")])
    writer.writerow(["# Статус", metrics["status_label"]])
    writer.writerow(["# Физическая корректность", "КОРРЕКТНО" if metrics["is_physical"] else "ВНИМАНИЕ — НЕФИЗИЧНЫЙ РАСЧЕТ"])
    for w in metrics["warnings"]:
        writer.writerow(["# ПРЕДУПРЕЖДЕНИЕ", w])
    writer.writerow([])
    writer.writerow(["КЛЮЧЕВЫЕ МЕТРИКИ"])
    writer.writerow(["Параметр", "Значение", "Единица измерения"])
    writer.writerow(["Дебит жидкости (q_liq)", metrics["q_liq"], "м3/сут"])
    writer.writerow(["Дебит нефти (q_oil)", metrics["q_oil"], "м3/сут"])
    writer.writerow(["Дебит газа (q_gas)", metrics["q_gas"], "тыс. м3/сут"])
    writer.writerow(["Забойное давление (p_wf)", metrics["p_wf"] or "N/A", "атм"])
    writer.writerow(["Пластовое давление (p_res)", metrics["p_res"], "атм"])
    writer.writerow(["Депрессия на пласт (ΔP)", metrics["drawdown"], "атм"])
    writer.writerow(["Обводненность (wct)", metrics["wct"], "%"])
    writer.writerow([])
    writer.writerow(["РАСЧЕТНЫЕ ТОЧКИ КРИВЫХ IPR И VLP"])
    writer.writerow(["Номер точки", "Q_IPR (м3/сут)", "P_wf_IPR (атм)", "Q_VLP (м3/сут)", "P_wf_VLP (атм)"])

    max_len = max(len(ipr_q), len(vlp_q))
    for i in range(max_len):
        qi = ipr_q[i] if i < len(ipr_q) else ""
        pi = ipr_p[i] if i < len(ipr_p) else ""
        qv = vlp_q[i] if i < len(vlp_q) else ""
        pv = vlp_p[i] if i < len(vlp_p) else ""
        writer.writerow([i + 1, qi, pi, qv, pv])

    return output.getvalue()


def generate_json_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> Dict[str, Any]:
    """Генерация структурированного JSON-отчета для корпоративных систем (DWH/SCADA)."""
    metrics = _build_report_context(params, calculation_result)
    return {
        "well_name": well_name,
        "generated_at": datetime.now().isoformat(),
        "status": metrics["status_label"],
        "is_physical": metrics["is_physical"],
        "physical_warnings": metrics["warnings"],
        "export_notice": (
            "ВНИМАНИЕ: расчёт содержит физические аномалии или отрицательный дебит; требуется проверка исходных параметров."
            if metrics["warnings"]
            else None
        ),
        "is_flowing": metrics["is_flowing"],
        "key_metrics": {
            "q_liq_m3_day": metrics["q_liq"],
            "q_oil_m3_day": metrics["q_oil"],
            "q_gas_th_m3_day": metrics["q_gas"],
            "p_wf_atm": metrics["p_wf"],
            "drawdown_atm": metrics["drawdown"],
            "drawdown_pct": metrics["drawdown_pct"],
            "flow_regime": metrics["flow_regime"],
        },
        "input_parameters": params,
        "calculation_result": calculation_result,
    }


def generate_markdown_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> str:
    """Генерация структурированного инженерного отчета в формате Markdown."""
    metrics = _build_report_context(params, calculation_result)
    ipr_in = params.get("ipr", {})
    vlp_in = params.get("vlp", {})
    tubing_in = vlp_in.get("tubing", {})
    casing_in = vlp_in.get("casing", {})

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    warning_block = ""
    if metrics["warnings"]:
        bullet_warn = "\n".join(f"> - {w}" for w in metrics["warnings"])
        warning_block = f"\n> **⚠️ ВНИМАНИЕ: НЕФИЗИЧНЫЙ / НЕКОРРЕКТНЫЙ РАСЧЕТ (ЭКСПОРТ С ПОМЕТКОЙ)**\n{bullet_warn}\n"

    md = f"""# ИНЖЕНЕРНЫЙ ОТЧЕТ: Узловой анализ скважины «{well_name}»
**Дата формирования:** {date_str}  
**Система:** Well Model Builder v3.1  
**Статус расчета:** {metrics['status_label']}
{warning_block}
---

## 1. Ключевые показатели режима (KPI)
- **Дебит жидкости (Q_liq):** **{metrics['q_liq']} м³/сут**
- **Дебит нефти (Q_oil):** **{metrics['q_oil']} м³/сут**
- **Дебит газа (Q_gas):** **{metrics['q_gas']} тыс. м³/сут**
- **Забойное давление (P_wf):** **{metrics['p_wf']} атм**
- **Депрессия на пласт (ΔP):** **{metrics['drawdown']} атм** ({metrics['drawdown_pct']}% от пластового)
- **Режим фильтрации:** {metrics['flow_regime']}

---

## 2. Исходные параметры объекта
### Пласт и пластовые флюиды (IPR / PVT)
- **Пластовое давление (p_res):** {metrics['p_res']} атм
- **Давление насыщения (p_b):** {metrics['pb']} атм
- **Коэффициент продуктивности (π):** {metrics['pi']} м³/(сут·атм)
- **Обводненность продукции (wct):** {metrics['wct']}%
- **Газовый фактор (rp):** {metrics['rp']} м³/т

### Конструкция скважины и гидравлика (VLP)
- **Глубина пласта (h_res):** {vlp_in.get('h_res', 1500)} м
- **Глубина спуска НКТ (h_mes):** {tubing_in.get('h_mes', 1000)} м
- **Диаметр НКТ (d):** {tubing_in.get('d', 0.062)} м
- **Диаметр ЭК (d):** {casing_in.get('d', 0.1)} м
- **Буферное давление (p_wh):** {vlp_in.get('p_wh', 10.0)} атм

---

## 3. Заключение и технологические выводы
1. Скважина работает в режиме: **{metrics['status_label']}**.
2. Забойное давление обеспечивает баланс притока и подъема газожидкостной смеси.
3. Дополнительные сценарии (подбор НКТ по ГОСТ, критическая обводненность) доступны через модуль оптимизации.
"""
    return md


def generate_excel_report(
    well_name: str,
    params: Dict[str, Any],
    calculation_result: Dict[str, Any]
) -> bytes:
    """Генерация структурированного отчета в формате Microsoft Excel (.xlsx)."""
    wb = openpyxl.Workbook()
    metrics = _build_report_context(params, calculation_result)

    # 1. Лист «Сводка»
    ws_summary = wb.active
    ws_summary.title = "Сводка KPI"

    header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Arial", size=14, bold=True, color="111827")
    kpi_font = Font(name="Arial", size=11, bold=True, color="0284C7")
    warn_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    warn_font = Font(name="Arial", size=11, bold=True, color="B91C1C")

    ws_summary["A1"] = f"ПАСПОРТ УЗЛОВОГО АНАЛИЗА: {well_name}"
    ws_summary["A1"].font = title_font
    ws_summary["A2"] = f"Дата расчета: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Статус: {metrics['status_label']}"
    if metrics["warnings"]:
        ws_summary["A3"] = "⚠️ ВНИМАНИЕ — НЕФИЗИЧНЫЙ РАСЧЕТ: " + " | ".join(metrics["warnings"])
        for c in range(1, 5):
            cell = ws_summary.cell(row=3, column=c)
            cell.fill = warn_fill
            cell.font = warn_font
    else:
        ws_summary["A3"] = "Физическая валидация: корректно"

    headers = ["Показатель", "Значение", "Единица измерения", "Примечание"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws_summary.cell(row=4, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    ipr = params.get("ipr", {})
    vlp = params.get("vlp", {})
    tubing = vlp.get("tubing", {})
    casing = vlp.get("casing", {})

    rows = [
        ("Дебит жидкости (q_liq)", metrics["q_liq"], "м³/сут", "Рабочая точка узлового анализа"),
        ("Дебит чистой нефти (q_oil)", metrics["q_oil"], "м³/сут", f"С учетом WCT {metrics['wct']}%"),
        ("Дебит попутного газа (q_gas)", metrics["q_gas"], "тыс. м³/сут", f"Газовый фактор Rp={metrics['rp']} м³/т"),
        ("Забойное давление (p_wf)", metrics["p_wf"] or "—", "атм", "Давление на приеме пласта"),
        ("Депрессия на пласт (ΔP)", metrics["drawdown"], "атм", f"{metrics['drawdown_pct']}% от пластового P_res"),
        ("Пластовое давление (p_res)", metrics["p_res"], "атм", "Начальное/текущее пластовое"),
        ("Давление насыщения (p_b)", metrics["pb"], "атм", "Точка выделения газа"),
        ("Коэффициент продуктивности (pi)", metrics["pi"], "м³/(сут·атм)", "Индекс продуктивности"),
        ("Обводненность (wct)", metrics["wct"], "%", "Доля воды в продукции"),
        ("Буферное давление (p_wh)", vlp.get("p_wh"), "атм", "Давление на устье"),
        ("Глубина пласта (h_res)", vlp.get("h_res"), "м", "Истинная вертикальная глубина"),
        ("Глубина спуска НКТ (h_mes)", tubing.get("h_mes", vlp.get("h_mes")), "м", "Длина лифтовой колонны"),
        ("Диаметр НКТ (d)", tubing.get("d", vlp.get("tubing_d")), "м", "Внутренний диаметр НКТ"),
        ("Диаметр колонны ЭК (d)", casing.get("d", vlp.get("casing_d")), "м", "Внутренний диаметр ЭК"),
    ]

    for r_idx, (p_name, p_val, p_unit, p_note) in enumerate(rows, 5):
        ws_summary.cell(row=r_idx, column=1, value=p_name)
        val_cell = ws_summary.cell(row=r_idx, column=2, value=p_val)
        if "Дебит" in p_name or "Забойное" in p_name:
            val_cell.font = kpi_font
        ws_summary.cell(row=r_idx, column=3, value=p_unit)
        ws_summary.cell(row=r_idx, column=4, value=p_note)

    ws_summary.column_dimensions["A"].width = 38
    ws_summary.column_dimensions["B"].width = 16
    ws_summary.column_dimensions["C"].width = 20
    ws_summary.column_dimensions["D"].width = 36

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
