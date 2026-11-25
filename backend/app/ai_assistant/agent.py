"""Bounded tool-calling agent with calculation-only numeric evidence."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .guardrails import isolate_untrusted, redact_unsupported_numbers, sanitize_untrusted_text
from .llm_client import LLMConfig, create_client
from .prompts import SYSTEM_PROMPT
from .parsers import parse_message_parameters
from .sessions import get_history, save_history
from .tools import calculate_well_model, methodology_tool, run_what_if_scenario, validate_well_params


def _tool_specs() -> list[dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "validate_well_params", "description": "Проверить полноту и физическую согласованность параметров (использует текущие параметры модели)", "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": []}}},
        {"type": "function", "function": {"name": "calculate_well_model", "description": "Рассчитать текущую модель (если ещё не рассчитана)", "parameters": {"type": "object", "properties": {"params": {"type": "object"}}, "required": []}}},
        {"type": "function", "function": {"name": "run_what_if_scenario", "description": "Рассчитать сценарий «что если» с явными переопределениями в секциях ipr/vlp (например {\"vlp\": {\"p_wh\": 5}})", "parameters": {"type": "object", "properties": {"overrides": {"type": "object"}}, "required": ["overrides"]}}},
        {"type": "function", "function": {"name": "search_methodology_kb", "description": "Найти фрагменты локальной методики с источниками", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "optimize_well_parameters", "description": "Подобрать оптимальный диаметр НКТ или проанализировать критическую обводненность скважины", "parameters": {"type": "object", "properties": {"optimization_type": {"type": "string", "enum": ["tubing", "wct", "wellhead", "all"]}}, "required": []}}},
        {"type": "function", "function": {"name": "compare_with_field_measurement", "description": "Сравнить расчетную модель с фактическим замером дебита/давления ГДИ/АГЗУ и выявить причины невязки", "parameters": {"type": "object", "properties": {"measured_q_liq": {"type": "number", "description": "Фактический дебит жидкости, м3/сут"}, "measured_p_wf": {"type": "number", "description": "Фактическое забойное давление, атм"}}, "required": ["measured_q_liq"]}}},
        {"type": "function", "function": {"name": "generate_meeting_protocol", "description": "Составить официальный протокол технического совещания по скважине из стенограммы", "parameters": {"type": "object", "properties": {"transcript": {"type": "string"}}, "required": ["transcript"]}}},
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
    evidence: Any = {}
    if client is None:
        response_text = "ИИ-ассистент не настроен (отсутствует ключ LLM или LLM_MODEL). Расчет через /api/calculate доступен независимо."
        return {"available": False, "text": response_text, "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result}

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_history(session_id))
    context_note = ""
    if params is not None:
        context_note = (
            "\nКонтекст формы (не вызывай расчёт и не выводи числа из него, пока пользователь явно не попросит рассчитать, оптимизировать или проанализировать модель): "
            + json.dumps(params, ensure_ascii=False)
        )
    messages.append({"role": "user", "content": isolate_untrusted(sanitize_untrusted_text(message)) + context_note})
    for step in range(1, config.max_steps + 1):
        try:
            response = await client.chat.completions.create(model=config.model, messages=messages, tools=_tool_specs(), tool_choice="auto")
        except Exception:
            return {"available": False, "text": "ИИ-провайдер временно недоступен. Расчет через /api/calculate продолжает работать.", "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result}
        choice = response.choices[0].message
        if not choice.tool_calls:
            text = choice.content or "Не удалось сформировать ответ."
            if calculation_failed or (calculation_result is not None and calculation_result.get("operating_point") is None):
                text = "Расчет не подтвердил рабочую точку. Не выдаю прогнозные числа; проверьте исходные данные и диагностическое сообщение."
            safe_text = redact_unsupported_numbers(text, evidence)
            save_history(session_id, messages[1:] + [{"role": "assistant", "content": safe_text}])
            return {"available": True, "text": safe_text, "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result}

        messages.append({"role": "assistant", "content": choice.content, "tool_calls": [call.model_dump(exclude_none=True) for call in choice.tool_calls]})
        for call in choice.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                started = time.perf_counter()
                if name == "validate_well_params":
                    candidate = params if params is not None else {}
                    result = validate_well_params(candidate)
                    evidence = {"input": params, "validation": result}
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
                    overrides = args.get("overrides")
                    if not isinstance(overrides, dict):
                        raise ValueError("Передайте объект overrides с параметрами сценария")
                    args["overrides"] = overrides
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
                        evidence = {"input": params, "what_if_result": result}
                elif name == "search_methodology_kb":
                    result = methodology_tool(args.get("query", ""))
                    evidence = {"input": params, "methodology": result}
                elif name == "optimize_well_parameters":
                    from app.enhancements.optimization import optimize_tubing_diameter, find_critical_wct, optimize_wellhead_pressure
                    target_params = params if params is not None else {}
                    opt_t = args.get("optimization_type", "tubing")
                    if opt_t == "tubing":
                        result = await optimize_tubing_diameter(target_params, calculate)
                    elif opt_t == "wct":
                        result = await find_critical_wct(target_params, calculate)
                    elif opt_t == "wellhead":
                        result = await optimize_wellhead_pressure(target_params, calculate)
                    else:
                        result = {
                            "tubing": await optimize_tubing_diameter(target_params, calculate),
                            "wct": await find_critical_wct(target_params, calculate)
                        }
                    evidence = {"input": params, "optimization": result}
                elif name == "compare_with_field_measurement":
                    from app.enhancements.matching import compare_with_field_measurement as match_fn
                    target_params = params if params is not None else {}
                    result = await match_fn(target_params, args.get("measured_q_liq", 0.0), args.get("measured_p_wf"), calculate)
                    evidence = {"input": params, "match": result}
                elif name == "generate_meeting_protocol":
                    from app.enhancements.protocol import generate_meeting_protocol as proto_fn
                    result = proto_fn(args.get("transcript", message))
                    evidence = {"protocol": result}
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
    return {"available": True, "text": safe, "session_id": session_id, "tool_trace": trace, "calculation_result": calculation_result}
