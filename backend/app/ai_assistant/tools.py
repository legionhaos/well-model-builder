"""Deterministic tools available to the optional assistant."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .rag import search_methodology_kb

REQUIRED_IPR = ("p_res", "wct", "pi", "pb")
REQUIRED_VLP_BASE = ("p_wh", "geo_grad", "h_res", "tubing", "casing", "pvt")


def validate_well_params(params: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    errors: list[str] = []
    ipr = params.get("ipr")
    vlp = params.get("vlp")
    if not isinstance(ipr, dict):
        missing.append("ipr")
        ipr = {}
    if not isinstance(vlp, dict):
        missing.append("vlp")
        vlp = {}
    missing.extend(f"ipr.{key}" for key in REQUIRED_IPR if key not in ipr)
    missing.extend(f"vlp.{key}" for key in REQUIRED_VLP_BASE if key not in vlp)

    # Проверка h_mes (может быть в vlp или в vlp.tubing)
    h_mes = vlp.get("h_mes")
    if h_mes is None and isinstance(vlp.get("tubing"), dict):
        h_mes = vlp["tubing"].get("h_mes")
    if h_mes is None:
        missing.append("vlp.h_mes")

    # Проверка MD и TVD (могут быть в vlp или в vlp.inclinometry)
    inclinometry = vlp.get("inclinometry") if isinstance(vlp.get("inclinometry"), dict) else {}
    md = vlp.get("MD") or inclinometry.get("MD")
    tvd = vlp.get("TVD") or inclinometry.get("TVD")
    if md is None:
        missing.append("vlp.MD")
    if tvd is None:
        missing.append("vlp.TVD")

    pvt = vlp.get("pvt")
    if not isinstance(pvt, dict):
        if "vlp.pvt" not in missing:
            missing.append("vlp.pvt")
    else:
        missing.extend(f"vlp.pvt.{key}" for key in ("wct", "rp", "gamma_oil", "gamma_gas", "gamma_wat") if key not in pvt)
    for section, value in (("ipr", ipr), ("vlp.pvt", pvt if isinstance(pvt, dict) else {})):
        if "wct" in value:
            try:
                if not 0 <= float(value["wct"]) <= 100:
                    errors.append(f"{section}.wct должен быть в диапазоне 0..100")
            except (TypeError, ValueError):
                errors.append(f"{section}.wct должен быть числом")
    if "wct" in ipr and isinstance(pvt, dict) and "wct" in pvt:
        try:
            if float(ipr["wct"]) != float(pvt["wct"]):
                errors.append("ipr.wct и vlp.pvt.wct должны совпадать")
        except (TypeError, ValueError):
            errors.append("ipr.wct и vlp.pvt.wct должны быть числами")
    for section, values in (("ipr", ipr), ("vlp", vlp), ("vlp.pvt", pvt if isinstance(pvt, dict) else {})):
        for key in values:
            if key in {"p_res", "p_wh", "h_res", "h_mes", "geo_grad", "pi", "pb"}:
                try:
                    number = float(values[key])
                    if not math.isfinite(number):
                        errors.append(f"{section}.{key} должен быть конечным числом")
                    elif key in {"p_res", "p_wh", "h_res"} and number <= 0:
                        errors.append(f"{section}.{key} должен быть больше нуля")
                    elif key in {"h_mes", "pi", "pb", "geo_grad"} and number < 0:
                        errors.append(f"{section}.{key} не может быть отрицательным")
                except (TypeError, ValueError):
                    errors.append(f"{section}.{key} должен быть числом")
    if "tubing" in vlp and "casing" in vlp:
        try:
            if float(vlp["casing"]["d"]) <= float(vlp["tubing"]["d"]):
                errors.append("Диаметр casing.d должен быть больше tubing.d")
        except (KeyError, TypeError, ValueError):
            errors.append("Не заданы числовые tubing.d и casing.d")
    if md is not None and tvd is not None:
        if not isinstance(md, list) or not isinstance(tvd, list) or len(md) != len(tvd) or len(md) < 2:
            errors.append("MD и TVD должны быть списками одинаковой длины (не менее 2)")
        else:
            try:
                if any(b <= a for a, b in zip(md, md[1:])):
                    errors.append("MD должен строго возрастать")
                if any(b < a for a, b in zip(tvd, tvd[1:])):
                    errors.append("TVD не должен убывать")
                if "h_res" in vlp and float(vlp["h_res"]) > max(md):
                    errors.append("h_res не должен превышать max(MD)")
                if h_mes is not None and "h_res" in vlp and float(h_mes) >= float(vlp["h_res"]):
                    errors.append("h_mes должен быть меньше h_res")
            except (TypeError, ValueError):
                errors.append("MD и TVD должны содержать числа")

    warnings: list[str] = []
    if not missing and not errors:
        try:
            from ..orchestrator.router import inspect_physical_warnings

            vlp_norm = deepcopy(vlp)
            if isinstance(vlp_norm, dict) and "h_mes" in vlp_norm and isinstance(vlp_norm.get("tubing"), dict):
                vlp_norm["tubing"].setdefault("h_mes", vlp_norm["h_mes"])
            warnings = inspect_physical_warnings(ipr, vlp_norm if isinstance(vlp_norm, dict) else {}, {})
        except Exception:
            warnings = []
        try:
            wct_val = float(ipr.get("wct"))
            if 98.0 <= wct_val <= 100.0:
                msg = f"Критически высокая обводнённость WCT = {wct_val:g}%: доля нефти близка к нулю."
                if msg not in warnings:
                    warnings.append(msg)
        except (TypeError, ValueError):
            pass

    return {
        "valid": not missing and not errors,
        "is_physical": (not missing and not errors and len(warnings) == 0),
        "missing": missing,
        "errors": errors,
        "warnings": warnings,
        "wct_allowed_range": [0, 100],
    }


async def calculate_well_model(params: dict[str, Any], calculate) -> dict[str, Any]:
    validation = validate_well_params(params)
    if not validation["valid"]:
        return {"ok": False, "validation": validation, "operating_point": None}

    # Приводим к структуре /api/calculate
    calc_params = deepcopy(params)
    vlp = calc_params.get("vlp", {})
    if isinstance(vlp, dict):
        if "inclinometry" not in vlp and "MD" in vlp and "TVD" in vlp:
            vlp["inclinometry"] = {"MD": vlp["MD"], "TVD": vlp["TVD"]}
        if isinstance(vlp.get("tubing"), dict) and "h_mes" in vlp and "h_mes" not in vlp["tubing"]:
            vlp["tubing"]["h_mes"] = vlp["h_mes"]

    result = await calculate(calc_params)
    if not isinstance(result, dict) or result.get("operating_point") is None:
        raw_warnings = list(validation.get("warnings") or [])
        if isinstance(result, dict):
            for w in result.get("warnings") or []:
                if w not in raw_warnings:
                    raw_warnings.append(w)
        return {
            "ok": False,
            "result": result,
            "operating_point": None,
            "warnings": raw_warnings,
            "is_physical": len(raw_warnings) == 0,
            "reason": "Рабочая точка не найдена (кривая VLP лежит выше кривой IPR — скважина не фонтанирует)",
        }
    return {"ok": True, **result}


async def run_what_if_scenario(base_params: dict[str, Any], overrides: dict[str, Any], calculate) -> dict[str, Any]:
    changed = deepcopy(base_params)
    for section, values in overrides.items():
        if section not in changed or not isinstance(changed[section], dict) or not isinstance(values, dict):
            raise ValueError("Переопределения должны содержать существующие секции параметров")
        unexpected = set(values) - set(changed[section])
        if unexpected:
            raise ValueError("Переопределения содержат неизвестные параметры")
        changed[section].update(values)
    before, after = await calculate_well_model(base_params, calculate), await calculate_well_model(changed, calculate)
    old, new = before.get("operating_point"), after.get("operating_point")
    if not before.get("ok") or not after.get("ok") or not old or not new:
        return {"ok": False, "base": before, "scenario": after, "deltas": None}
    dq, dp = new["q_liq"] - old["q_liq"], new["p_wf"] - old["p_wf"]
    return {"ok": True, "base": before, "scenario": after, "deltas": {"q_liq": dq, "q_liq_percent": dq / old["q_liq"] * 100 if old["q_liq"] else None, "p_wf": dp, "p_wf_percent": dp / old["p_wf"] * 100 if old["p_wf"] else None}}


def methodology_tool(query: str) -> list[dict[str, Any]]:
    return search_methodology_kb(query)
