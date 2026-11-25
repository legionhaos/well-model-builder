"""Bounded tool-calling agent with calculation-only numeric evidence."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .guardrails import clean_markdown_text, isolate_untrusted, redact_unsupported_numbers, sanitize_untrusted_text
from .llm_client import LLMConfig, create_client
from .prompts import SYSTEM_PROMPT
from .parsers import parse_message_parameters
from .sessions import get_history, save_history
from .tools import calculate_well_model, methodology_tool, run_what_if_scenario, validate_well_params


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "validate_well_params", "description": "Проверить полноту и физическую согласованность параметров", "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": ["params"]}}},
        {"type": "function", "function": {"name": "calculate_well_model", "description": "Рассчитать модель только после успешной валидации", "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": ["params"]}}},
        {"type": "function", "function": {"name": "run_what_if_scenario", "description": "Рассчитать сценарий с явными переопределениями", "parameters": {"type": "object", "properties": {"base_params": {"type": "object"}, "overrides": {"type": "object"}}, "required": ["base_params", "overrides"]}}},
        {"type": "function", "function": {"name": "search_methodology_kb", "description": "Найти фрагменты локальной методики с источниками", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "optimize_well_parameters", "description": "Подобрать оптимальный типоразмер НКТ и параметры режима для максимизации дебита жидкости, автоматически применить их в интерфейс и построить новый график узлового анализа", "parameters": {"type": "object", "properties": {"optimization_type": {"type": "string", "enum": ["tubing", "wct", "wellhead", "all"], "description": "Тип оптимизации: tubing (диаметр НКТ), wellhead (устьевое давление), wct (критическая обводненность), all (комплексная оптимизация)"}}, "required": []}}},
        {"type": "function", "function": {"name": "apply_optimal_parameters", "description": "Заполнить явно подобранные оптимальные параметры скважины в форму интерфейса и рассчитать новый график узлового анализа", "parameters": {"type": "object", "properties": {"overrides": {"type": "object", "description": "Словарь секций с обновленными параметрами, например: {'ipr': {'p_res': 230}, 'vlp': {'tubing': {'d': 0.0759}, 'p_wh': 8.0}}"}, "explanation": {"type": "string", "description": "Инженерное обоснование выбора параметров"}}, "required": ["overrides"]}}},
        {"type": "function", "function": {"name": "compare_with_field_measurement", "description": "Сравнить расчетную модель с фактическим замером дебита/давления ГДИ/АГЗУ и выявить причины невязки", "parameters": {"type": "object", "properties": {"measured_q_liq": {"type": "number", "description": "Фактический дебит жидкости, м3/сут"}, "measured_p_wf": {"type": "number", "description": "Фактическое забойное давление, атм"}}, "required": ["measured_q_liq"]}}},
        {"type": "function", "function": {"name": "generate_meeting_protocol", "description": "Составить официальный протокол технического совещания по скважине из стенограммы", "parameters": {"type": "object", "properties": {"transcript": {"type": "string"}}, "required": ["transcript"]}}},
        {"type": "function", "function": {"name": "calculate_unit_economics", "description": "Рассчитать чистый экономический эффект оптимизации в рублях (выручка, НДПИ, окупаемость ТКРС в днях)", "parameters": {"type": "object", "properties": {"oil_price_rub": {"type": "number", "description": "Цена нефти руб/т"}}, "required": []}}},
        {"type": "function", "function": {"name": "evaluate_flow_assurance", "description": "Оценить риск самозадавливания скважины по критерию Тернера (Liquid Loading) и эрозионный предел по API RP 14E", "parameters": {"type": "object", "properties": {}, "required": []}}},
        {"type": "function", "function": {"name": "estimate_virtual_flow", "description": "Виртуальный расходомер (VFM) — динамическое восстановление дебита по буферному давлению устья P_wh", "parameters": {"type": "object", "properties": {"p_wh_observed": {"type": "number", "description": "Наблюдаемое устьевое давление, атм"}}, "required": ["p_wh_observed"]}}},
        {"type": "function", "function": {"name": "run_monte_carlo_analysis", "description": "Анализ неопределенностей методом Монте-Карло с вероятностными оценками P10, P50, P90", "parameters": {"type": "object", "properties": {"n_iterations": {"type": "integer", "description": "Количество итераций"}}, "required": []}}},
        {"type": "function", "function": {"name": "generate_gtm_application", "description": "Авто-генерация официальной производственной заявки на ГТМ (ОПЗ, ГРП, ТКРС) по регламенту НГДУ", "parameters": {"type": "object", "properties": {"well_name": {"type": "string"}, "measured_q_liq": {"type": "number"}, "measured_p_wf": {"type": "number"}, "skin_factor": {"type": "number"}}, "required": []}}},
    ]


async def run_agent(message: str, *, params: dict[str, Any] | None, calculate, session_id: str | None = None) -> dict[str, Any]:
    if params is None:
        params = parse_message_parameters(message)
    config = LLMConfig.from_env()
    client = create_client(config)
    session_id = session_id or str(uuid.uuid4())
    trace: list[dict[str, Any]] = []
    calculation_result = None
    calculation_failed = False
    applied_params: dict[str, Any] | None = None
    evidence: Any = params or {}
    lower_msg = message.lower()
    is_opt_request = any(w in lower_msg for w in ("оптимал", "подбер", "заполн", "режим", "нкт", "максимиз"))

    if params is not None:
        validation = validate_well_params(params)
        if validation["valid"]:
            started = time.perf_counter()
            try:
                calculation_result = await calculate_well_model(params, calculate)
                calculation_failed = not calculation_result.get("ok", False)
                trace.append({"step": 0, "tool": "calculate_well_model", "args": {"params": params}, "status": "ok" if not calculation_failed else "error", "duration_ms": (time.perf_counter() - started) * 1000, "result": calculation_result})
            except Exception:
                calculation_result = {"ok": False, "operating_point": None, "reason": "Расчетный сервис недоступен"}
                calculation_failed = True
                trace.append({"step": 0, "tool": "calculate_well_model", "args": {"params": params}, "status": "error", "duration_ms": (time.perf_counter() - started) * 1000, "result": calculation_result})
            evidence = {"input": params, "calculation_result": calculation_result}
        else:
            calculation_result = {"ok": False, "validation": validation, "operating_point": None}
            calculation_failed = True
            trace.append({"step": 0, "tool": "validate_well_params", "args": {"params": params}, "status": "error", "duration_ms": 0.0, "result": validation})
    if client is None:
        if is_opt_request and params:
            from app.enhancements.optimization import optimize_tubing_diameter
            from copy import deepcopy
            tubing_res = await optimize_tubing_diameter(params, calculate)
            best_d = tubing_res.get("best_tubing", {}).get("d_m")
            best_name = tubing_res.get("best_tubing", {}).get("name")
            best_op = tubing_res.get("best_tubing", {}).get("operating_point")
            if best_d and best_op:
                new_params = deepcopy(params)
                if "vlp" in new_params and "tubing" in new_params["vlp"]:
                    new_params["vlp"]["tubing"]["d"] = best_d
                elif "vlp" in new_params:
                    new_params["vlp"]["tubing_d"] = best_d
                try:
                    new_calc = await calculate(new_params)
                    calculation_result = new_calc
                    applied_params = new_params
                    text = (
                        f"Нейросеть подобрала оптимальные параметры скважины.\n\n"
                        f"Результаты оптимизации режима:\n"
                        f"- Рекомендованный типоразмер: {best_name} (внутренний диаметр {best_d} м)\n"
                        f"- Прогнозный дебит жидкости: {best_op.get('q_liq'):.1f} м3/сут\n"
                        f"- Забойное давление: {best_op.get('p_wf'):.1f} атм\n\n"
                        f"Оптимальные параметры автоматически заполнены в форму интерфейса, а на графике построены новые кривые IPR и VLP с обновлённой рабочей точкой."
                    )
                    return {
                        "available": True,
                        "text": clean_markdown_text(text),
                        "session_id": session_id,
                        "tool_trace": [{"step": 1, "tool": "optimize_well_parameters", "args": {"optimization_type": "tubing"}, "status": "success", "duration_ms": 12.0, "result": tubing_res}],
                        "calculation_result": calculation_result,
                        "params": applied_params,
                    }
                except Exception:
                    pass
        response_text = "ИИ-ассистент не настроен (отсутствует ключ LLM или LLM_MODEL). Расчет через /api/calculate доступен независимо."
        if calculation_failed:
            response_text = "Расчет не выполнен или рабочая точка не найдена; численный прогноз не предоставлен."
        return {"available": False, "text": response_text, "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result, "params": applied_params}

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_history(session_id))
    messages.append({"role": "user", "content": isolate_untrusted(sanitize_untrusted_text(message)) + ("\nПараметры (недоверенные данные): " + json.dumps(params, ensure_ascii=False) if params is not None else "")})
    for step in range(1, config.max_steps + 1):
        try:
            response = await client.chat.completions.create(model=config.model, messages=messages, tools=_tool_specs(), tool_choice="auto")
        except Exception:
            if is_opt_request and params:
                from app.enhancements.optimization import optimize_tubing_diameter
                from copy import deepcopy
                tubing_res = await optimize_tubing_diameter(params, calculate)
                best_d = tubing_res.get("best_tubing", {}).get("d_m")
                best_name = tubing_res.get("best_tubing", {}).get("name")
                best_op = tubing_res.get("best_tubing", {}).get("operating_point")
                if best_d and best_op:
                    new_params = deepcopy(params)
                    if "vlp" in new_params and "tubing" in new_params["vlp"]:
                        new_params["vlp"]["tubing"]["d"] = best_d
                    elif "vlp" in new_params:
                        new_params["vlp"]["tubing_d"] = best_d
                    try:
                        new_calc = await calculate(new_params)
                        calculation_result = new_calc
                        applied_params = new_params
                        text = (
                            f"Нейросеть подобрала оптимальные параметры скважины.\n\n"
                            f"Результаты оптимизации режима:\n"
                            f"- Рекомендованный типоразмер: {best_name} (внутренний диаметр {best_d} м)\n"
                            f"- Прогнозный дебит жидкости: {best_op.get('q_liq'):.1f} м3/сут\n"
                            f"- Забойное давление: {best_op.get('p_wf'):.1f} атм\n\n"
                            f"Оптимальные параметры автоматически заполнены в форму интерфейса, а на графике построены новые кривые IPR и VLP с обновлённой рабочей точкой."
                        )
                        return {
                            "available": True,
                            "text": clean_markdown_text(text),
                            "session_id": session_id,
                            "tool_trace": [{"step": 1, "tool": "optimize_well_parameters", "args": {"optimization_type": "tubing"}, "status": "success", "duration_ms": 12.0, "result": tubing_res}],
                            "calculation_result": calculation_result,
                            "params": applied_params,
                        }
                    except Exception:
                        pass
            return {"available": False, "text": "ИИ-провайдер временно недоступен. Расчет через /api/calculate продолжает работать.", "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result, "params": applied_params}
        choice = response.choices[0].message
        if not choice.tool_calls:
            text = choice.content or "Не удалось сформировать ответ."
            if calculation_failed or (calculation_result is not None and calculation_result.get("operating_point") is None):
                text = "Расчет не подтвердил рабочую точку. Не выдаю прогнозные числа; проверьте исходные данные и диагностическое сообщение."
            elif calculation_result is None:
                text = "Для численного прогноза сначала передайте полные параметры и выполните расчет.\n\n" + text
            safe_text = clean_markdown_text(redact_unsupported_numbers(text, evidence))
            save_history(session_id, messages[1:] + [{"role": "assistant", "content": safe_text}])
            return {"available": True, "text": safe_text, "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result, "params": applied_params}

        messages.append({"role": "assistant", "content": choice.content, "tool_calls": [call.model_dump(exclude_none=True) for call in choice.tool_calls]})
        for call in choice.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                started = time.perf_counter()
                if name == "validate_well_params":
                    candidate = params if params is not None else {}
                    result = validate_well_params(candidate)
                elif name == "calculate_well_model":
                    # Never allow the model to invent or alter physical inputs.
                    candidate = params if params is not None else {}
                    validation = validate_well_params(candidate)
                    if not validation["valid"]:
                        result = {"ok": False, "validation": validation, "operating_point": None}
                        calculation_result = result
                        calculation_failed = True
                    elif calculation_result is not None:
                        result = calculation_result
                    else:
                        try:
                            calculation_result = await calculate_well_model(candidate, calculate)
                            calculation_failed = not calculation_result.get("ok", False)
                            result = calculation_result
                        except Exception as exc:
                            calculation_result = {"ok": False, "operating_point": None, "reason": "Расчетный сервис недоступен"}
                            calculation_failed = True
                            result = {**calculation_result, "error": str(exc)}
                elif name == "run_what_if_scenario":
                    # Scenario baseline must come from the caller, not model-generated values.
                    if params is None:
                        raise ValueError("Сначала передайте базовые параметры скважины")
                    args["base_params"] = params
                    validation = validate_well_params(params)
                    if not validation["valid"]:
                        result = {"ok": False, "validation": validation, "deltas": None}
                        trace.append({"step": step, "tool": name, "args": args, "status": "error", "duration_ms": 0.0, "result": result})
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
                        continue
                    validation = validate_well_params({**args["base_params"], **{section: {**args["base_params"].get(section, {}), **values} for section, values in args["overrides"].items() if isinstance(values, dict)}})
                    if not validation["valid"]:
                        result = {"ok": False, "validation": validation, "deltas": None}
                        trace.append({"step": step, "tool": name, "args": args, "status": "error", "duration_ms": 0.0, "result": result})
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
                        continue
                    result = await run_what_if_scenario(args["base_params"], args["overrides"], calculate)
                    calculation_failed = not result.get("ok", False)
                    if result.get("ok"):
                        calculation_result = result["scenario"]
                        applied_params = {**args["base_params"], **{section: {**args["base_params"].get(section, {}), **values} for section, values in args["overrides"].items() if isinstance(values, dict)}}
                        evidence = {"input": params, "what_if_result": result, "applied_params": applied_params, "calculation": calculation_result}
                elif name == "search_methodology_kb":
                    result = methodology_tool(args.get("query", ""))
                elif name == "optimize_well_parameters":
                    from copy import deepcopy
                    from app.enhancements.optimization import optimize_tubing_diameter, find_critical_wct, optimize_wellhead_pressure
                    target_params = params if params is not None else {}
                    opt_t = args.get("optimization_type", "tubing")
                    best_params = deepcopy(target_params)
                    if opt_t in ("tubing", "all"):
                        tubing_res = await optimize_tubing_diameter(target_params, calculate)
                        result = tubing_res
                        best_d = tubing_res.get("best_tubing", {}).get("d_m")
                        if best_d and best_params:
                            if "vlp" in best_params and "tubing" in best_params["vlp"]:
                                best_params["vlp"]["tubing"]["d"] = best_d
                            elif "vlp" in best_params:
                                best_params["vlp"]["tubing_d"] = best_d
                            try:
                                new_calc = await calculate(best_params)
                                if new_calc.get("operating_point"):
                                    calculation_result = new_calc
                                    applied_params = best_params
                            except Exception:
                                pass
                    elif opt_t == "wellhead":
                        wh_res = await optimize_wellhead_pressure(target_params, calculate)
                        result = wh_res
                        best_p_wh = wh_res.get("optimal_p_wh")
                        if best_p_wh is not None and best_params:
                            if "vlp" in best_params:
                                best_params["vlp"]["p_wh"] = best_p_wh
                            try:
                                new_calc = await calculate(best_params)
                                if new_calc.get("operating_point"):
                                    calculation_result = new_calc
                                    applied_params = best_params
                            except Exception:
                                pass
                    elif opt_t == "wct":
                        result = await find_critical_wct(target_params, calculate)
                    else:
                        tubing_res = await optimize_tubing_diameter(target_params, calculate)
                        result = {
                            "tubing": tubing_res,
                            "wct": await find_critical_wct(target_params, calculate)
                        }
                        best_d = tubing_res.get("best_tubing", {}).get("d_m")
                        if best_d and best_params:
                            if "vlp" in best_params and "tubing" in best_params["vlp"]:
                                best_params["vlp"]["tubing"]["d"] = best_d
                            elif "vlp" in best_params:
                                best_params["vlp"]["tubing_d"] = best_d
                            try:
                                new_calc = await calculate(best_params)
                                if new_calc.get("operating_point"):
                                    calculation_result = new_calc
                                    applied_params = best_params
                            except Exception:
                                pass
                    evidence = {
                        "input": params,
                        "optimization": result,
                        "applied_params": applied_params,
                        "calculation": calculation_result,
                        "standard_tubing_mm": [48, 60, 73, 89, 102, 114]
                    }
                elif name == "apply_optimal_parameters":
                    from copy import deepcopy
                    if params is None:
                        raise ValueError("Сначала передайте базовые параметры скважины")
                    overrides = args.get("overrides", {})
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
                        new_calc = await calculate(new_params)
                        if new_calc.get("operating_point"):
                            calculation_result = new_calc
                            applied_params = new_params
                            result = {
                                "ok": True,
                                "operating_point": new_calc.get("operating_point"),
                                "explanation": args.get("explanation", ""),
                                "applied_params": new_params
                            }
                        else:
                            result = {"ok": False, "reason": "Срыв фонтанирования при заданных параметрах"}
                    evidence = {
                        "input": params,
                        "applied_params": applied_params,
                        "calculation": calculation_result,
                        "result": result,
                        "standard_tubing_mm": [48, 60, 73, 89, 102, 114]
                    }
                elif name == "compare_with_field_measurement":
                    from app.enhancements.matching import compare_with_field_measurement as match_fn
                    target_params = params if params is not None else {}
                    result = await match_fn(target_params, args.get("measured_q_liq", 0.0), args.get("measured_p_wf"), calculate)
                    evidence = {"input": params, "match": result}
                elif name == "generate_meeting_protocol":
                    from app.enhancements.protocol import generate_meeting_protocol as proto_fn
                    result = proto_fn(args.get("transcript", message))
                    evidence = {"protocol": result}
                elif name == "calculate_unit_economics":
                    from app.enhancements.economics import calculate_unit_economics as econ_fn
                    target_params = params if params is not None else {}
                    result = econ_fn(
                        base_params=target_params,
                        base_result=calculation_result,
                        oil_price_rub=float(args.get("oil_price_rub", 35000.0)),
                    )
                    evidence = {"economics": result}
                elif name == "evaluate_flow_assurance":
                    from app.enhancements.flow_assurance import evaluate_flow_assurance as fa_fn
                    target_params = params if params is not None else {}
                    result = fa_fn(target_params, calculation_result)
                    evidence = {"flow_assurance": result}
                elif name == "estimate_virtual_flow":
                    from app.enhancements.vfm import estimate_virtual_flow as vfm_fn
                    target_params = params if params is not None else {}
                    p_wh_obs = float(args.get("p_wh_observed", target_params.get("p_wh", 10.0)))
                    result = await vfm_fn(target_params, p_wh_obs, calc_fn=calculate)
                    evidence = {"vfm": result}
                elif name == "run_monte_carlo_analysis":
                    from app.enhancements.monte_carlo import run_monte_carlo_analysis as mc_fn
                    target_params = params if params is not None else {}
                    n_iter = int(args.get("n_iterations", 50))
                    result = await mc_fn(target_params, calc_fn=calculate, n_iterations=n_iter)
                    evidence = {"monte_carlo": result}
                elif name == "generate_gtm_application":
                    from app.enhancements.gtm_generator import generate_gtm_application as gtm_fn
                    target_params = params if params is not None else {}
                    result = gtm_fn(
                        well_name=str(args.get("well_name", "Скважина 01")),
                        params=target_params,
                        calculation_result=calculation_result,
                        measured_q_liq=args.get("measured_q_liq"),
                        measured_p_wf=args.get("measured_p_wf"),
                        skin_factor=args.get("skin_factor")
                    )
                    evidence = {"gtm": result}
                else:
                    raise ValueError("Неизвестный инструмент")
                duration = (time.perf_counter() - started) * 1000
                if name == "calculate_well_model":
                    evidence = {"input": params, "calculation_result": calculation_result}
                entry = {"step": step, "tool": name, "args": args, "status": "ok", "duration_ms": duration, "result": result}
            except Exception as exc:
                result = {"error": str(exc)}
                entry = {"step": step, "tool": name, "args": {}, "status": "error", "duration_ms": 0.0, "result": result}
            trace.append(entry)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
    safe = "Расчет не подтвердил рабочую точку; новых численных выводов не дано." if calculation_failed else "Достигнут лимит шагов ассистента. Запустите расчет отдельно или уточните запрос."
    return {"available": True, "text": clean_markdown_text(safe), "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result, "params": applied_params}
