import math
from typing import List, Tuple
import numpy as np
from scipy.integrate import solve_ivp

from .pvt import BlackOilPVT, P_ATM_PA

G = 9.80665


def calc_friction_factor(re: float, eps_rel: float) -> float:
    """
    Расчет коэффициента гидравлического сопротивления Дарси f.
    Для ламинарного потока (Re < 2300): f = 64 / Re.
    Для турбулентного потока: итерационное решение уравнения Colebrook-White
    с начальным приближением по формуле Haaland.
    """
    if re < 2300.0:
        return 64.0 / max(re, 1e-4)

    # Начальное приближение по Haaland
    term = ((eps_rel / 3.7) ** 1.11) + (6.9 / max(re, 1e-4))
    inv_sqrt_f = -1.8 * math.log10(max(1e-8, term))
    f = 1.0 / (inv_sqrt_f ** 2)

    # 3-4 итерации Colebrook-White
    for _ in range(4):
        inner = (eps_rel / 3.7) + 2.51 / (re * math.sqrt(f))
        inv_sqrt_f = -2.0 * math.log10(max(1e-8, inner))
        f = 1.0 / (inv_sqrt_f ** 2)

    return f


def calculate_vlp(
    md_list: List[float],
    tvd_list: List[float],
    casing_d: float,
    tubing_d: float,
    tubing_h_mes: float,
    pvt: BlackOilPVT,
    p_wh: float,
    geo_grad: float,
    h_res: float,
    t_res: float,
    roughness: float = 0.0001,
    q_max: float = 400.0,
    points: int = 21
) -> Tuple[List[float], List[float]]:
    """
    Расчет кривой подъема жидкости по стволу скважины (VLP).
    """
    md_arr = np.array(md_list, dtype=np.float64)
    tvd_arr = np.array(tvd_list, dtype=np.float64)

    tvd_res = float(np.interp(h_res, md_arr, tvd_arr))

    # Функция вертикальной глубины
    def get_tvd(md_val: float) -> float:
        return float(np.interp(md_val, md_arr, tvd_arr))

    # Производная dTVD / dMD (кусочно-линейная инклинометрия)
    def get_dtvd_dmd(md_val: float) -> float:
        idx = int(np.searchsorted(md_arr, md_val))
        if idx == 0:
            idx = 1
        elif idx >= len(md_arr):
            idx = len(md_arr) - 1
        d_md = md_arr[idx] - md_arr[idx - 1]
        if d_md <= 1e-9:
            return 1.0
        return (tvd_arr[idx] - tvd_arr[idx - 1]) / d_md

    # Температурный профиль по TVD
    def get_temperature_c(md_val: float) -> float:
        tvd = get_tvd(md_val)
        return t_res - geo_grad * ((tvd_res - tvd) / 100.0)

    # Градиент давления dP/dL (атм/м)
    def dp_dl(l: float, p_atm: float, q_liq: float) -> float:
        p_safe = max(0.05, p_atm)
        t_c = get_temperature_c(l)
        props = pvt.calc_properties(p_safe, t_c)

        vmix = props["vmix"]
        rho_mix = props["rho_mix"]
        mu_mix = props["mu_mix"]

        # Определение диаметра на текущей глубине ствола
        d = tubing_d if l <= tubing_h_mes else casing_d
        area = math.pi * (d ** 2) / 4.0

        if q_liq <= 1e-4:
            v_mix = 0.0
            f = 0.0
        else:
            q_mix_m3_s = (q_liq / 86400.0) * vmix
            v_mix = q_mix_m3_s / area
            mu_pa_s = mu_mix * 1e-3
            re = (rho_mix * v_mix * d) / max(1e-7, mu_pa_s)
            f = calc_friction_factor(re, roughness)

        dtvd_dmd = get_dtvd_dmd(l)
        dp_grav_pa = rho_mix * G * dtvd_dmd
        dp_fric_pa = f * (rho_mix * (v_mix ** 2)) / (2.0 * d)
        dp_total_pa = dp_grav_pa + dp_fric_pa

        return dp_total_pa / P_ATM_PA

    # Сетка дебитов от 0 до q_max
    q_liq_arr = np.linspace(0.0, q_max, points)
    p_wf_list = []

    for q in q_liq_arr:
        # Участок 1: НКТ от 0 до tubing_h_mes
        try:
            sol1 = solve_ivp(
                lambda l, y: [dp_dl(l, y[0], q)],
                [0.0, tubing_h_mes],
                [p_wh],
                method="RK45",
                rtol=1e-5,
                atol=1e-5
            )
            if not sol1.success:
                # Fallback на RK23
                sol1 = solve_ivp(
                    lambda l, y: [dp_dl(l, y[0], q)],
                    [0.0, tubing_h_mes],
                    [p_wh],
                    method="RK23",
                    rtol=1e-4,
                    atol=1e-4
                )
            p_mid = sol1.y[0][-1]
        except Exception:
            p_mid = p_wh + 30.0

        # Участок 2: Эксплуатационная колонна от tubing_h_mes до h_res
        if h_res > tubing_h_mes:
            try:
                sol2 = solve_ivp(
                    lambda l, y: [dp_dl(l, y[0], q)],
                    [tubing_h_mes, h_res],
                    [p_mid],
                    method="RK45",
                    rtol=1e-5,
                    atol=1e-5
                )
                if not sol2.success:
                    sol2 = solve_ivp(
                        lambda l, y: [dp_dl(l, y[0], q)],
                        [tubing_h_mes, h_res],
                        [p_mid],
                        method="RK23",
                        rtol=1e-4,
                        atol=1e-4
                    )
                p_bottom = sol2.y[0][-1]
            except Exception:
                p_bottom = p_mid + 15.0
        else:
            p_bottom = p_mid

        p_wf_list.append(round(float(p_bottom), 2))

    q_res = [round(float(q), 1) for q in q_liq_arr]
    return q_res, p_wf_list
