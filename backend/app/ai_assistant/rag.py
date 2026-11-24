"""Small deterministic local methodology search (no external service)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def search_methodology_kb(query: str, kb_dir: str | Path | None = None, *, limit: int = 4) -> list[dict[str, Any]]:
    root = Path(kb_dir) if kb_dir else Path(__file__).resolve().parents[3] / "docs" / "kb"
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
                results.append({"source": str(path.relative_to(root.parent.parent)), "text": chunk[:2000].strip(), "score": overlap / max(len(terms), 1)})
    return sorted(results, key=lambda item: item["score"], reverse=True)[: max(1, limit)]
