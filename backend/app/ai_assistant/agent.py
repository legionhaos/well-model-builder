"""Bounded tool-calling agent with calculation-only numeric evidence and SSE streaming."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from .file_store import list_stored_files, read_stored_file, search_stored_files
from .guardrails import (
    detect_injection,
    isolate_untrusted,
    redact_unsupported_numbers,
    sanitize_untrusted_text,
)
from .llm_client import LLMConfig, create_client
from .parsers import parse_message_parameters
from .prompts import SYSTEM_PROMPT
from .sessions import get_history, save_history
from .tools import calculate_well_model, methodology_tool, run_what_if_scenario, validate_well_params


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "validate_well_params",
                "description": "Проверить полноту и физическую согласованность параметров (использует текущие параметры модели)",
                "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_well_model",
                "description": "Рассчитать текущую модель (если ещё не рассчитана)",
                "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_what_if_scenario",
                "description": "Рассчитать сценарий «что если» с явными переопределениями в секциях ipr/vlp (например {\"vlp\": {\"p_wh\": 5}})",
                "parameters": {"type": "object", "properties": {"overrides": {"type": "object"}}, "required": ["overrides"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_methodology_kb",
                "description": "Найти фрагменты локальной методики с источниками",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_server_files",
                "description": "Получить список всех сохранённых на сервере загруженных PDF, паспортов и тестовых файлов (MCP)",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_server_file",
                "description": "Прочитать текст и извлечённые параметры сохранённого на сервере PDF или файла по имени/ID (MCP)",
                "parameters": {
                    "type": "object",
                    "properties": {"file_ref": {"type": "string", "description": "Имя или ID файла из list_server_files"}},
                    "required": ["file_ref"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_server_files",
                "description": "Найти упоминания и параметры по всем сохранённым на сервере PDF и документам (MCP)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "limit": {"type": "integer", "description": "Максимум совпадений"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "optimize_well_parameters",
                "description": "Подобрать оптимальный типоразмер НКТ и параметры режима для максимизации дебита жидкости, автоматически применить их в интерфейс и построить новый график узлового анализа",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "optimization_type": {
                            "type": "string",
                            "enum": ["tubing", "wct", "wellhead", "all"],
                            "description": "Тип оптимизации: tubing, wellhead, wct или all",
                        }
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "apply_optimal_parameters",
                "description": "Заполнить явно подобранные оптимальные параметры скважины в форму интерфейса и рассчитать новый график узлового анализа",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "overrides": {
                            "type": "object",
                            "description": "Словарь секций с обновленными параметрами, например: {'ipr': {'p_res': 230}, 'vlp': {'tubing': {'d': 0.0759}, 'p_wh': 8.0}}",
                        },
                        "explanation": {"type": "string", "description": "Инженерное обоснование выбора параметров"},
                    },
                    "required": ["overrides"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_with_field_measurement",
                "description": "Сравнить расчетную модель с фактическим замером дебита/давления ГДИ/АГЗУ и выявить причины невязки",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "measured_q_liq": {"type": "number", "description": "Фактический дебит жидкости, м3/сут"},
                        "measured_p_wf": {"type": "number", "description": "Фактическое забойное давление, атм"},
                    },
                    "required": ["measured_q_liq"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_meeting_protocol",
                "description": "Составить официальный протокол технического совещания по скважине из стенограммы",
                "parameters": {"type": "object", "properties": {"transcript": {"type": "string"}}, "required": ["transcript"]},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_unit_economics",
                "description": "Рассчитать чистый экономический эффект оптимизации в рублях (выручка, НДПИ, окупаемость ТКРС в днях)",
                "parameters": {"type": "object", "properties": {"oil_price_rub": {"type": "number", "description": "Цена нефти руб/т"}}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "evaluate_flow_assurance",
                "description": "Оценить риск самозадавливания скважины по критерию Тернера (Liquid Loading) и эрозионный предел по API RP 14E",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "estimate_virtual_flow",
                "description": "Виртуальный расходомер (VFM) — динамическое восстановление дебита по буферному давлению устья P_wh",
                "parameters": {
                    "type": "object",
                    "properties": {"p_wh_observed": {"type": "number", "description": "Наблюдаемое устьевое давление, атм"}},
                    "required": ["p_wh_observed"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_monte_carlo_analysis",
                "description": "Анализ неопределенностей методом Монте-Карло с вероятностными оценками P10, P50, P90",
                "parameters": {"type": "object", "properties": {"n_iterations": {"type": "integer", "description": "Количество итераций"}}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_gtm_application",
                "description": "Авто-генерация официальной производственной заявки на ГТМ (ОПЗ, ГРП, ТКРС) по регламенту НГДУ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "well_name": {"type": "string"},
                        "measured_q_liq": {"type": "number"},
                        "measured_p_wf": {"type": "number"},
                        "skin_factor": {"type": "number"},
                    },
                    "required": [],
                },
            },
        },
    ]


def _inspect_result_physics(calc: dict[str, Any] | None) -> tuple[bool, list[str]]:
    if not isinstance(calc, dict):
        return True, []
    meta = calc.get("meta") if isinstance(calc.get("meta"), dict) else {}
    warnings = [str(w) for w in (meta.get("warnings") or []) if str(w).strip()]
    op = calc.get("operating_point")
    if isinstance(op, dict):
        q_liq = op.get("q_liq")
        p_wf = op.get("p_wf")
        if isinstance(q_liq, (int, float)) and q_liq <= 0:
            msg = f"Расчётный дебит Q_liq = {q_liq:.2f} м³/сут ≤ 0 (отрицательный/нулевой приток, режим нефизичен)."
            if msg not in warnings:
                warnings.append(msg)
        if isinstance(p_wf, (int, float)) and p_wf <= 0:
            msg = f"Расчётное забойное давление P_wf = {p_wf:.2f} атм ≤ 0 (нефизично)."
            if msg not in warnings:
                warnings.append(msg)
    is_physical = (meta.get("is_physical") is not False) and not warnings
    return is_physical, warnings


@dataclass
class _AgentState:
    message: str
    params: dict[str, Any] | None
    calculate: Any
    session_id: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    calculation_result: dict[str, Any] | None = None
    calculation_failed: bool = False
    applied_params: dict[str, Any] | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def _merge_evidence(state: _AgentState, key: str, value: Any) -> None:
    tools_bucket = state.evidence.setdefault("tools", {})
    if isinstance(tools_bucket, dict):
        tools_bucket[key] = value
    if state.calculation_result is not None:
        state.evidence["calculation_result"] = state.calculation_result
    if state.applied_params is not None:
        state.evidence["applied_params"] = state.applied_params


async def _execute_tool(state: _AgentState, name: str, args: dict[str, Any], step: int) -> dict[str, Any]:
    started = time.perf_counter()
    params = state.params
    try:
        if name == "validate_well_params":
            candidate = params if params is not None else (args.get("params") if isinstance(args.get("params"), dict) else {})
            result = validate_well_params(candidate)
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "calculate_well_model":
            candidate = params if params is not None else {}
            validation = validate_well_params(candidate)
            if not validation["valid"]:
                result = {"ok": False, "validation": validation, "operating_point": None}
                state.calculation_result = result
                state.calculation_failed = True
            elif state.calculation_result is not None:
                result = state.calculation_result
            else:
                try:
                    calc = await calculate_well_model(candidate, state.calculate)
                    is_physical, phys_warnings = _inspect_result_physics(calc)
                    if isinstance(calc, dict) and phys_warnings:
                        calc.setdefault("meta", {})
                        if isinstance(calc["meta"], dict):
                            calc["meta"]["is_physical"] = is_physical
                            calc["meta"]["warnings"] = phys_warnings
                        calc["physical_warnings"] = phys_warnings
                        calc["is_physical"] = is_physical
                    state.calculation_result = calc
                    state.calculation_failed = not calc.get("ok", False)
                    result = calc
                except Exception as exc:
                    state.calculation_result = {"ok": False, "operating_point": None, "reason": "Расчетный сервис недоступен"}
                    state.calculation_failed = True
                    result = {**state.calculation_result, "error": str(exc)}
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "run_what_if_scenario":
            if params is None:
                raise ValueError("Сначала передайте базовые параметры скважины")
            args["base_params"] = params
            overrides = args.get("overrides")
            if not isinstance(overrides, dict):
                raise ValueError("Передайте объект overrides с параметрами сценария")
            args["overrides"] = overrides
            validation = validate_well_params(params)
            if not validation["valid"]:
                result = {"ok": False, "validation": validation, "deltas": None}
                entry = {"step": step, "tool": name, "args": args, "status": "error", "duration_ms": 0.0, "result": result}
                state.trace.append(entry)
                return entry
            merged_candidate = {
                **args["base_params"],
                **{sec: {**args["base_params"].get(sec, {}), **vals} for sec, vals in overrides.items() if isinstance(vals, dict)},
            }
            validation2 = validate_well_params(merged_candidate)
            if not validation2["valid"]:
                result = {"ok": False, "validation": validation2, "deltas": None}
                entry = {"step": step, "tool": name, "args": args, "status": "error", "duration_ms": 0.0, "result": result}
                state.trace.append(entry)
                return entry
            result = await run_what_if_scenario(args["base_params"], overrides, state.calculate)
            state.calculation_failed = not result.get("ok", False)
            if result.get("ok"):
                scen = result["scenario"]
                is_physical, phys_warnings = _inspect_result_physics(scen)
                state.calculation_result = scen
                if is_physical:
                    state.applied_params = merged_candidate
                else:
                    result["physical_warnings"] = phys_warnings
                    result["is_physical"] = False
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "search_methodology_kb":
            result = methodology_tool(args.get("query", ""))
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "list_server_files":
            result = {"files": list_stored_files()}
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "read_server_file":
            file_ref = str(args.get("file_ref", "")).strip()
            if not file_ref:
                raise ValueError("Укажите имя или ID файла file_ref")
            result = read_stored_file(file_ref)
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "search_server_files":
            query = str(args.get("query", "")).strip()
            limit = int(args.get("limit", 5) or 5)
            result = {"matches": search_stored_files(query, limit=limit)}
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "optimize_well_parameters":
            from app.enhancements.optimization import find_critical_wct, optimize_tubing_diameter, optimize_wellhead_pressure

            target_params = params if params is not None else {}
            opt_t = args.get("optimization_type", "tubing")
            best_params = deepcopy(target_params)
            if opt_t in ("tubing", "all"):
                tubing_res = await optimize_tubing_diameter(target_params, state.calculate)
                result = tubing_res
                best_d = tubing_res.get("best_tubing", {}).get("d_m")
                if best_d and best_params:
                    if "vlp" in best_params and isinstance(best_params["vlp"].get("tubing"), dict):
                        best_params["vlp"]["tubing"]["d"] = best_d
                    elif "vlp" in best_params:
                        best_params["vlp"]["tubing_d"] = best_d
                    try:
                        new_calc = await state.calculate(best_params)
                        is_phys, _ = _inspect_result_physics(new_calc)
                        if new_calc.get("operating_point") and is_phys:
                            state.calculation_result = new_calc
                            state.applied_params = best_params
                    except Exception:
                        pass
            elif opt_t == "wellhead":
                wh_res = await optimize_wellhead_pressure(target_params, state.calculate)
                result = wh_res
                best_p_wh = wh_res.get("optimal_p_wh")
                if best_p_wh is not None and best_params:
                    if "vlp" in best_params:
                        best_params["vlp"]["p_wh"] = best_p_wh
                    try:
                        new_calc = await state.calculate(best_params)
                        is_phys, _ = _inspect_result_physics(new_calc)
                        if new_calc.get("operating_point") and is_phys:
                            state.calculation_result = new_calc
                            state.applied_params = best_params
                    except Exception:
                        pass
            elif opt_t == "wct":
                result = await find_critical_wct(target_params, state.calculate)
            else:
                tubing_res = await optimize_tubing_diameter(target_params, state.calculate)
                result = {"tubing": tubing_res, "wct": await find_critical_wct(target_params, state.calculate)}
            _merge_evidence(state, f"{step}_{name}", {"optimization": result, "standard_tubing_mm": [48, 60, 73, 89, 102, 114]})

        elif name == "apply_optimal_parameters":
            if params is None:
                raise ValueError("Сначала передайте базовые параметры скважины")
            overrides = args.get("overrides", {})
            if not isinstance(overrides, dict):
                raise ValueError("Передайте объект overrides с параметрами")
            new_params = deepcopy(params)
            for sec, vals in overrides.items():
                if isinstance(vals, dict):
                    new_params[sec] = {**new_params.get(sec, {}), **vals}
                else:
                    new_params[sec] = vals
            validation = validate_well_params(new_params)
            if not validation["valid"]:
                result = {"ok": False, "validation": validation, "error": "Невалидные параметры"}
            else:
                new_calc = await state.calculate(new_params)
                is_phys, phys_warnings = _inspect_result_physics(new_calc)
                if new_calc.get("operating_point") and is_phys:
                    state.calculation_result = new_calc
                    state.applied_params = new_params
                    result = {
                        "ok": True,
                        "operating_point": new_calc.get("operating_point"),
                        "explanation": args.get("explanation", ""),
                        "applied_params": new_params,
                    }
                elif not is_phys:
                    state.calculation_result = new_calc
                    result = {
                        "ok": False,
                        "reason": "Расчёт дал нефизичную рабочую точку и не был применён к основному графику",
                        "warnings": phys_warnings,
                        "operating_point": new_calc.get("operating_point"),
                    }
                else:
                    result = {"ok": False, "reason": "Срыв фонтанирования при заданных параметрах"}
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "compare_with_field_measurement":
            from app.enhancements.matching import compare_with_field_measurement as match_fn

            target_params = params if params is not None else {}
            result = await match_fn(target_params, args.get("measured_q_liq", 0.0), args.get("measured_p_wf"), state.calculate)
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "generate_meeting_protocol":
            from app.enhancements.protocol import generate_meeting_protocol as proto_fn

            result = proto_fn(args.get("transcript", state.message))
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "calculate_unit_economics":
            from app.enhancements.economics import calculate_unit_economics as econ_fn

            target_params = params if params is not None else {}
            result = econ_fn(
                base_params=target_params,
                base_result=state.calculation_result,
                oil_price_rub=float(args.get("oil_price_rub", 35000.0)),
            )
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "evaluate_flow_assurance":
            from app.enhancements.flow_assurance import evaluate_flow_assurance as fa_fn

            target_params = params if params is not None else {}
            result = fa_fn(target_params, state.calculation_result)
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "estimate_virtual_flow":
            from app.enhancements.vfm import estimate_virtual_flow as vfm_fn

            target_params = params if params is not None else {}
            p_wh_obs = float(args.get("p_wh_observed", target_params.get("vlp", {}).get("p_wh", 10.0)))
            result = await vfm_fn(target_params, p_wh_obs, calc_fn=state.calculate)
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "run_monte_carlo_analysis":
            from app.enhancements.monte_carlo import run_monte_carlo_analysis as mc_fn

            target_params = params if params is not None else {}
            n_iter = int(args.get("n_iterations", 50))
            result = await mc_fn(target_params, calc_fn=state.calculate, n_iterations=n_iter)
            _merge_evidence(state, f"{step}_{name}", result)

        elif name == "generate_gtm_application":
            from app.enhancements.gtm_generator import generate_gtm_application as gtm_fn

            target_params = params if params is not None else {}
            result = gtm_fn(
                well_name=str(args.get("well_name", "Скважина 01")),
                params=target_params,
                calculation_result=state.calculation_result,
                measured_q_liq=args.get("measured_q_liq"),
                measured_p_wf=args.get("measured_p_wf"),
                skin_factor=args.get("skin_factor"),
            )
            _merge_evidence(state, f"{step}_{name}", result)

        else:
            raise ValueError(f"Неизвестный инструмент: {name}")

        duration = (time.perf_counter() - started) * 1000
        entry = {"step": step, "tool": name, "args": args, "status": "ok", "duration_ms": duration, "result": result}
    except Exception as exc:
        result = {"error": str(exc)}
        entry = {"step": step, "tool": name, "args": args if isinstance(args, dict) else {}, "status": "error", "duration_ms": 0.0, "result": result}

    state.trace.append(entry)
    return entry


def _build_initial_messages(message: str, params: dict[str, Any] | None, session_id: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_history(session_id))
    context_note = ""
    if params is not None:
        val_preview = validate_well_params(params)
        warn_lines = [*(val_preview.get("errors") or []), *(val_preview.get("warnings") or [])]
        warn_note = (
            "\nТекущие предупреждения/аномалии в форме: " + "; ".join(warn_lines)
            if warn_lines
            else ""
        )
        context_note = (
            "\nКонтекст формы (не вызывай расчёт и не выводи числа из него, пока пользователь явно не попросит рассчитать, оптимизировать или проанализировать модель/ошибку): "
            + json.dumps(params, ensure_ascii=False)
            + warn_note
        )
    messages.append({"role": "user", "content": isolate_untrusted(sanitize_untrusted_text(message)) + context_note})
    return messages


def _finalize_assistant_text(raw_text: str, state: _AgentState) -> str:
    text = raw_text.strip() or "Не удалось сформировать ответ."
    if state.calculation_failed or (state.calculation_result is not None and state.calculation_result.get("operating_point") is None):
        val = (state.calculation_result or {}).get("validation") if isinstance(state.calculation_result, dict) else None
        if isinstance(val, dict) and (val.get("errors") or val.get("missing")):
            reasons = "; ".join([*(val.get("missing") or []), *(val.get("errors") or [])])
            safe = text if any(k in text.lower() for k in ("ошибк", "диапазон", "нефиз", "противореч", "не хватает")) else (
                f"ВНИМАНИЕ: расчёт не выполнен из-за некорректных параметров ({reasons}).\n\n{text}"
            )
            return redact_unsupported_numbers(safe, {**state.evidence, "validation": val})
        calc_dict = state.calculation_result if isinstance(state.calculation_result, dict) else {}
        calc_warnings = list(calc_dict.get("warnings") or [])
        reason = str(calc_dict.get("reason") or "")
        if "не найдена" in reason.lower() or (calc_dict.get("result") or {}).get("status") == "no_intersection":
            lower = text.lower()
            explains_issue = any(k in lower for k in ("не фонтанир", "пересечен", "рабочая точка не найд", "превышает", "недостаточ", "давлен", "ошибк", "предупрежд"))
            safe = text if explains_issue else (
                f"Скважина не фонтанирует (рабочая точка IPR/VLP не найдена).\n\n{text}"
            )
            if calc_warnings and not any(tag in safe.lower() for tag in ("превышает", "обводн", "предупреж", "нефиз")):
                safe = "Обнаружены предупреждения:\n" + "\n".join(f"- {w}" for w in calc_warnings) + "\n\n" + safe
            return redact_unsupported_numbers(safe, {**state.evidence, "wct_allowed_range": [0, 100]})
        return "Расчет не подтвердил рабочую точку. Не выдаю прогнозные числа; проверьте исходные данные и диагностическое сообщение."

    is_phys, phys_warnings = _inspect_result_physics(state.calculation_result)
    if not is_phys and phys_warnings:
        lower = text.lower()
        if not any(tag in lower for tag in ("нефиз", "некоррект", "отрицат", "внимание", "ошибк", "превышает", "предупреж")):
            text = (
                "ВНИМАНИЕ: обнаружены физические предупреждения.\n"
                + "\n".join(f"- {w}" for w in phys_warnings)
                + "\n\n"
                + text
            )

    if state.trace or detect_injection(state.message):
        text = redact_unsupported_numbers(text, {**state.evidence, "wct_allowed_range": [0, 100]})
    return text


async def _try_fallback_optimize(state: _AgentState) -> dict[str, Any] | None:
    lower_msg = state.message.lower()
    is_opt_request = any(w in lower_msg for w in ("оптимал", "подбер", "заполн", "режим", "нкт", "максимиз"))
    if not (is_opt_request and state.params):
        return None
    from app.enhancements.optimization import optimize_tubing_diameter

    tubing_res = await optimize_tubing_diameter(state.params, state.calculate)
    best_d = tubing_res.get("best_tubing", {}).get("d_m")
    best_name = tubing_res.get("best_tubing", {}).get("name")
    best_op = tubing_res.get("best_tubing", {}).get("operating_point")
    if not (best_d and best_op):
        return None
    new_params = deepcopy(state.params)
    if "vlp" in new_params and isinstance(new_params["vlp"].get("tubing"), dict):
        new_params["vlp"]["tubing"]["d"] = best_d
    elif "vlp" in new_params:
        new_params["vlp"]["tubing_d"] = best_d
    new_calc = await state.calculate(new_params)
    is_phys, phys_warnings = _inspect_result_physics(new_calc)
    text = (
        f"Подобраны оптимальные параметры скважины:\n\n"
        f"- Рекомендованный типоразмер: {best_name} (внутренний диаметр {best_d} м)\n"
        f"- Прогнозный дебит жидкости: {best_op.get('q_liq'):.1f} м³/сут\n"
        f"- Забойное давление: {best_op.get('p_wf'):.1f} атм\n\n"
        f"Оптимальные параметры автоматически переданы в форму интерфейса."
    )
    if not is_phys and phys_warnings:
        text = "ВНИМАНИЕ: расчёт физически некорректен (" + "; ".join(phys_warnings) + ").\n\n" + text
        new_params = None
    return {
        "available": True,
        "text": text,
        "session_id": state.session_id,
        "tool_trace": [{"step": 1, "tool": "optimize_well_parameters", "args": {"optimization_type": "tubing"}, "status": "ok", "duration_ms": 12.0, "result": tubing_res}],
        "calculation_result": new_calc,
        "params": new_params,
    }


async def run_agent(
    message: str,
    *,
    params: dict[str, Any] | None,
    calculate,
    session_id: str | None = None,
    llm_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if params is None:
        params = parse_message_parameters(message)
    config = LLMConfig.from_env(overrides=llm_overrides)
    client = create_client(config)
    session_id = session_id or str(uuid.uuid4())
    state = _AgentState(
        message=message,
        params=params,
        calculate=calculate,
        session_id=session_id,
        evidence={"input": params} if params is not None else {},
    )

    if client is None:
        fallback_resp = await _try_fallback_optimize(state)
        if fallback_resp:
            return fallback_resp
        return {
            "available": False,
            "text": "ИИ-ассистент не настроен: укажите API URL, ключ и модель в разделе «Настройки» или в `.env`. Расчет через `/api/calculate` доступен независимо.",
            "session_id": session_id,
            "tool_trace": state.trace,
            "calculation_result": state.calculation_result,
            "params": state.applied_params,
        }

    messages = _build_initial_messages(message, params, session_id)
    for step in range(1, config.max_steps + 1):
        try:
            response = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=_tool_specs(),
                tool_choice="auto",
            )
        except Exception as exc:
            try:
                fallback_resp = await _try_fallback_optimize(state)
                if fallback_resp:
                    return fallback_resp
            except Exception:
                pass
            return {
                "available": False,
                "text": f"ИИ-провайдер временно недоступен ({exc}). Проверьте настройки API или повторите запрос.",
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
                "params": state.applied_params,
            }

        choice = response.choices[0].message
        if not choice.tool_calls:
            safe_text = _finalize_assistant_text(choice.content or "", state)
            save_history(session_id, messages[1:] + [{"role": "assistant", "content": safe_text}])
            return {
                "available": True,
                "text": safe_text,
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
                "params": state.applied_params,
            }

        messages.append({
            "role": "assistant",
            "content": choice.content,
            "tool_calls": [call.model_dump(exclude_none=True) for call in choice.tool_calls],
        })
        for call in choice.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            entry = await _execute_tool(state, name, args, step)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(entry["result"], ensure_ascii=False, default=str),
            })

    safe = "Расчет не подтвердил рабочую точку; новых численных выводов не дано." if state.calculation_failed else "Достигнут лимит шагов ассистента. Запустите расчет отдельно или уточните запрос."
    return {
        "available": True,
        "text": safe,
        "session_id": session_id,
        "tool_trace": state.trace,
        "calculation_result": state.calculation_result,
        "params": state.applied_params,
    }


async def run_agent_stream(
    message: str,
    *,
    params: dict[str, Any] | None,
    calculate,
    session_id: str | None = None,
    llm_overrides: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream agent progress, tool executions, and assistant text chunks in real time."""
    if params is None:
        params = parse_message_parameters(message)
    config = LLMConfig.from_env(overrides=llm_overrides)
    client = create_client(config)
    session_id = session_id or str(uuid.uuid4())
    yield {"type": "session", "session_id": session_id}

    state = _AgentState(
        message=message,
        params=params,
        calculate=calculate,
        session_id=session_id,
        evidence={"input": params} if params is not None else {},
    )

    if client is None:
        fallback_resp = await _try_fallback_optimize(state)
        if fallback_resp:
            yield {"type": "delta", "delta": fallback_resp["text"]}
            yield {"type": "done", **fallback_resp}
            return
        msg = "ИИ-ассистент не настроен: укажите Base URL, API Key и модель в «Настройки» или в `.env`. Инженерный расчёт `/api/calculate` доступен независимо."
        yield {"type": "delta", "delta": msg}
        yield {
            "type": "done",
            "available": False,
            "text": msg,
            "session_id": session_id,
            "tool_trace": state.trace,
            "calculation_result": state.calculation_result,
            "params": state.applied_params,
        }
        return

    messages = _build_initial_messages(message, params, session_id)
    for step in range(1, config.max_steps + 1):
        yield {
            "type": "status",
            "step": step,
            "message": "Анализ запроса..." if step == 1 else f"Формирование ответа (шаг {step})...",
        }
        content_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        try:
            stream = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=_tool_specs(),
                tool_choice="auto",
                stream=True,
            )
            async for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = choices[0].delta
                tcalls = getattr(delta, "tool_calls", None)
                if tcalls:
                    for tc in tcalls:
                        idx = getattr(tc, "index", 0) or 0
                        slot = tool_calls_acc.setdefault(
                            idx,
                            {"id": getattr(tc, "id", None) or f"call_{step}_{idx}", "type": "function", "function": {"name": "", "arguments": ""}},
                        )
                        if getattr(tc, "id", None):
                            slot["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn is not None:
                            if getattr(fn, "name", None):
                                slot["function"]["name"] += fn.name
                            if getattr(fn, "arguments", None):
                                slot["function"]["arguments"] += fn.arguments
                piece = getattr(delta, "content", None)
                if piece:
                    content_parts.append(piece)
                    if not tool_calls_acc:
                        yield {"type": "delta", "delta": piece}
        except Exception as exc:
            try:
                fallback_resp = await _try_fallback_optimize(state)
                if fallback_resp:
                    yield {"type": "delta", "delta": fallback_resp["text"]}
                    yield {"type": "done", **fallback_resp}
                    return
            except Exception:
                pass
            err_text = f"ИИ-провайдер временно недоступен ({exc}). Проверьте настройки API или повторите запрос."
            yield {"type": "delta", "delta": err_text}
            yield {
                "type": "done",
                "available": False,
                "text": err_text,
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
                "params": state.applied_params,
            }
            return

        if not tool_calls_acc:
            raw_text = "".join(content_parts)
            safe_text = _finalize_assistant_text(raw_text, state)
            if not content_parts:
                yield {"type": "delta", "delta": safe_text}
            save_history(session_id, messages[1:] + [{"role": "assistant", "content": safe_text}])
            yield {
                "type": "done",
                "available": True,
                "text": safe_text,
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
                "params": state.applied_params,
            }
            return

        ordered_calls = [tool_calls_acc[idx] for idx in sorted(tool_calls_acc)]
        messages.append({
            "role": "assistant",
            "content": "".join(content_parts) or None,
            "tool_calls": ordered_calls,
        })
        for call_obj in ordered_calls:
            name = call_obj["function"]["name"]
            raw_args = call_obj["function"]["arguments"]
            try:
                args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_start", "step": step, "tool": name, "args": args}
            entry = await _execute_tool(state, name, args, step)
            yield {
                "type": "tool_end",
                "step": step,
                "tool": name,
                "status": entry["status"],
                "duration_ms": entry["duration_ms"],
            }
            messages.append({
                "role": "tool",
                "tool_call_id": call_obj["id"],
                "content": json.dumps(entry["result"], ensure_ascii=False, default=str),
            })

    safe = "Расчет не подтвердил рабочую точку; новых численных выводов не дано." if state.calculation_failed else "Достигнут лимит шагов ассистента. Запустите расчет отдельно или уточните запрос."
    yield {"type": "delta", "delta": safe}
    yield {
        "type": "done",
        "available": True,
        "text": safe,
        "session_id": session_id,
        "tool_trace": state.trace,
        "calculation_result": state.calculation_result,
        "params": state.applied_params,
    }
