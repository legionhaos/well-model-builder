import math
from typing import List, Tuple
import numpy as np


def calculate_ipr(
    p_res: float,
    wct: float,
    pi: float,
    pb: float,
    points: int = 21
) -> Tuple[List[float], List[float]]:
    """
    Расчет индикаторной диаграммы притока (IPR) по методике Composite IPR (Brown, 1984).
    
    Спецификация:
    - p_wf: равномерная сетка от 1.0 атм до p_res
    - p_wf[0] = 1.0, p_wf[-1] = p_res
    - q_liq[-1] = 0.0
    - q_liq не возрастает с ростом p_wf
    - при wct = 100 - линейная модель
    - при p_wf >= pb - линейная модель по pi
    - при wct = 0 и p_wf < pb - модель Вогеля
    """
    p_wf_arr = np.linspace(1.0, p_res, points)
    
    if pi <= 0:
        return [0.0] * points, [round(float(p), 4) for p in p_wf_arr]
        
    F_w = wct / 100.0
    F_o = 1.0 - F_w
    pb_eff = min(pb, p_res)
    
    # Режим 1: Чисто линейная модель (100% воды или pb <= 0 или пластовое давление ниже 0)
    if F_w >= 1.0 or pb_eff <= 0:
        q_liq_arr = pi * (p_res - p_wf_arr)
        q_liq_arr = np.maximum(0.0, q_liq_arr)
        q_liq_arr[-1] = 0.0
        return [round(float(q), 4) for q in q_liq_arr], [round(float(p), 4) for p in p_wf_arr]
        
    qb = pi * (p_res - pb_eff)
    q_omax = qb + (pi * pb_eff) / 1.8
    
    # Режим 2: Чистая нефть (wct = 0)
    if F_o >= 1.0:
        q_liq = []
        for p in p_wf_arr:
            if p >= pb_eff:
                q = pi * (p_res - p)
            else:
                # Vogel
                ratio = p / pb_eff
                q = qb + ((pi * pb_eff) / 1.8) * (1.0 - 0.2 * ratio - 0.8 * (ratio ** 2))
            q_liq.append(max(0.0, float(q)))
        q_liq[-1] = 0.0
        return [round(q, 4) for q in q_liq], [round(float(p), 4) for p in p_wf_arr]
        
    # Режим 3: Двухфазный приток (Composite Brown, 1984)
    P_wfG = F_w * (p_res - q_omax / pi)
    denom = 0.125 * F_o * pb_eff
    
    q_liq = []
    for p in p_wf_arr:
        if p >= pb_eff:
            # Зона выше давления насыщения: однофазный линейный приток
            q = pi * (p_res - p)
        elif p >= P_wfG and denom > 1e-9 and (q_omax - qb) > 1e-9:
            # Зона 2: Аналитическое решение квадратного уравнения Брауна
            A = (p + denom - F_w * p_res) / denom
            B = F_w / (denom * pi)
            dq = q_omax - qb
            C = 2.0 * A * B + 80.0 / dq
            D = (A ** 2) - 80.0 * (qb / dq) - 81.0
            discriminant = (C ** 2) - 4.0 * (B ** 2) * D
            if discriminant < 0:
                discriminant = 0.0
            q = (-C + math.sqrt(discriminant)) / (2.0 * (B ** 2))
        else:
            # Зона 3: Ниже граничного давления P_wfG (касательное продолжение)
            CG = 0.001 * q_omax
            dq = max(1e-6, q_omax - qb)
            term_under_sqrt = 81.0 - 80.0 * (0.999 * q_omax - qb) / dq
            term_under_sqrt = max(0.0, term_under_sqrt)
            CD = F_w * (CG / pi) + denom * (-1.0 + math.sqrt(term_under_sqrt))
            tan_beta = CD / CG if CG > 1e-9 else 1.0
            if abs(tan_beta) > 1e-9:
                q = (P_wfG + q_omax * tan_beta - p) / tan_beta
            else:
                q = q_omax
                
        q = max(0.0, float(q))
        q_liq.append(q)
        
    # Обеспечение монотонности (q_liq не возрастает с ростом p_wf)
    for i in range(1, len(q_liq)):
        if q_liq[i] > q_liq[i - 1]:
            q_liq[i] = q_liq[i - 1]
            
    q_liq[-1] = 0.0
    
    return [round(q, 4) for q in q_liq], [round(float(p), 4) for p in p_wf_arr]
