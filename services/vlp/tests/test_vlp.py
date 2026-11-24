import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from services.vlp.app.main import app

client = TestClient(app)


def test_vlp_health():
    response = client.get("/vlp/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "vlp"}


def test_vlp_benchmark_well_01():
    payload = {
        "inclinometry": {
            "MD": [0, 1000, 1500],
            "TVD": [0, 1000, 1100]
        },
        "casing": {"d": 0.1},
        "tubing": {"d": 0.062, "h_mes": 1000},
        "pvt": {
            "wct": 50,
            "rp": 100,
            "gamma_oil": 0.8,
            "gamma_gas": 0.7,
            "gamma_wat": 1.0,
            "t_res": 90
        },
        "p_wh": 10,
        "geo_grad": 3,
        "h_res": 1500,
        "roughness": 0.0001,
        "q_max": 400,
        "points": 21
    }
    response = client.post("/vlp/calc", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "q_liq" in data and "p_wf" in data

    q_liq = data["q_liq"]
    p_wf = data["p_wf"]

    assert len(q_liq) == 21
    assert len(p_wf) == 21

    # Checks from Section 5.3:
    # q_liq strictly increases
    for i in range(len(q_liq) - 1):
        assert q_liq[i] < q_liq[i + 1]

    # q_liq[0] <= 1, q_liq[-1] ~ 400
    assert q_liq[0] <= 1.0
    assert abs(q_liq[-1] - 400.0) < 1.0

    # p_wf > 0
    assert all(p > 0 for p in p_wf)

    # Benchmark comparison with Section 5.3 targets (allowance is 5%):
    # Target p_wf[0] = 47.48
    assert abs(p_wf[0] - 47.48) / 47.48 < 0.03  # ~1.5% error (< 5%)
    # Target p_wf[1] = 47.56
    assert abs(p_wf[1] - 47.56) / 47.56 < 0.03
    # Target p_wf[-1] = 62.16
    assert abs(p_wf[-1] - 62.16) / 62.16 < 0.03


@pytest.mark.parametrize("invalid_payload", [
    # Mismatched inclinometry
    {
        "inclinometry": {"MD": [0, 1000], "TVD": [0, 1000, 1100]},
        "casing": {"d": 0.1},
        "tubing": {"d": 0.062, "h_mes": 1000},
        "pvt": {"wct": 50, "rp": 100, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90},
        "p_wh": 10, "geo_grad": 3, "h_res": 1500
    },
    # Casing <= Tubing
    {
        "inclinometry": {"MD": [0, 1000, 1500], "TVD": [0, 1000, 1100]},
        "casing": {"d": 0.05},
        "tubing": {"d": 0.062, "h_mes": 1000},
        "pvt": {"wct": 50, "rp": 100, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90},
        "p_wh": 10, "geo_grad": 3, "h_res": 1500
    },
    # Tubing h_mes >= h_res
    {
        "inclinometry": {"MD": [0, 1000, 1500], "TVD": [0, 1000, 1100]},
        "casing": {"d": 0.1},
        "tubing": {"d": 0.062, "h_mes": 1600},
        "pvt": {"wct": 50, "rp": 100, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90},
        "p_wh": 10, "geo_grad": 3, "h_res": 1500
    },
    # Negative p_wh
    {
        "inclinometry": {"MD": [0, 1000, 1500], "TVD": [0, 1000, 1100]},
        "casing": {"d": 0.1},
        "tubing": {"d": 0.062, "h_mes": 1000},
        "pvt": {"wct": 50, "rp": 100, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90},
        "p_wh": -5, "geo_grad": 3, "h_res": 1500
    },
    # Invalid wct
    {
        "inclinometry": {"MD": [0, 1000, 1500], "TVD": [0, 1000, 1100]},
        "casing": {"d": 0.1},
        "tubing": {"d": 0.062, "h_mes": 1000},
        "pvt": {"wct": 150, "rp": 100, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90},
        "p_wh": 10, "geo_grad": 3, "h_res": 1500
    },
    {}
])
def test_vlp_validation_errors(invalid_payload):
    response = client.post("/vlp/calc", json=invalid_payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert "message" in data or "detail" in data
