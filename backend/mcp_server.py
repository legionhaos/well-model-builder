"""Lightweight Model Context Protocol (MCP) stdio server for local files and well calculation."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

# Позволяем запускать как `python backend/mcp_server.py` из корня репозитория или `/app`
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ai_assistant.storage import list_server_files, read_server_file


TOOLS = [
    {
        "name": "list_server_files",
        "description": "Показать список сохранённых на сервере загруженных файлов (PDF, таблицы, сканы) и файлов из samples/.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_server_file",
        "description": "Прочитать содержимое и извлечённые параметры скважины из файла на сервере.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Имя файла"},
                "folder": {"type": "string", "enum": ["uploads", "samples"], "default": "uploads"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "calculate_well_model",
        "description": "Выполнить расчёт IPR/VLP/Nodal через backend оркестратор.",
        "inputSchema": {
            "type": "object",
            "properties": {"params": {"type": "object", "description": "Объект параметров {ipr, vlp}"}},
            "required": ["params"],
        },
    },
]


def _handle_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "list_server_files":
        return {"files": list_server_files()}
    if name == "read_server_file":
        return read_server_file(str(args.get("name", "")), folder=str(args.get("folder", "uploads")))
    if name == "calculate_well_model":
        base_url = os.getenv("BACKEND_INTERNAL_URL", "http://127.0.0.1:8080").rstrip("/")
        resp = httpx.post(f"{base_url}/api/calculate", json=args.get("params", {}), timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    raise ValueError(f"Неизвестный MCP-инструмент: {name}")


def _send(msg: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if method == "initialize":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "well-model-builder-mcp", "version": "1.0.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            try:
                tool_name = params.get("name", "")
                tool_args = params.get("arguments") or {}
                data = _handle_tool_call(tool_name, tool_args)
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]},
                    }
                )
            except Exception as exc:
                _send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"isError": True, "content": [{"type": "text", "text": str(exc)}]},
                    }
                )
        elif req_id is not None:
            _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()
