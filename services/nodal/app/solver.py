from typing import List, Tuple, Optional


def intersect_segments(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float],
    eps: float = 1e-7
) -> Optional[Tuple[float, float]]:
    """
    Поиск точки пересечения двух отрезков: (p1-p2) и (p3-p4).
    Координаты: (q, p).
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

    if -eps <= t <= 1.0 + eps and -eps <= u <= 1.0 + eps:
        # Ограничиваем t строго внутри [0, 1] для устранения численного шума
        t_clamped = max(0.0, min(1.0, t))
        xi = x1 + t_clamped * (x2 - x1)
        yi = y1 + t_clamped * (y2 - y1)
        return float(xi), float(yi)

    return None


def solve_nodal_intersection(
    ipr_q: List[float],
    ipr_p: List[float],
    vlp_q: List[float],
    vlp_p: List[float]
) -> List[Tuple[float, float]]:
    """
    Поиск точек пересечения двух полилиний IPR и VLP в координатах (q_liq, p_wf).
    """
    poly1 = list(zip(ipr_q, ipr_p))
    poly2 = list(zip(vlp_q, vlp_p))

    intersections: List[Tuple[float, float]] = []

    for i in range(len(poly1) - 1):
        seg1_a = poly1[i]
        seg1_b = poly1[i + 1]
        for j in range(len(poly2) - 1):
            seg2_a = poly2[j]
            seg2_b = poly2[j + 1]
            pt = intersect_segments(seg1_a, seg1_b, seg2_a, seg2_b)
            if pt is not None:
                # Дедупликация пересечений на стыках сегментов
                if not any(abs(pt[0] - ex[0]) < 1e-3 and abs(pt[1] - ex[1]) < 1e-3 for ex in intersections):
                    intersections.append(pt)

    return intersections
