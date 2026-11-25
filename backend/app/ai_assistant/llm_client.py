"""Lazy OpenAI-compatible client; missing configuration never disables calculations."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_sec: float
    max_steps: int

    @classmethod
    def from_env(cls, overrides: Mapping[str, Any] | None = None) -> "LLMConfig":
        ov = overrides or {}
        ov_url = str(ov.get("base_url") or "").strip()
        ov_key = str(ov.get("api_key") or "").strip()
        ov_model = str(ov.get("model") or "").strip()
        return cls(
            base_url=ov_url or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            api_key=ov_key or (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip(),
            model=ov_model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-flash",
            timeout_sec=max(1.0, float(os.getenv("LLM_TIMEOUT_SEC", "30"))),
            max_steps=max(1, min(20, int(os.getenv("AI_MAX_STEPS", "6")))),
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model)


def create_client(config: LLMConfig | None = None):
    """Instantiate the optional SDK only when actually configured."""
    config = config or LLMConfig.from_env()
    if not config.available:
        return None
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_sec, max_retries=1)
