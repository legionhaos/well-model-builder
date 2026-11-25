"""Request and response contracts for the optional AI assistant."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = Field(default=None, max_length=128)
    params: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Сообщение не должно быть пустым")
        return value.strip()


class ToolTraceEntry(BaseModel):
    step: int
    tool: str
    args: dict[str, Any]
    status: str
    duration_ms: float
    result: Any | None = None


class ChatResponse(BaseModel):
    available: bool = True
    text: str
    session_id: str
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list)
    calculation_result: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


class ChatStatus(BaseModel):
    available: bool
    message: str | None = None


class UploadResponse(BaseModel):
    filename: str
    text: str
    extracted_values: dict[str, Any] = Field(default_factory=dict)
    parsed_params: dict[str, Any] | None = None
    wells: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
