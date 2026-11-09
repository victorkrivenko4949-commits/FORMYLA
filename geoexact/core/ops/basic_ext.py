"""Пример расширения: середина дуги (второе пересечение серединного перпендикуляра)."""
import numpy as np

from ..constructions import _circumcenter, _norm, register_op
from ..schema import PlanError


def _arc_midpoint(A, B, C, value=None):
    """Середина дуги AB описанной окружности ABC, не содержащей C."""
    O = _circumcenter(A, B, C)
    r = _norm(A - O)
    ab = B - A
    if _norm(ab) < 1e-12:
        raise PlanError("DEGENERATE", "arc_midpoint: A и B совпадают")
    n = np.array([-ab[1], ab[0]]) / _norm(ab)
    P, Q = O + n * r, O - n * r
    # дуга без C: точка по другую сторону от AB, чем C
    s = lambda X: float(ab[0] * (X - A)[1] - ab[1] * (X - A)[0])  # noqa: E731
    return np.asarray(P if s(P) * s(C) < 0 else Q, float)



register_op("arc_midpoint", _arc_midpoint, 3,
            "середина дуги AB описанной окружности ABC, не содержащей C")
