import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from services.nodal.app.main import app

client = TestClient(app)


def test_nodal_health():
    response = client.get("/nodal/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nodal"}


def test_nodal_reference_intersection():
    payload = {
        "ipr": {
            "q_liq": [139.98, 137.93, 128.03, 0.0],
            "p_wf": [1.0, 10.95, 49.61, 200.0]
        },
        "vlp": {
            "q_liq": [0.0, 20.0, 128.03, 400.0],
            "p_wf": [47.48, 47.56, 49.61, 62.16]
        }
    }
    response = client.post("/nodal/calc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    point = data[0]
    assert "q_liq" in point and "p_wf" in point
    assert abs(point["q_liq"] - 128.03) < 0.1
    assert abs(point["p_wf"] - 49.61) < 0.1


def test_nodal_no_intersection_422():
    # Non-intersecting curves: IPR is below VLP
    payload = {
        "ipr": {
            "q_liq": [100.0, 0.0],
            "p_wf": [10.0, 30.0]
        },
        "vlp": {
            "q_liq": [0.0, 100.0],
            "p_wf": [50.0, 90.0]
        }
    }
    response = client.post("/nodal/calc", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert "message" in data or "detail" in data


@pytest.mark.parametrize("invalid_payload", [
    # Mismatched lengths
    {
        "ipr": {"q_liq": [100.0, 0.0], "p_wf": [10.0]},
        "vlp": {"q_liq": [0.0, 100.0], "p_wf": [10.0, 50.0]}
    },
    # Less than 2 points
    {
        "ipr": {"q_liq": [100.0], "p_wf": [10.0]},
        "vlp": {"q_liq": [0.0, 100.0], "p_wf": [10.0, 50.0]}
    },
    # Negative q_liq
    {
        "ipr": {"q_liq": [-10.0, 0.0], "p_wf": [10.0, 20.0]},
        "vlp": {"q_liq": [0.0, 100.0], "p_wf": [10.0, 50.0]}
    },
    # Non-positive p_wf
    {
        "ipr": {"q_liq": [100.0, 0.0], "p_wf": [0.0, 20.0]},
        "vlp": {"q_liq": [0.0, 100.0], "p_wf": [10.0, 50.0]}
    },
    {}
])
def test_nodal_validation_errors(invalid_payload):
    response = client.post("/nodal/calc", json=invalid_payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
