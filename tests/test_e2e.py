import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app as backend_app
from backend.app.orchestrator.presets import PRESETS
from backend.app.orchestrator.client import calc_client


@pytest.mark.asyncio
async def test_e2e_full_orchestration_mocked(monkeypatch):
    """
    Тест оркестрации через backend с моком микросервисов:
    проверяет сборку запроса, параллельный вызов и обработку пересечения.
    """
    async def mock_run_full_calc(ipr_payload, vlp_payload):
        return {
            "status": "success",
            "ipr": {"q_liq": [139.98, 0.0], "p_wf": [1.0, 200.0]},
            "vlp": {"q_liq": [0.0, 400.0], "p_wf": [48.19, 62.66]},
            "operating_point": {"q_liq": 127.78, "p_wf": 50.27},
            "meta": {"calc_time_ms": 12.5, "message": "Расчет успешен"}
        }

    monkeypatch.setattr(calc_client, "run_full_calculation", mock_run_full_calc)

    client = TestClient(backend_app)
    well_01_data = next(p["data"] for p in PRESETS if p["id"] == "well_01")
    
    response = client.post("/api/calculate", json=well_01_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["operating_point"]["q_liq"] == 127.78
    assert data["operating_point"]["p_wf"] == 50.27


@pytest.mark.asyncio
async def test_e2e_no_intersection_graceful_handling(monkeypatch):
    """
    Проверка сценария скважины без пересечения:
    система отдает кривые и operating_point: null, не возвращая 500.
    """
    async def mock_no_intersection(ipr_payload, vlp_payload):
        return {
            "status": "no_intersection",
            "ipr": {"q_liq": [45.0, 0.0], "p_wf": [1.0, 45.0]},
            "vlp": {"q_liq": [0.0, 300.0], "p_wf": [50.0, 80.0]},
            "operating_point": None,
            "meta": {"calc_time_ms": 15.0, "message": "Рабочая точка не найдена"}
        }

    monkeypatch.setattr(calc_client, "run_full_calculation", mock_no_intersection)

    client = TestClient(backend_app)
    no_cross_data = next(p["data"] for p in PRESETS if p["id"] == "well_no_intersection")
    
    response = client.post("/api/calculate", json=no_cross_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_intersection"
    assert data["operating_point"] is None
    assert "ipr" in data and "vlp" in data
