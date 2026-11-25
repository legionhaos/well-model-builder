"""Small deterministic local methodology search (no external service)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from app.ai_assistant.guardrails import clean_markdown_text


def search_methodology_kb(query: str, kb_dir: str | Path | None = None, *, limit: int = 4) -> list[dict[str, Any]]:
    if kb_dir:
        root = Path(kb_dir)
    else:
        # Проверяем локальную папку базы знаний модуля или корень docs/kb
        local_kb = Path(__file__).resolve().parent / "kb"
        docs_kb = Path(__file__).resolve().parents[2] / "docs" / "kb"
        root = local_kb if local_kb.exists() else docs_kb
    terms = {word.lower() for word in re.findall(r"[\w-]+", query) if len(word) > 2}
    results = []
    if not root.exists():
        return results
    for path in root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        chunks = re.split(r"\n(?=#{1,3} )", text)
        for chunk in chunks:
            words = {word.lower() for word in re.findall(r"[\w-]+", chunk) if len(word) > 2}
            overlap = len(terms & words)
            if overlap:
                cleaned_chunk = clean_markdown_text(chunk[:2000].strip())
                source_name = path.name
                results.append({"source": source_name, "text": cleaned_chunk, "score": overlap / max(len(terms), 1)})
    return sorted(results, key=lambda item: item["score"], reverse=True)[: max(1, limit)]
