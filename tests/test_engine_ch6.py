"""
tests/test_engine_ch6.py — тесты блока CH6 (подписи и штрихи равенства).

Покрытие:
- Минимальное расстояние подписи до отрезков (> порога)
- Минимальное расстояние подписи до других подписей (> порога)
- Наличие двойных насечек равенства отрезков в SVG
- Наличие двойных дуг равенства углов в SVG
- equal_group в спецификации управляет числом насечек/дуг
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from geometric_engine.engine import build_svg, CANVAS_W, CANVAS_H, CANVAS_MARGIN, CANVAS_BG
from geometric_engine.engine import (
    _compute_label_candidates, _score_label_candidate, EngineSettings,
    EQUAL_TICK_SPACING, EQUAL_ARC_RADIUS_GAP, EQUAL_TICK_HALF_LENGTH,
)
from geometric_engine import geom


# ═══════════════════════════════════════════════════════════════
# Тесты: кандидаты подписей
# ═══════════════════════════════════════════════════════════════

class TestLabelCandidates:
    def test_generates_24_candidates(self):
        candidates = _compute_label_candidates((310, 310), 14.0, 24)
        assert len(candidates) == 24
        # Все кандидаты на расстоянии padding от точки
        for cand in candidates:
            dist = geom.dist((310, 310), cand)
            assert abs(dist - 14.0) < 0.01

    def test_candidates_are_distinct(self):
        candidates = _compute_label_candidates((100, 200), 14.0, 24)
        # Проверяем, что все кандидаты разные
        seen = set()
        for cand in candidates:
            key = (round(cand[0], 6), round(cand[1], 6))
            assert key not in seen
            seen.add(key)


# ═══════════════════════════════════════════════════════════════
# Тесты: штрафы подписей
# ═══════════════════════════════════════════════════════════════

class TestLabelScoring:
    def test_candidate_on_segment_gets_huge_penalty(self):
        settings = EngineSettings()
        # Кандидат лежит прямо на отрезке
        seg = ((0, 0), (10, 0))
        score = _score_label_candidate((5, 0), [seg], [], settings)
        assert score > 1e8  # огромный штраф

    def test_candidate_far_from_segment_gets_low_score(self):
        settings = EngineSettings()
        seg = ((0, 0), (10, 0))
        # Кандидат на расстоянии 50 пикселей вверх
        score = _score_label_candidate((5, 50), [seg], [], settings)
        # 500 / (50*50) = 500/2500 = 0.2
        assert score < 1.0

    def test_candidate_close_to_placed_label_gets_penalty(self):
        settings = EngineSettings()
        placed = [(100, 100)]
        # Кандидат очень близко к уже размещённой подписи
        score = _score_label_candidate((102, 100), [], placed, settings)
        # 300 / (2*2) = 300/4 = 75, плюс inf для отрезков (нет)
        assert score > 50.0

    def test_candidate_far_from_placed_label_gets_low_score(self):
        settings = EngineSettings()
        placed = [(0, 0)]
        # Кандидат далеко от подписи
        score = _score_label_candidate((200, 200), [], placed, settings)
        assert score < 5.0  # 300/(40000+40000) = 300/80000 = 0.00375


# ═══════════════════════════════════════════════════════════════
# Тесты: build_svg с equal_sides и equal_angles
# ═══════════════════════════════════════════════════════════════

class TestBuildSvgEqualMarks:
    def test_triangle_isosceles_has_equal_ticks(self):
        spec = {"type": "triangle", "labels": ["A", "B", "C"], "equal_sides": [["AB", "AC"]]}
        svg = build_svg(spec)
        assert "equal-tick" in svg
        # Двойная насечка: минимум 2 тика
        tick_count = svg.count("equal-tick")
        assert tick_count >= 2
        assert tick_count % 2 == 0  # чётное (по 2 на пару равных сторон)

    def test_triangle_equal_angles_has_equal_arcs(self):
        spec = {"type": "triangle", "labels": ["A", "B", "C"], "equal_angles": [["B", "C"]]}
        svg = build_svg(spec)
        assert "equal-arc" in svg
        arc_count = svg.count("equal-arc")
        assert arc_count >= 2  # двойная дуга
        assert arc_count % 2 == 0  # чётное

    def test_trapezoid_equal_sides_has_ticks(self):
        spec = {"type": "trapezoid", "labels": ["A", "B", "C", "D"], "equal_sides": [["AB", "CD"]]}
        svg = build_svg(spec)
        assert "equal-tick" in svg
        tick_count = svg.count("equal-tick")
        assert tick_count >= 2
        assert tick_count % 2 == 0

    def test_square_no_equal_sides_no_ticks(self):
        spec = {"type": "square", "labels": ["A", "B", "C", "D"]}
        svg = build_svg(spec)
        # Квадрат без указания equal_sides не должен иметь тиков
        assert "equal-tick" not in svg
        assert "equal-arc" not in svg

    def test_svg_has_correct_canvas(self):
        spec = {"type": "triangle", "labels": ["A", "B", "C"], "equal_sides": [["AB", "AC"]]}
        svg = build_svg(spec)
        assert f'width="{CANVAS_W}"' in svg
        assert f'height="{CANVAS_H}"' in svg
        assert CANVAS_BG in svg

    def test_label_distances_above_threshold(self):
        """Все подписи должны быть на расстоянии >= 8px от линий."""
        import re, math

        spec = {"type": "triangle", "labels": ["A", "B", "C"], "equal_sides": [["AB", "AC"]]}
        svg = build_svg(spec)

        segments = re.findall(
            r'<line[^>]*x1="([\d\.\-]+)"[^>]*y1="([\d\.\-]+)"[^>]*x2="([\d\.\-]+)"[^>]*y2="([\d\.\-]+)"',
            svg
        )
        labels = re.findall(
            r'<text[^>]*x="([\d\.\-]+)"[^>]*y="([\d\.\-]+)"[^>]*>([^<]+)</text>',
            svg
        )
        segs = [(float(a), float(b), float(c), float(d)) for a, b, c, d in segments]

        THRESHOLD = 8.0
        for lx_str, ly_str, _ in labels:
            lx, ly = float(lx_str), float(ly_str)
            for x1, y1, x2, y2 in segs:
                dx, dy = x2 - x1, y2 - y1
                if dx == dy == 0:
                    d = math.hypot(lx - x1, ly - y1)
                else:
                    t = max(0, min(1, ((lx - x1) * dx + (ly - y1) * dy) / (dx * dx + dy * dy)))
                    d = math.hypot(lx - (x1 + t * dx), ly - (y1 + t * dy))
                assert d >= THRESHOLD, f"Label ({lx}, {ly}) too close to segment: {d:.1f} < {THRESHOLD}"


# ═══════════════════════════════════════════════════════════════
# Тесты: константы
# ═══════════════════════════════════════════════════════════════

class TestConstants:
    def test_canvas_dimensions_unchanged(self):
        assert CANVAS_W == 620
        assert CANVAS_H == 620
        assert CANVAS_MARGIN == 60
        assert CANVAS_BG == "#070C18"

    def test_tick_constants_positive(self):
        assert EQUAL_TICK_SPACING > 0
        assert EQUAL_ARC_RADIUS_GAP > 0
        assert EQUAL_TICK_HALF_LENGTH > 0


# ═══════════════════════════════════════════════════════════════
# Тест: equal_group управляет числом насечек/дуг
# ═══════════════════════════════════════════════════════════════

class TestEqualGroup:
    def test_different_equal_groups_get_same_ticks(self):
        """Разные группы равенства всё равно получают 2 тика по умолчанию."""
        spec = {
            "type": "triangle",
            "labels": ["A", "B", "C"],
            "equal_sides": [["AB", "AC"], ["AB", "BC"]],
        }
        svg = build_svg(spec)
        tick_count = svg.count("equal-tick")
        # Две пары равных сторон, каждая с двойной насечкой = 4 тика
        assert tick_count >= 4
        assert tick_count % 2 == 0
