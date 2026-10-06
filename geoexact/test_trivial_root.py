# -*- coding: utf-8 -*-
"""Пересечение не должно «строить» уже существующую точку.

Треугольник ABC, ∠C = 60°, AM — медиана, AM = 6, BC = 12 (∠A = 90°).
Доп. построение «D на BC, AD = AC»: прямая BC пересекает окружность
(A, |AC|) в C и в D. Раньше при неудачном value получалась D = C."""
import math
import numpy as np
import pytest

from geoexact.core.constructions import _circle_circle, _line_circle
from geoexact.core.schema import PlanError

A = np.array([0.0, 0.0]); C = np.array([0.0, 6.0]); B = np.array([6 * math.sqrt(3), 0.0])
M = 0.5 * (B + C)


@pytest.mark.parametrize("value", [0, 1])
def test_line_circle_skips_the_known_point_C(value):
    D = _line_circle(B, C, A, C, value=value)
    assert np.linalg.norm(D - C) > 1.0
    assert abs(np.linalg.norm(D - A) - 6.0) < 1e-9          # AD = AC
    assert abs(np.linalg.norm(D - M)) < 1e-9                 # здесь D = M (ΔACD правильный)


@pytest.mark.parametrize("value", [0, 1])
def test_line_circle_skips_the_line_endpoint(value):
    # удвоение медианы: прямая AM, окружность (M, |MA|): корни A и D
    D = _line_circle(A, M, M, A, value=value)
    assert np.linalg.norm(D - A) > 1.0
    assert np.linalg.norm(D - (2 * M - A)) < 1e-9


def test_line_circle_without_a_known_root_respects_value():
    O = np.array([0.0, 0.0]); P = np.array([-10.0, 1.0]); Q = np.array([10.0, 1.0]); R = np.array([5.0, 0.0])
    r0, r1 = _line_circle(P, Q, O, R, value=0), _line_circle(P, Q, O, R, value=1)
    assert r0[0] < 0 < r1[0]


def test_tangency_keeps_the_single_root():
    P = np.array([-1.0, 5.0]); Q = np.array([1.0, 5.0]); O = np.array([0.0, 0.0]); R = np.array([5.0, 0.0])
    assert np.linalg.norm(_line_circle(P, Q, O, R, value=0) - [0.0, 5.0]) < 1e-9


@pytest.mark.parametrize("value", [0, 1])
def test_circle_circle_skips_the_shared_known_point(value):
    # окружности (A,|AB|) и (C,|CB|) пересекаются в B и в B' (отражение B в AC)
    X = _circle_circle(A, B, C, B, value=value)
    assert np.linalg.norm(X - B) > 1.0
    assert np.linalg.norm(X - np.array([-B[0], B[1]])) < 1e-9


def test_disjoint_circles_still_fail():
    with pytest.raises(PlanError):
        _circle_circle(A, np.array([1.0, 0.0]), np.array([10.0, 0.0]), np.array([11.0, 0.0]), value=0)
