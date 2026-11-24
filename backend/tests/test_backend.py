import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_backend_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "backend"
    assert "dependencies" in data
    assert "ai_enabled" in data


def test_get_presets():
    response = client.get("/api/presets")
    assert response.status_code == 200
    presets = response.json()
    assert isinstance(presets, list)
    assert len(presets) >= 3
    preset_ids = [p["id"] for p in presets]
    assert "well_01" in preset_ids
    assert "well_high_wct" in preset_ids
    assert "well_no_intersection" in preset_ids


def test_get_preset_by_id():
    response = client.get("/api/presets/well_01")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "well_01"
    assert "data" in data
    assert "ipr" in data["data"]
    assert "vlp" in data["data"]


def test_get_preset_not_found():
    response = client.get("/api/presets/non_existent_preset")
    assert response.status_code == 404


def test_chat_status():
    response = client.get("/api/chat/status")
    assert response.status_code == 200
    data = response.json()
    assert "available" in data


def test_calculate_validation_error():
    # Отправка неполных данных
    response = client.post("/api/calculate", json={"p_res": 200})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert "message" in data or "detail" in data
