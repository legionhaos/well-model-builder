"""Lazy OpenAI-compatible client; missing configuration never disables calculations."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_sec: float
    max_steps: int

    @classmethod
    def from_env(cls, override: dict[str, str | None] | None = None) -> "LLMConfig":
        ov = override or {}
        base_url = (ov.get("base_url") or "").strip() or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        api_key = (ov.get("api_key") or "").strip() or (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        model = (ov.get("model") or "").strip() or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-flash"
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_sec=max(1.0, float(os.getenv("LLM_TIMEOUT_SEC", "45"))),
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
