import asyncio

from backend.app.ai_assistant.tools import run_what_if_scenario, validate_well_params


BASE = {
    "ipr": {"p_res": 200, "wct": 50, "pi": 1, "pb": 150},
    "vlp": {
        "p_wh": 10, "geo_grad": 0.03, "h_res": 1000, "h_mes": 500,
        "MD": [0, 500, 1000], "TVD": [0, 450, 900],
        "tubing": {"d": 0.06}, "casing": {"d": 0.12},
        "pvt": {"wct": 50, "rp": 100, "gamma_oil": 0.85, "gamma_gas": 0.7, "gamma_wat": 1.0},
    },
}


def test_validation_requires_physical_inputs_and_consistent_wct():
    assert validate_well_params(BASE)["valid"]
    changed = {**BASE, "vlp": {**BASE["vlp"], "pvt": {**BASE["vlp"]["pvt"], "wct": 55}}}
    assert not validate_well_params(changed)["valid"]


def test_validation_rejects_non_finite_and_invalid_geometry():
    bad = {**BASE, "vlp": {**BASE["vlp"], "h_res": float("inf"), "casing": {"d": 0.05}}}
    assert not validate_well_params(bad)["valid"]


def test_what_if_uses_python_delta_and_does_not_mutate_base():
    calls = []

    async def calculate(params):
        calls.append(params)
        return {"operating_point": {"q_liq": 100 if params["vlp"]["p_wh"] == 10 else 110, "p_wf": 50}}

    result = asyncio.run(run_what_if_scenario(BASE, {"vlp": {"p_wh": 7}}, calculate))
    assert result["deltas"]["q_liq"] == 10
    assert result["deltas"]["q_liq_percent"] == 10
    assert BASE["vlp"]["p_wh"] == 10
    assert len(calls) == 2
