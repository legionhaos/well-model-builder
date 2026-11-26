"""Persistent storage and lookup for uploaded well documents (PDF/DOCX/XLSX/TXT/CSV/JSON)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_uploads_dir() -> Path:
    raw = os.getenv("UPLOAD_STORAGE_DIR", "").strip()
    if raw:
        root = Path(raw)
    else:
        root = Path(__file__).resolve().parent.parent.parent.parent / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_samples_dir() -> Path:
    if Path("/samples").exists():
        return Path("/samples")
    return Path(__file__).resolve().parent.parent.parent.parent / "samples"


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9._-]+", "_", base).strip("._")
    return cleaned or "document.bin"


def save_uploaded_document(
    filename: str,
    content: bytes,
    *,
    extracted_text: str = "",
    parsed_params: dict[str, Any] | None = None,
    extracted_values: dict[str, Any] | None = None,
    sources: list[str] | None = None,
    ocr_method: str | None = None,
) -> dict[str, Any]:
    """Persist uploaded binary and extracted metadata so AI/MCP can inspect old files."""
    uploads = get_uploads_dir()
    safe_name = _safe_filename(filename)
    digest = hashlib.sha256(content).hexdigest()[:10]
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    stored_name = f"{stem}_{digest}{suffix}"
    target_path = uploads / stored_name
    target_path.write_bytes(content)

    meta = {
        "id": stored_name,
        "filename": Path(filename).name,
        "stored_name": stored_name,
        "path": str(target_path),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "ocr_method": ocr_method or "text_parser",
        "sources": sources or [Path(filename).name],
        "extracted_values": extracted_values or {},
        "parsed_params": parsed_params,
        "text": (extracted_text or "")[:100_000],
    }
    meta_path = uploads / f"{stored_name}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def list_stored_files() -> list[dict[str, Any]]:
    """List saved uploaded documents and sample files available on server."""
    items: list[dict[str, Any]] = []
    uploads = get_uploads_dir()
    for meta_file in sorted(uploads.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            items.append({
                "scope": "uploads",
                "id": meta.get("id", meta_file.name),
                "filename": meta.get("filename", meta_file.stem),
                "uploaded_at": meta.get("uploaded_at"),
                "size_bytes": meta.get("size_bytes", 0),
                "ocr_method": meta.get("ocr_method"),
                "has_params": bool(meta.get("parsed_params")),
                "text_preview": (meta.get("text") or "")[:240],
            })
        except Exception:
            continue

    samples = get_samples_dir()
    if samples.exists():
        for f in sorted(samples.glob("*")):
            if not f.is_file() or f.name.startswith("."):
                continue
            items.append({
                "scope": "samples",
                "id": f"samples/{f.name}",
                "filename": f.name,
                "uploaded_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                "size_bytes": f.stat().st_size,
                "ocr_method": "sample",
                "has_params": True,
                "text_preview": "",
            })
    return items


def read_stored_file(file_ref: str) -> dict[str, Any]:
    """Read text and parsed parameters of any saved file or sample on the server."""
    ref = (file_ref or "").strip()
    if not ref:
        raise ValueError("Укажите имя или id файла")

    uploads = get_uploads_dir()
    for meta_file in sorted(uploads.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if ref in {meta.get("id"), meta.get("filename"), meta.get("stored_name")} or ref.lower() in str(meta.get("filename", "")).lower():
                return {
                    "found": True,
                    "scope": "uploads",
                    "id": meta.get("id"),
                    "filename": meta.get("filename"),
                    "uploaded_at": meta.get("uploaded_at"),
                    "ocr_method": meta.get("ocr_method"),
                    "sources": meta.get("sources", []),
                    "parsed_params": meta.get("parsed_params"),
                    "extracted_values": meta.get("extracted_values", {}),
                    "text": (meta.get("text") or "")[:30_000],
                }
        except Exception:
            continue

    samples = get_samples_dir()
    clean_ref = ref.replace("samples/", "")
    sample_path = (samples / Path(clean_ref).name).resolve()
    if samples.exists() and sample_path.is_file() and str(sample_path).startswith(str(samples.resolve())):
        from .parsers import parse_upload
        parsed = parse_upload(sample_path.name, sample_path.read_bytes())
        return {
            "found": True,
            "scope": "samples",
            "id": f"samples/{sample_path.name}",
            "filename": sample_path.name,
            "sources": parsed.get("sources", []),
            "parsed_params": parsed.get("parsed_params"),
            "extracted_values": parsed.get("extracted_values", {}),
            "text": parsed.get("text", "")[:30_000],
        }

    return {"found": False, "error": f"Файл «{ref}» не найден на сервере"}


def search_stored_files(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Keyword/value search across uploaded server PDFs/documents and samples."""
    terms = [t for t in re.findall(r"[a-zа-яё0-9._-]+", (query or "").lower()) if len(t) >= 2]
    matches: list[dict[str, Any]] = []
    for entry in list_stored_files():
        data = read_stored_file(entry["id"])
        if not data.get("found"):
            continue
        haystack = f"{data.get('filename', '')}\n{data.get('text', '')}\n{json.dumps(data.get('parsed_params') or {}, ensure_ascii=False)}".lower()
        score = sum(haystack.count(t) for t in terms) if terms else 1
        if score > 0:
            matches.append({
                "id": data["id"],
                "filename": data["filename"],
                "scope": data["scope"],
                "score": score,
                "parsed_params": data.get("parsed_params"),
                "snippet": (data.get("text") or "")[:500],
            })
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:limit]


def resolve_stored_file_path(file_ref: str) -> tuple[Path, str] | None:
    """Safely resolve disk path and original filename for any stored upload or sample."""
    ref = (file_ref or "").strip()
    if not ref:
        return None

    uploads = get_uploads_dir().resolve()
    for meta_file in sorted(uploads.glob("*.meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if ref in {meta.get("id"), meta.get("stored_name"), meta.get("filename")}:
                stored_name = str(meta.get("stored_name") or "").strip()
                if not stored_name:
                    continue
                target = (uploads / stored_name).resolve()
                if target.is_relative_to(uploads) and target.is_file():
                    return target, str(meta.get("filename") or target.name)
        except Exception:
            continue

    samples = get_samples_dir().resolve()
    clean_ref = ref.removeprefix("samples/")
    if samples.exists() and clean_ref:
        candidate = (samples / Path(clean_ref).name).resolve()
        if candidate.is_relative_to(samples) and candidate.is_file():
            return candidate, candidate.name

    return None
