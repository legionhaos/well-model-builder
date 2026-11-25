"""Safe server-side file storage for uploaded documents, PDFs, and samples access."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parsers import parse_upload

_SAFE_NAME_RE = re.compile(r"[^a-zA-Zа-яА-ЯёЁ0-9._-]+")


def get_uploads_dir() -> Path:
    env_dir = os.getenv("UPLOAD_STORAGE_DIR")
    if env_dir:
        path = Path(env_dir)
    elif Path("/app").exists() and os.access("/app", os.W_OK):
        path = Path("/app/uploads")
    else:
        path = Path(__file__).resolve().parents[3] / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_samples_dir() -> Path:
    if Path("/samples").exists():
        return Path("/samples")
    return Path(__file__).resolve().parents[3] / "samples"


def sanitize_filename(filename: str) -> str:
    base = Path(filename or "upload.txt").name
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._")
    return cleaned or "upload.txt"


def save_uploaded_file(
    filename: str,
    content: bytes,
    parsed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an uploaded file and its extracted metadata on the server."""
    uploads = get_uploads_dir()
    safe_name = sanitize_filename(filename)
    target = (uploads / safe_name).resolve()
    if not target.is_relative_to(uploads.resolve()):
        raise ValueError("Недопустимое имя файла")

    target.write_bytes(content)

    meta_path = uploads / f"{safe_name}.meta.json"
    meta_payload = {
        "filename": safe_name,
        "original_filename": filename,
        "size_bytes": len(content),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "sources": (parsed or {}).get("sources", []),
        "extracted_values": (parsed or {}).get("extracted_values", {}),
        "parsed_params": (parsed or {}).get("parsed_params"),
        "text_preview": ((parsed or {}).get("text") or "")[:40_000],
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "saved_name": safe_name,
        "saved_path": str(target),
        "saved_at": meta_payload["saved_at"],
        "size_bytes": len(content),
    }


def list_server_files() -> list[dict[str, Any]]:
    """List uploaded files and sample well files available on the server."""
    items: list[dict[str, Any]] = []
    uploads = get_uploads_dir()
    for entry in sorted(uploads.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_file() or entry.name.endswith(".meta.json"):
            continue
        stat = entry.stat()
        meta_path = uploads / f"{entry.name}.meta.json"
        has_params = False
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                has_params = bool(meta.get("parsed_params"))
            except Exception:
                pass
        items.append(
            {
                "name": entry.name,
                "folder": "uploads",
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "has_parsed_params": has_params,
            }
        )

    samples = get_samples_dir()
    if samples.exists():
        for entry in sorted(samples.rglob("*")):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            rel = entry.relative_to(samples).as_posix()
            stat = entry.stat()
            items.append(
                {
                    "name": rel,
                    "folder": "samples",
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "has_parsed_params": True,
                }
            )
    return items


def read_server_file(name: str, folder: str = "uploads") -> dict[str, Any]:
    """Read and parse a stored file safely without escaping allowed directories."""
    if folder not in {"uploads", "samples"}:
        raise ValueError("Папка должна быть 'uploads' или 'samples'")

    base_dir = (get_uploads_dir() if folder == "uploads" else get_samples_dir()).resolve()
    candidate = (base_dir / name).resolve()
    if not candidate.is_relative_to(base_dir) or not candidate.is_file():
        # Попробуем найти в другой папке, если пользователь не указал folder точно
        alt_dir = (get_samples_dir() if folder == "uploads" else get_uploads_dir()).resolve()
        alt_candidate = (alt_dir / name).resolve()
        if alt_candidate.is_relative_to(alt_dir) and alt_candidate.is_file():
            base_dir = alt_dir
            candidate = alt_candidate
            folder = "samples" if folder == "uploads" else "uploads"
        else:
            raise FileNotFoundError(f"Файл '{name}' не найден на сервере")

    if folder == "uploads":
        meta_path = base_dir / f"{candidate.name}.meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                return {
                    "filename": candidate.name,
                    "folder": "uploads",
                    "size_bytes": candidate.stat().st_size,
                    "text": meta.get("text_preview", ""),
                    "sources": meta.get("sources", []),
                    "extracted_values": meta.get("extracted_values", {}),
                    "parsed_params": meta.get("parsed_params"),
                }
            except Exception:
                pass

    content = candidate.read_bytes()
    try:
        parsed = parse_upload(candidate.name, content)
    except ValueError:
        text = content.decode("utf-8", errors="replace")[:40_000]
        parsed = {"text": text, "sources": [candidate.name], "extracted_values": {}, "parsed_params": None}

    return {
        "filename": candidate.name,
        "folder": folder,
        "size_bytes": len(content),
        **parsed,
    }
