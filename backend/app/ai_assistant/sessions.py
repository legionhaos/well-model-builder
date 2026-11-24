"""Small process-local TTL cache for bounded chat history."""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock
from typing import Any

_TTL_SECONDS = 30 * 60
_MAX_SESSIONS = 256
_MAX_MESSAGES = 20
_sessions: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
_lock = Lock()


def get_history(session_id: str) -> list[dict[str, Any]]:
    now = time.monotonic()
    with _lock:
        for key in list(_sessions):
            expires, _ = _sessions[key]
            if expires <= now:
                del _sessions[key]
        entry = _sessions.get(session_id)
        if entry is None:
            return []
        expires, history = entry
        _sessions.move_to_end(session_id)
        return [dict(item) for item in history] if expires > now else []


def save_history(session_id: str, history: list[dict[str, Any]]) -> None:
    now = time.monotonic()
    with _lock:
        _sessions[session_id] = (now + _TTL_SECONDS, [dict(item) for item in history[-_MAX_MESSAGES:]])
        _sessions.move_to_end(session_id)
        while len(_sessions) > _MAX_SESSIONS:
            _sessions.popitem(last=False)
