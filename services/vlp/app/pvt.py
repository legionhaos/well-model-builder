import math
from typing import Dict, Any, Tuple

# Константы перевода единиц
P_ATM_PA = 101325.0
ATM_TO_PSI = 14.6959487755
PSI_TO_ATM = 1.0 / ATM_TO_PSI
M3_TO_SCF = 35.3146667
BBL_TO_M3 = 0.1589873
# 1 м3/м3 = 5.61458333 scf/STB
M3M3_TO_SCFSTB = 5.61458333
SCFSTB_TO_M3M3 = 1.0 / M3M3_TO_SCFSTB

# Коэффициенты полинома Демпси (Dempsey, 1965) для вязкости газа
DEMPSEY_COEFFS = [
    -2.46211820, 2.97054714, -0.286264054, 8.05420522e-3,
    2.80860949, -3.49803305, 0.360373020, -1.04432413e-2,
    -0.793385684, 1.39643306, -0.149144925, 4.41015512e-3,
    8.39387178e-2, -0.186408848, 2.03367881e-2, -6.09579263e-4
]


class BlackOilPVT:
    """
    Модель PVT Black-Oil со встроенными корреляциями по ТЗ раздела 7.2.
    """

    def __init__(
        self,
        wct: float,
        rp_m3_t: float,
        gamma_oil: float,
        gamma_gas: float,
        gamma_wat: float
    ):
        self.wct = wct
        self.rp_m3_t = rp_m3_t
        self.gamma_oil = gamma_oil
        self.gamma_gas = gamma_gas
        self.gamma_wat = gamma_wat

        # Плотность в градусах API
        self.api = 141.5 / max(1e-4, gamma_oil) - 131.5

        # Газовый фактор: rp (м3/т) -> (м3/м3) через плотность нефти gamma_oil
        self.rp_m3_m3 = rp_m3_t * gamma_oil
        # (м3/м3) -> (scf/STB)
        self.rp_scf_stb = self.rp_m3_m3 * M3M3_TO_SCFSTB

        # Плотность газа при стандартных условиях (20 °C = 293.15 K, 1 атм = 101325 Па)
        # R = 8.3144626 Дж/(моль*К), M_возд = 0.0289647 кг/моль
        self.rho_g_sc = (P_ATM_PA * 0.0289647 * gamma_gas) / (8.3144626 * 293.15)

        # Псевдокритические параметры газа (Sutton / Standing)
        self.ppc = 756.8 - 131.0 * gamma_gas - 3.6 * (gamma_gas ** 2)
        self.tpc = 169.2 + 349.5 * gamma_gas - 74.0 * (gamma_gas ** 2)

    def calc_bubble_point(self, t_c: float) -> Tuple[float, float]:
        """
        Расчет давления насыщения Pb (Standing, 1947).
        Возвращает Pb в атм и psia.
        """
        t_f = 1.8 * t_c + 32.0
        exponent = 0.00091 * t_f - 0.0125 * self.api
        term = ((self.rp_scf_stb / max(1e-4, self.gamma_gas)) ** 0.83) * (10.0 ** exponent) - 1.4
        if term <= 0:
            pb_psia = 14.696
        else:
            pb_psia = 18.2 * term
        pb_atm = pb_psia * PSI_TO_ATM
        return pb_atm, pb_psia

    def calc_properties(self, p_atm: float, t_c: float) -> Dict[str, float]:
        """
        Расчет свойств флюидов и гомогенной смеси при давлении p_atm и температуре t_c (°C).
        """
        p_safe = max(0.05, p_atm)
        p_psia = p_safe * ATM_TO_PSI
        t_f = 1.8 * t_c + 32.0
        t_r = t_f + 459.67
        t_k = t_c + 273.15

        pb_atm, pb_psia = self.calc_bubble_point(t_c)

        # 1. Газосодержание Rs (Standing, 1947)
        if p_psia >= pb_psia:
            rs_scf_stb = self.rp_scf_stb
        else:
            exp_term = 0.0125 * self.api - 0.00091 * t_f
            inner = (p_psia / 18.2 + 1.4) * (10.0 ** exp_term)
            if inner <= 0:
                rs_scf_stb = 0.0
            else:
                rs_scf_stb = self.gamma_gas * (inner ** 1.2048)
            rs_scf_stb = min(self.rp_scf_stb, max(0.0, rs_scf_stb))

        rs_m3_m3 = rs_scf_stb * SCFSTB_TO_M3M3

        # 2. Объемный коэффициент нефти Bo (Standing 1947 для насыщенной, Vasquez-Beggs 1980 для недонасыщенной)
        def _calc_bo_sat(rs_val: float) -> float:
            term = rs_val * math.sqrt(self.gamma_gas / max(1e-4, self.gamma_oil)) + 1.25 * t_f
            return 0.9759 + 0.00012 * (term ** 1.2)

        bob = _calc_bo_sat(self.rp_scf_stb)
        if p_psia <= pb_psia:
            bo = _calc_bo_sat(rs_scf_stb)
        else:
            # Сжимаемость недонасыщенной нефти по Vasquez-Beggs (1980)
            co = (-1433.0 + 5.0 * self.rp_scf_stb + 17.2 * t_f - 1180.0 * self.gamma_gas + 12.61 * self.api) / (
                1e5 * max(1e-3, p_psia)
            )
            bo = bob * math.exp(-co * (p_psia - pb_psia))
        bo = max(1.0, bo)

        # 3. Вязкость нефти (Beggs-Robinson 1975 + Vasquez-Beggs 1980)
        # Дегазированная нефть
        x = (10.0 ** (3.0324 - 0.02023 * self.api)) * (t_f ** (-1.163))
        mu_od = max(1e-3, (10.0 ** x) - 1.0)

        # Насыщенная нефть при Rs
        a_br = 10.715 * ((rs_scf_stb + 100.0) ** (-0.515))
        b_br = 5.44 * ((rs_scf_stb + 150.0) ** (-0.338))
        mu_os = a_br * (mu_od ** b_br)

        if p_psia <= pb_psia:
            mu_o = mu_os
        else:
            # Недонасыщенная нефть по Vasquez-Beggs
            a_br_b = 10.715 * ((self.rp_scf_stb + 100.0) ** (-0.515))
            b_br_b = 5.44 * ((self.rp_scf_stb + 150.0) ** (-0.338))
            mu_ob = a_br_b * (mu_od ** b_br_b)
            m_vb = 2.6 * (p_psia ** 1.187) * math.exp(-11.513 - 8.98e-5 * p_psia)
            mu_o = mu_ob * ((p_psia / max(1e-3, pb_psia)) ** m_vb)
        mu_o = max(1e-3, mu_o)

        # 4. Свойства газа (Идеальный газ z=1, CKB 1954 + Dempsey 1965)
        bg = (1.0 / p_safe) * (t_k / 293.15)
        rho_g = self.rho_g_sc / max(1e-6, bg)

        # Вязкость газа: атмосферная по Standing 1977
        mu_1 = (1.709e-5 - 2.062e-6 * self.gamma_gas) * t_f + 8.188e-3 - 6.15e-3 * math.log10(max(1e-4, self.gamma_gas))
        ppr = p_psia / max(1e-4, self.ppc)
        tpr = t_r / max(1e-4, self.tpc)

        sum_dempsey = 0.0
        for i in range(4):
            for j in range(4):
                sum_dempsey += DEMPSEY_COEFFS[4 * i + j] * (tpr ** i) * (ppr ** j)
        mu_g = (mu_1 / tpr) * math.exp(sum_dempsey)
        mu_g = max(1e-4, mu_g)

        # 5. Свойства воды (несжимаемая)
        rho_w = 1000.0 * self.gamma_wat
        mu_w = 1.0  # сП
        bw = 1.0

        # 6. Свойства смеси (Линейное смешение без скольжения)
        fw = self.wct / 100.0
        fo = 1.0 - fw

        vo = fo * bo
        vw = fw * bw
        free_gas_sc = fo * max(0.0, self.rp_m3_m3 - rs_m3_m3)
        vg = free_gas_sc * bg

        vmix = vo + vw + vg
        vmix = max(1e-4, vmix)

        lo = vo / vmix
        lw = vw / vmix
        lg = vg / vmix

        rho_o = (1000.0 * self.gamma_oil + rs_m3_m3 * self.rho_g_sc) / max(1e-3, bo)
        rho_mix = lo * rho_o + lw * rho_w + lg * rho_g
        mu_mix = lo * mu_o + lw * mu_w + lg * mu_g

        return {
            "vmix": vmix,
            "rho_mix": rho_mix,
            "mu_mix": mu_mix,
            "pb_atm": pb_atm,
            "rs_m3_m3": rs_m3_m3,
            "bo": bo
        }



