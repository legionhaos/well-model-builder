"""Official Verification Suite using organizers' test_data/well_01."""

import json
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app
from app.orchestrator.client import calc_client
TEST_DATA_DIR = REPO_ROOT / "test_data" / "well_01"


@pytest.fixture(scope="module")
def official_well_01_data():
    if not TEST_DATA_DIR.exists():
        pytest.skip("test_data/well_01 is excluded from repository")
    req_dir = TEST_DATA_DIR / "requests"
    exp_dir = TEST_DATA_DIR / "expected"

    with open(req_dir / "ipr.json", encoding="utf-8") as f:
        ipr_req = json.load(f)
    with open(req_dir / "vlp.json", encoding="utf-8") as f:
        vlp_req = json.load(f)
    with open(req_dir / "nodal.json", encoding="utf-8") as f:
        nodal_req = json.load(f)

    with open(exp_dir / "ipr.json", encoding="utf-8") as f:
        ipr_exp = json.load(f)
    with open(exp_dir / "vlp.json", encoding="utf-8") as f:
        vlp_exp = json.load(f)
    with open(exp_dir / "nodal.json", encoding="utf-8") as f:
        nodal_exp = json.load(f)

    return {
        "ipr_req": ipr_req,
        "vlp_req": vlp_req,
        "nodal_req": nodal_req,
        "ipr_exp": ipr_exp,
        "vlp_exp": vlp_exp,
        "nodal_exp": nodal_exp,
    }


import httpx

@pytest.mark.asyncio
async def test_official_ipr_accuracy(official_well_01_data):
    """IPR Service comparison with official expected data (tolerance <= 5%)."""
    ipr_req = official_well_01_data["ipr_req"]
    ipr_exp = official_well_01_data["ipr_exp"]

    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.post(f"{calc_client.ipr_url}/ipr/calc", json=ipr_req)
        assert resp.status_code == 200
        actual = resp.json()

    exp_q = ipr_exp["q_liq"]
    exp_p = ipr_exp["p_wf"]
    act_q = actual["q_liq"]
    act_p = actual["p_wf"]

    assert len(act_q) == len(exp_q)
    assert len(act_p) == len(exp_p)

    for i in range(len(exp_q)):
        if exp_q[i] != 0:
            delta_q = abs(act_q[i] - exp_q[i]) / abs(exp_q[i]) * 100
            assert delta_q <= 5.0, f"IPR q_liq[{i}] delta {delta_q:.2f}% > 5%"
        if exp_p[i] != 0:
            delta_p = abs(act_p[i] - exp_p[i]) / abs(exp_p[i]) * 100
            assert delta_p <= 5.0, f"IPR p_wf[{i}] delta {delta_p:.2f}% > 5%"


@pytest.mark.asyncio
async def test_official_vlp_accuracy(official_well_01_data):
    """VLP Service comparison with official expected data (tolerance <= 5%)."""
    vlp_req = official_well_01_data["vlp_req"]
    vlp_exp = official_well_01_data["vlp_exp"]

    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.post(f"{calc_client.vlp_url}/vlp/calc", json=vlp_req)
        assert resp.status_code == 200
        actual = resp.json()

    exp_q = vlp_exp["q_liq"]
    exp_p = vlp_exp["p_wf"]
    act_q = actual["q_liq"]
    act_p = actual["p_wf"]

    assert len(act_q) == len(exp_q)
    assert len(act_p) == len(exp_p)

    for i in range(len(exp_q)):
        if exp_q[i] != 0:
            delta_q = abs(act_q[i] - exp_q[i]) / abs(exp_q[i]) * 100
            assert delta_q <= 5.0, f"VLP q_liq[{i}] delta {delta_q:.2f}% > 5%"
        if exp_p[i] != 0:
            delta_p = abs(act_p[i] - exp_p[i]) / abs(exp_p[i]) * 100
            assert delta_p <= 5.0, f"VLP p_wf[{i}] delta {delta_p:.2f}% > 5%"


@pytest.mark.asyncio
async def test_official_nodal_accuracy(official_well_01_data):
    """Nodal Service comparison with official expected data (tolerance <= 5%)."""
    nodal_req = official_well_01_data["nodal_req"]
    nodal_exp = official_well_01_data["nodal_exp"]

    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.post(f"{calc_client.nodal_url}/nodal/calc", json=nodal_req)
        assert resp.status_code == 200
        actual = resp.json()

    # Nodal returns a list of points: [{"q_liq": ..., "p_wf": ...}]
    act_pt = actual[0] if isinstance(actual, list) else actual
    exp_pt = nodal_exp[0]

    dq = abs(act_pt["q_liq"] - exp_pt["q_liq"]) / exp_pt["q_liq"] * 100
    dp = abs(act_pt["p_wf"] - exp_pt["p_wf"]) / exp_pt["p_wf"] * 100

    assert dq <= 5.0, f"Nodal q_liq delta {dq:.2f}% > 5%"
    assert dp <= 5.0, f"Nodal p_wf delta {dp:.2f}% > 5%"



def test_official_e2e_full_calculation(official_well_01_data):
    """Full End-to-End calculation through Backend API (tolerance <= 10%)."""
    payload = {
        "ipr": official_well_01_data["ipr_req"],
        "vlp": official_well_01_data["vlp_req"]
    }
    client = TestClient(app)
    resp = client.post("/api/calculate", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "success"
    op = data["operating_point"]
    exp_pt = official_well_01_data["nodal_exp"][0]

    dq = abs(op["q_liq"] - exp_pt["q_liq"]) / exp_pt["q_liq"] * 100
    dp = abs(op["p_wf"] - exp_pt["p_wf"]) / exp_pt["p_wf"] * 100

    assert dq <= 10.0, f"E2E q_liq delta {dq:.2f}% > 10%"
    assert dp <= 10.0, f"E2E p_wf delta {dp:.2f}% > 10%"
