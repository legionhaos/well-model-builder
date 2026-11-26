"""Model Context Protocol (MCP) server exposing server-saved files and well documents."""

from __future__ import annotations

import json
import mimetypes
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from app.ai_assistant.file_store import (
    list_stored_files,
    read_stored_file,
    resolve_stored_file_path,
    search_stored_files,
)

mcp_app = FastMCP("well-model-builder-files")
mcp_router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class MCPCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = {}


@mcp_app.tool()
def list_server_files() -> str:
    """Получить список сохранённых PDF, паспортов скважин и тестовых файлов на сервере."""
    return json.dumps(list_stored_files(), ensure_ascii=False, indent=2)


@mcp_app.tool()
def read_server_file(file_ref: str) -> str:
    """Прочитать текст и извлечённые параметры сохранённого на сервере PDF или файла по имени/ID."""
    return json.dumps(read_stored_file(file_ref), ensure_ascii=False, indent=2)


@mcp_app.tool()
def search_server_files(query: str, limit: int = 5) -> str:
    """Найти фрагменты и параметры скважин по всем загруженным PDF и документам на сервере."""
    return json.dumps(search_stored_files(query, limit=limit), ensure_ascii=False, indent=2)


def get_mcp_tools_manifest() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_server_files",
            "description": "Получить список всех сохранённых на сервере PDF/документов и тестовых файлов.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "read_server_file",
            "description": "Прочитать содержимое и параметры сохранённого на сервере файла или PDF.",
            "inputSchema": {
                "type": "object",
                "properties": {"file_ref": {"type": "string"}},
                "required": ["file_ref"],
            },
        },
        {
            "name": "search_server_files",
            "description": "Поиск по тексту и параметрам всех загруженных ранее файлов и PDF на сервере.",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
        },
    ]


@mcp_router.get("/tools")
async def http_mcp_tools() -> dict[str, Any]:
    return {"server": "well-model-builder-files", "tools": get_mcp_tools_manifest()}


@mcp_router.get("/files")
async def http_mcp_files() -> dict[str, Any]:
    files = list_stored_files()
    return {"count": len(files), "files": files}


@mcp_router.get("/files/{file_ref:path}")
async def http_mcp_read_file(file_ref: str) -> dict[str, Any]:
    result = read_stored_file(file_ref)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("error", "Файл не найден"))
    return result


@mcp_router.get("/file/{file_ref:path}/raw")
async def http_mcp_raw_file(file_ref: str) -> FileResponse:
    """Serve stored upload/sample file inline so uploaded media and PDFs can be opened from the UI."""
    resolved = resolve_stored_file_path(file_ref)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
    file_path, orig_name = resolved
    media_type, _ = mimetypes.guess_type(orig_name)
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=orig_name,
        content_disposition_type="inline",
    )


@mcp_router.post("/call")
async def http_mcp_call(req: MCPCallRequest) -> dict[str, Any]:
    if req.name == "list_server_files":
        return {"tool": req.name, "result": list_stored_files()}
    if req.name == "read_server_file":
        file_ref = str(req.arguments.get("file_ref", "")).strip()
        if not file_ref:
            raise HTTPException(status_code=422, detail="Не передан аргумент file_ref")
        return {"tool": req.name, "result": read_stored_file(file_ref)}
    if req.name == "search_server_files":
        query = str(req.arguments.get("query", "")).strip()
        limit = int(req.arguments.get("limit", 5) or 5)
        return {"tool": req.name, "result": search_stored_files(query, limit=limit)}
    raise HTTPException(status_code=404, detail=f"Неизвестный MCP-инструмент: {req.name}")


if __name__ == "__main__":
    mcp_app.run(transport="stdio")
