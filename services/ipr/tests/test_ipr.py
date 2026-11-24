import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from services.ipr.app.main import app

client = TestClient(app)


def test_ipr_health():
    response = client.get("/ipr/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ipr"}


def test_ipr_benchmark_well_01():
    payload = {
        "p_res": 200,
        "wct": 50,
        "pi": 1,
        "pb": 150
    }
    response = client.post("/ipr/calc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "q_liq" in data and "p_wf" in data
    
    q_liq = data["q_liq"]
    p_wf = data["p_wf"]
    
    assert len(q_liq) == 21
    assert len(p_wf) == 21
    
    # Grid checks
    assert abs(p_wf[0] - 1.0) < 1e-4
    assert abs(p_wf[-1] - 200.0) < 1e-4
    assert abs(q_liq[-1] - 0.0) < 1e-4
    
    # Benchmark targets: q_liq[0] ~ 139.98, q_liq[1] ~ 137.93
    assert abs(q_liq[0] - 139.98) / 139.98 < 0.01  # less than 1% error (limit is 5%)
    assert abs(q_liq[1] - 137.93) / 137.93 < 0.01
    
    # Monotonicity check
    for i in range(len(q_liq) - 1):
        assert q_liq[i] >= q_liq[i + 1]


def test_ipr_wct_100():
    payload = {
        "p_res": 200,
        "wct": 100,
        "pi": 2.0,
        "pb": 150,
        "points": 50
    }
    response = client.post("/ipr/calc", json=payload)
    assert response.status_code == 200
    data = response.json()
    q_liq = data["q_liq"]
    p_wf = data["p_wf"]
    assert len(q_liq) == 50
    # Pure linear: q = 2 * (200 - p_wf)
    for q, p in zip(q_liq, p_wf):
        expected_q = 2.0 * (200.0 - p)
        assert abs(q - expected_q) < 1e-3


def test_ipr_zero_pi():
    payload = {
        "p_res": 150,
        "wct": 20,
        "pi": 0,
        "pb": 100
    }
    response = client.post("/ipr/calc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert all(q == 0.0 for q in data["q_liq"])


@pytest.mark.parametrize("invalid_payload", [
    {"p_res": -10, "wct": 50, "pi": 1, "pb": 150},
    {"p_res": 200, "wct": 120, "pi": 1, "pb": 150},
    {"p_res": 200, "wct": -5, "pi": 1, "pb": 150},
    {"p_res": 200, "wct": 50, "pi": -1, "pb": 150},
    {"p_res": 200, "wct": 50, "pi": 1, "pb": -10},
    {"p_res": 200, "wct": 50, "pi": 1, "pb": 150, "points": 1},
    {"p_res": 200, "wct": 50, "pi": 1, "pb": 150, "points": 300},
    {"p_res": "invalid", "wct": 50, "pi": 1, "pb": 150},
    {}
])
def test_ipr_validation_errors(invalid_payload):
    response = client.post("/ipr/calc", json=invalid_payload)
    assert response.status_code == 422
    data = response.json()
    assert "message" in data or "detail" in data
    assert response.headers["content-type"].startswith("application/json")
