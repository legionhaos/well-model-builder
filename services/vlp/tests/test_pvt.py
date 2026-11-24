import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from services.vlp.app.pvt import BlackOilPVT


def test_pvt_black_oil_properties():
    pvt = BlackOilPVT(
        wct=50.0,
        rp_m3_t=100.0,
        gamma_oil=0.8,
        gamma_gas=0.7,
        gamma_wat=1.0
    )

    # Check bubble point calculation at 90 C
    pb_atm, pb_psia = pvt.calc_bubble_point(90.0)
    assert pb_atm > 50.0 and pb_atm < 200.0

    # Low pressure (saturated oil, free gas present)
    props_sat = pvt.calc_properties(p_atm=30.0, t_c=90.0)
    assert props_sat["vmix"] > 1.0
    assert props_sat["rho_mix"] > 200.0 and props_sat["rho_mix"] < 1000.0
    assert props_sat["mu_mix"] > 0.05 and props_sat["mu_mix"] < 5.0

    # High pressure (undersaturated oil, no free gas)
    props_undersat = pvt.calc_properties(p_atm=250.0, t_c=90.0)
    assert props_undersat["vmix"] >= 1.0
    assert props_undersat["rho_mix"] > props_sat["rho_mix"]
    assert props_undersat["bo"] > 1.0
