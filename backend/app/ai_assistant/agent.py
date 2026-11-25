"""Bounded tool-calling agent with streaming and calculation-only numeric evidence."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .guardrails import isolate_untrusted, redact_unsupported_numbers, sanitize_untrusted_text
from .llm_client import LLMConfig, create_client
from .parsers import parse_message_parameters
from .prompts import SYSTEM_PROMPT
from .sessions import get_history, save_history
from .storage import list_server_files, read_server_file
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
                "name": "optimize_well_parameters",
                "description": "Подобрать оптимальный диаметр НКТ или проанализировать критическую обводненность скважины",
                "parameters": {
                    "type": "object",
                    "properties": {"optimization_type": {"type": "string", "enum": ["tubing", "wct", "wellhead", "all"]}},
                    "required": [],
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
                "name": "list_server_files",
                "description": "Получить список сохранённых пользователем файлов (PDF, таблицы, сканы) и файлов в папке samples на сервере",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_server_file",
                "description": "Прочитать содержимое и извлечённые параметры сохранённого на сервере файла по имени",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Имя файла на сервере"},
                        "folder": {"type": "string", "enum": ["uploads", "samples"], "description": "Папка: uploads или samples"},
                    },
                    "required": ["name"],
                },
            },
        },
    ]


@dataclass
class _AgentState:
    message: str
    params: dict[str, Any] | None
    calculate: Any
    session_id: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    calculation_result: dict[str, Any] | None = None
    calculation_failed: bool = False
    evidence: Any = field(default_factory=dict)


def _prepare_messages(message: str, params: dict[str, Any] | None, session_id: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_history(session_id))
    context_note = ""
    if params is not None:
        context_note = (
            "\nКонтекст формы (не вызывай расчёт и не выводи числа из него, пока пользователь явно не попросит рассчитать, оптимизировать или проанализировать модель): "
            + json.dumps(params, ensure_ascii=False)
        )
    messages.append({"role": "user", "content": isolate_untrusted(sanitize_untrusted_text(message)) + context_note})
    return messages


def _finalize_text(raw_text: str | None, state: _AgentState) -> str:
    text = raw_text or "Не удалось сформировать ответ."
    if state.calculation_failed or (
        state.calculation_result is not None and state.calculation_result.get("operating_point") is None
    ):
        text = "Расчет не подтвердил рабочую точку. Не выдаю прогнозные числа; проверьте исходные данные и диагностическое сообщение."
    return redact_unsupported_numbers(text, state.evidence)


async def _execute_tool(name: str, raw_args: str, step: int, state: _AgentState) -> tuple[dict[str, Any], dict[str, Any]]:
    params = state.params
    try:
        args = json.loads(raw_args or "{}")
        started = time.perf_counter()

        if name == "validate_well_params":
            candidate = params if params is not None else {}
            result = validate_well_params(candidate)
            state.evidence = {"input": params, "validation": result}

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
                    state.calculation_result = await calculate_well_model(candidate, state.calculate)
                    state.calculation_failed = not state.calculation_result.get("ok", False)
                    result = state.calculation_result
                except Exception as exc:
                    state.calculation_result = {"ok": False, "operating_point": None, "reason": "Расчетный сервис недоступен"}
                    state.calculation_failed = True
                    result = {**state.calculation_result, "error": str(exc)}
            state.evidence = {"input": params, "calculation_result": state.calculation_result}

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
                return result, entry
            merged = {
                **args["base_params"],
                **{
                    section: {**args["base_params"].get(section, {}), **values}
                    for section, values in overrides.items()
                    if isinstance(values, dict)
                },
            }
            validation = validate_well_params(merged)
            if not validation["valid"]:
                result = {"ok": False, "validation": validation, "deltas": None}
                entry = {"step": step, "tool": name, "args": args, "status": "error", "duration_ms": 0.0, "result": result}
                return result, entry
            result = await run_what_if_scenario(args["base_params"], overrides, state.calculate)
            state.calculation_failed = not result.get("ok", False)
            if result.get("ok"):
                state.calculation_result = result["scenario"]
                state.evidence = {"input": params, "what_if_result": result}

        elif name == "search_methodology_kb":
            result = methodology_tool(args.get("query", ""))
            state.evidence = {"input": params, "methodology": result}

        elif name == "optimize_well_parameters":
            from app.enhancements.optimization import (
                find_critical_wct,
                optimize_tubing_diameter,
                optimize_wellhead_pressure,
            )

            target_params = params if params is not None else {}
            opt_t = args.get("optimization_type", "tubing")
            if opt_t == "tubing":
                result = await optimize_tubing_diameter(target_params, state.calculate)
            elif opt_t == "wct":
                result = await find_critical_wct(target_params, state.calculate)
            elif opt_t == "wellhead":
                result = await optimize_wellhead_pressure(target_params, state.calculate)
            else:
                result = {
                    "tubing": await optimize_tubing_diameter(target_params, state.calculate),
                    "wct": await find_critical_wct(target_params, state.calculate),
                }
            state.evidence = {"input": params, "optimization": result}

        elif name == "compare_with_field_measurement":
            from app.enhancements.matching import compare_with_field_measurement as match_fn

            target_params = params if params is not None else {}
            result = await match_fn(
                target_params,
                args.get("measured_q_liq", 0.0),
                args.get("measured_p_wf"),
                state.calculate,
            )
            state.evidence = {"input": params, "match": result}

        elif name == "generate_meeting_protocol":
            from app.enhancements.protocol import generate_meeting_protocol as proto_fn

            result = proto_fn(args.get("transcript", state.message))
            state.evidence = {"protocol": result}

        elif name == "list_server_files":
            result = {"files": list_server_files()}
            state.evidence = {"input": params, "files": result}

        elif name == "read_server_file":
            file_name = str(args.get("name", "")).strip()
            folder = str(args.get("folder", "uploads")).strip() or "uploads"
            if not file_name:
                raise ValueError("Укажите имя файла")
            file_data = read_server_file(file_name, folder=folder)
            result = {
                "filename": file_data.get("filename"),
                "folder": file_data.get("folder"),
                "extracted_values": file_data.get("extracted_values"),
                "parsed_params": file_data.get("parsed_params"),
                "text": (file_data.get("text") or "")[:6000],
            }
            state.evidence = {"input": params, "file_data": result}

        else:
            raise ValueError("Неизвестный инструмент")

        duration = (time.perf_counter() - started) * 1000
        entry = {"step": step, "tool": name, "args": args, "status": "ok", "duration_ms": duration, "result": result}
        return result, entry

    except Exception as exc:
        result = {"error": str(exc)}
        entry = {"step": step, "tool": name, "args": {}, "status": "error", "duration_ms": 0.0, "result": result}
        return result, entry


async def run_agent(
    message: str,
    *,
    params: dict[str, Any] | None,
    calculate,
    session_id: str | None = None,
    llm_override: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    if params is None:
        params = parse_message_parameters(message)
    config = LLMConfig.from_env(llm_override)
    client = create_client(config)
    session_id = session_id or str(uuid.uuid4())
    state = _AgentState(message=message, params=params, calculate=calculate, session_id=session_id)

    if client is None:
        response_text = "ИИ-ассистент не настроен (укажите API-ключ в настройках или .env). Расчет через /api/calculate доступен независимо."
        return {
            "available": False,
            "text": response_text,
            "session_id": session_id,
            "tool_trace": state.trace,
            "calculation_result": state.calculation_result,
        }

    messages = _prepare_messages(message, params, session_id)
    for step in range(1, config.max_steps + 1):
        try:
            response = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=_tool_specs(),
                tool_choice="auto",
            )
        except Exception:
            return {
                "available": False,
                "text": "ИИ-провайдер временно недоступен. Проверьте настройки API или повторите позже; расчет ядра работает независимо.",
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
            }

        choice = response.choices[0].message
        if not choice.tool_calls:
            safe_text = _finalize_text(choice.content, state)
            save_history(session_id, messages[1:] + [{"role": "assistant", "content": safe_text}])
            return {
                "available": True,
                "text": safe_text,
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
            }

        messages.append(
            {
                "role": "assistant",
                "content": choice.content,
                "tool_calls": [call.model_dump(exclude_none=True) for call in choice.tool_calls],
            }
        )
        for call in choice.tool_calls:
            result, entry = await _execute_tool(call.function.name, call.function.arguments or "{}", step, state)
            state.trace.append(entry)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    safe = (
        "Расчет не подтвердил рабочую точку; новых численных выводов не дано."
        if state.calculation_failed
        else "Достигнут лимит шагов ассистента. Запустите расчет отдельно или уточните запрос."
    )
    return {
        "available": True,
        "text": safe,
        "session_id": session_id,
        "tool_trace": state.trace,
        "calculation_result": state.calculation_result,
    }


async def run_agent_stream(
    message: str,
    *,
    params: dict[str, Any] | None,
    calculate,
    session_id: str | None = None,
    llm_override: dict[str, str | None] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if params is None:
        params = parse_message_parameters(message)
    config = LLMConfig.from_env(llm_override)
    client = create_client(config)
    session_id = session_id or str(uuid.uuid4())
    state = _AgentState(message=message, params=params, calculate=calculate, session_id=session_id)

    yield {"type": "status", "session_id": session_id, "message": "Анализирую запрос..."}

    if client is None:
        response_text = "ИИ-ассистент не настроен (укажите API-ключ в настройках или .env). Расчет через /api/calculate доступен независимо."
        yield {
            "type": "done",
            "available": False,
            "text": response_text,
            "session_id": session_id,
            "tool_trace": state.trace,
            "calculation_result": state.calculation_result,
        }
        return

    messages = _prepare_messages(message, params, session_id)
    for step in range(1, config.max_steps + 1):
        content_parts: list[str] = []
        tool_calls_map: dict[int, dict[str, Any]] = {}

        try:
            stream = await client.chat.completions.create(
                model=config.model,
                messages=messages,
                tools=_tool_specs(),
                tool_choice="auto",
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
                    yield {"type": "delta", "chunk": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index if tc.index is not None else 0
                        bucket = tool_calls_map.setdefault(
                            idx,
                            {"id": tc.id or f"call_{step}_{idx}", "type": "function", "function": {"name": "", "arguments": ""}},
                        )
                        if tc.id:
                            bucket["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                bucket["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                bucket["function"]["arguments"] += tc.function.arguments
        except Exception:
            # Fallback: если провайдер не поддерживает stream=True с tools
            try:
                response = await client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                    tools=_tool_specs(),
                    tool_choice="auto",
                )
                choice = response.choices[0].message
                if choice.content:
                    content_parts = [choice.content]
                    yield {"type": "delta", "chunk": choice.content}
                if choice.tool_calls:
                    for idx, call in enumerate(choice.tool_calls):
                        tool_calls_map[idx] = call.model_dump(exclude_none=True)
            except Exception:
                yield {
                    "type": "done",
                    "available": False,
                    "text": "ИИ-провайдер временно недоступен. Проверьте настройки API или повторите позже; расчет ядра работает независимо.",
                    "session_id": session_id,
                    "tool_trace": state.trace,
                    "calculation_result": state.calculation_result,
                }
                return

        ordered_calls = [tool_calls_map[k] for k in sorted(tool_calls_map)]
        raw_content = "".join(content_parts) if content_parts else None

        if not ordered_calls:
            safe_text = _finalize_text(raw_content, state)
            save_history(session_id, messages[1:] + [{"role": "assistant", "content": safe_text}])
            yield {
                "type": "done",
                "available": True,
                "text": safe_text,
                "session_id": session_id,
                "tool_trace": state.trace,
                "calculation_result": state.calculation_result,
            }
            return

        messages.append({"role": "assistant", "content": raw_content, "tool_calls": ordered_calls})
        for tc in ordered_calls:
            fn_name = tc["function"]["name"]
            yield {"type": "status", "session_id": session_id, "message": f"Выполняю инструмент: {fn_name}..."}
            result, entry = await _execute_tool(fn_name, tc["function"].get("arguments", "{}"), step, state)
            state.trace.append(entry)
            yield {
                "type": "tool",
                "step": entry["step"],
                "tool": entry["tool"],
                "status": entry["status"],
                "duration_ms": entry["duration_ms"],
            }
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    safe = (
        "Расчет не подтвердил рабочую точку; новых численных выводов не дано."
        if state.calculation_failed
        else "Достигнут лимит шагов ассистента. Запустите расчет отдельно или уточните запрос."
    )
    yield {
        "type": "done",
        "available": True,
        "text": safe,
        "session_id": session_id,
        "tool_trace": state.trace,
        "calculation_result": state.calculation_result,
    }
