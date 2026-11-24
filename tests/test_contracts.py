import sys
from pathlib import Path
import pytest

# Подключение путей к сервисам для модульного тестирования ядра
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.ipr.app.model import calculate_ipr
from services.vlp.app.pvt import BlackOilPVT
from services.vlp.app.model import calculate_vlp
from services.nodal.app.solver import solve_nodal_intersection


def test_e2e_well_01_calculation():
    """
    Сквозной E2E-тест расчета рабочей точки на эталонных данных скважины well_01.
    Допуск по ТЗ: 10% по q_liq и p_wf.
    """
    # 1. Расчет IPR
    ipr_q, ipr_p = calculate_ipr(
        p_res=200.0,
        wct=50.0,
        pi=1.0,
        pb=150.0,
        points=21
    )
    assert len(ipr_q) == 21
    assert abs(ipr_q[0] - 139.98) / 139.98 < 0.05
    assert ipr_q[-1] == 0.0

    # 2. Расчет VLP
    pvt = BlackOilPVT(
        wct=50.0,
        rp_m3_t=100.0,
        gamma_oil=0.8,
        gamma_gas=0.7,
        gamma_wat=1.0
    )
    vlp_q, vlp_p = calculate_vlp(
        md_list=[0.0, 1000.0, 1500.0],
        tvd_list=[0.0, 1000.0, 1100.0],
        casing_d=0.1,
        tubing_d=0.062,
        tubing_h_mes=1000.0,
        pvt=pvt,
        p_wh=10.0,
        geo_grad=3.0,
        h_res=1500.0,
        t_res=90.0,
        roughness=0.0001,
        q_max=400.0,
        points=21
    )
    assert len(vlp_q) == 21
    assert abs(vlp_p[0] - 47.48) / 47.48 < 0.05
    assert abs(vlp_p[-1] - 62.16) / 62.16 < 0.05

    # 3. Расчет Nodal (пересечение)
    intersections = solve_nodal_intersection(
        ipr_q=ipr_q,
        ipr_p=ipr_p,
        vlp_q=vlp_q,
        vlp_p=vlp_p
    )
    assert len(intersections) == 1
    q_opt, p_opt = intersections[0]

    # Эталонные значения: q_liq = 128.03 м3/сут, p_wf = 49.61 атм
    # Проверка попадания в допуск E2E 10%
    err_q = abs(q_opt - 128.03) / 128.03
    err_p = abs(p_opt - 49.61) / 49.61

    print(f"\n[E2E Results] q_liq = {q_opt:.2f} (err: {err_q*100:.2f}%), p_wf = {p_opt:.2f} (err: {err_p*100:.2f}%)")
    assert err_q < 0.10, f"Дебит {q_opt} отклоняется более чем на 10% от 128.03"
    assert err_p < 0.10, f"Давление {p_opt} отклоняется более чем на 10% от 49.61"
