from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.ai_assistant.router import router


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_chat_status_without_key_is_available_as_degraded_mode(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    response = client.get("/api/chat/status")
    assert response.status_code == 200
    assert response.json() == {"available": False, "message": "ИИ-ассистент не настроен (отсутствует ключ LLM)"}


def test_chat_reports_missing_fields_without_guessing(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    response = client.post("/api/chat", json={"message": "пластовое_давление: 10 МПа\nобводненность: 50%"})
    body = response.json()
    assert response.status_code == 200
    assert "ipr.pi" in body["text"]
    assert body["calculation_result"]["operating_point"] is None
    assert body["session_id"]


def test_chat_accepts_nonempty_session_id():
    response = client.post("/api/chat", json={"message": "данные неполные", "session_id": "s-123"})
    assert response.status_code == 200
    assert response.json()["session_id"] == "s-123"
