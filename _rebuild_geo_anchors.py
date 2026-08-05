# -*- coding: utf-8 -*-
"""Скрипт для перегенерации всех геометрических чертежей якорей через geometric_engine."""
import json
import os
import sys

# Добавляем корень для импорта geometric_engine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geometric_engine.engine import GeometricEngine, EngineSettings

ANCHORS_DIR = os.path.join("static", "figures", "anchors")

# Настройки движка — тёмная тема
SETTINGS = EngineSettings()
SETTINGS.bg_color = "none"
SETTINGS.line_color = "#c8d6e5"
SETTINGS.point_color = "#e8f0fb"
SETTINGS.label_color = "#d0ddf0"
SETTINGS.mark_color = "#a0b8d8"
SETTINGS.dash_color = "#7a8fa8"
SETTINGS.font_size = 16
SETTINGS.label_font_size = 14
SETTINGS.label_padding = 14.0

# ───────────────────────────────────────────────────────────
# Описания чертежей для каждого гео-якоря
# ───────────────────────────────────────────────────────────

FIGURES = {
    # G5: Прямоугольник + разрез EF
    "A_G5_GEO": {
        "canvas": {"width": 500, "height": 320, "margin": 30},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 60, "y": 250, "label": "A", "side": "bottom_left"},
            {"type": "free_point", "id": "B", "x": 440, "y": 250, "label": "B", "side": "bottom_right"},
            {"type": "free_point", "id": "C", "x": 440, "y": 60, "label": "C", "side": "top_right"},
            {"type": "free_point", "id": "D", "x": 60, "y": 60, "label": "D", "side": "top_left"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "DA", "p1": "D", "p2": "A"},
            {"type": "quadrilateral_rectangle", "id": "rect", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            {"type": "point_on_segment", "id": "E", "p1": "A", "p2": "B", "ratio": 0.45, "label": "E", "side": "bottom"},
            {"type": "point_on_segment", "id": "F", "p1": "D", "p2": "C", "ratio": 0.45, "label": "F", "side": "top"},
            {"type": "segment", "id": "cut", "p1": "E", "p2": "F", "dashed": True},
        ]
    },

    # G6: Куб 3×3×3 (изометрический чертёж)
    "A_G6_GEO": {
        "canvas": {"width": 400, "height": 420, "margin": 30},
        "constructions": [
            # Передняя грань
            {"type": "free_point", "id": "A", "x": 100, "y": 340, "label": "", "side": "auto"},
            {"type": "free_point", "id": "B", "x": 300, "y": 340, "label": "", "side": "auto"},
            {"type": "free_point", "id": "D", "x": 100, "y": 170, "label": "", "side": "auto"},
            {"type": "free_point", "id": "C", "x": 300, "y": 170, "label": "", "side": "auto"},
            # Задняя грань (сдвиг вправо-вверх)
            {"type": "free_point", "id": "A2", "x": 160, "y": 290, "label": "", "side": "auto"},
            {"type": "free_point", "id": "B2", "x": 360, "y": 290, "label": "", "side": "auto"},
            {"type": "free_point", "id": "D2", "x": 160, "y": 120, "label": "", "side": "auto"},
            {"type": "free_point", "id": "C2", "x": 360, "y": 120, "label": "", "side": "auto"},
            # Передняя грань
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "DA", "p1": "D", "p2": "A"},
            # Задняя грань
            {"type": "segment", "id": "A2B2", "p1": "A2", "p2": "B2"},
            {"type": "segment", "id": "B2C2", "p1": "B2", "p2": "C2"},
            {"type": "segment", "id": "C2D2", "p1": "C2", "p2": "D2"},
            {"type": "segment", "id": "D2A2", "p1": "D2", "p2": "A2"},
            # Рёбра между гранями
            {"type": "segment", "id": "AA2", "p1": "A", "p2": "A2"},
            {"type": "segment", "id": "BB2", "p1": "B", "p2": "B2"},
            {"type": "segment", "id": "CC2", "p1": "C", "p2": "C2"},
            {"type": "segment", "id": "DD2", "p1": "D", "p2": "D2"},
            # Линии сетки 3×3 на передней грани (пунктир)
            {"type": "point_on_segment", "id": "pAB1", "p1": "A", "p2": "B", "ratio": 0.333, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pAB2", "p1": "A", "p2": "B", "ratio": 0.667, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pCD1", "p1": "C", "p2": "D", "ratio": 0.333, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pCD2", "p1": "C", "p2": "D", "ratio": 0.667, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pAD1", "p1": "A", "p2": "D", "ratio": 0.333, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pAD2", "p1": "A", "p2": "D", "ratio": 0.667, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pBC1", "p1": "B", "p2": "C", "ratio": 0.333, "label": "", "side": "auto"},
            {"type": "point_on_segment", "id": "pBC2", "p1": "B", "p2": "C", "ratio": 0.667, "label": "", "side": "auto"},
            {"type": "segment", "id": "grid_v1", "p1": "pAB1", "p2": "pCD1", "dashed": True},
            {"type": "segment", "id": "grid_v2", "p1": "pAB2", "p2": "pCD2", "dashed": True},
            {"type": "segment", "id": "grid_h1", "p1": "pAD1", "p2": "pBC1", "dashed": True},
            {"type": "segment", "id": "grid_h2", "p1": "pAD2", "p2": "pBC2", "dashed": True},
        ]
    },

    # G7: Треугольник + высота + биссектриса из C
    "A_G7_GEO": {
        "canvas": {"width": 460, "height": 400, "margin": 30},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 60, "y": 340, "label": "A", "side": "bottom_left"},
            {"type": "free_point", "id": "B", "x": 400, "y": 340, "label": "B", "side": "bottom_right"},
            {"type": "free_point", "id": "C", "x": 200, "y": 60, "label": "C", "side": "top"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CA", "p1": "C", "p2": "A"},
            {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
            # Высота из C на AB
            {"type": "altitude", "id": "h_C", "p1": "C", "p2": "A", "p3": "B", "dashed": True},
            # Биссектриса угла C (A-C-B)
            {"type": "angle_bisector", "id": "bis_C", "p1": "A", "p2": "C", "p3": "B", "dashed": True},
        ]
    },

    # G8: Равнобедренная трапеция + высота
    "A_G8_GEO": {
        "canvas": {"width": 460, "height": 380, "margin": 30},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 80, "y": 320, "label": "A", "side": "bottom_left"},
            {"type": "free_point", "id": "B", "x": 380, "y": 320, "label": "B", "side": "bottom_right"},
            {"type": "free_point", "id": "D", "x": 140, "y": 60, "label": "D", "side": "top_left"},
            {"type": "free_point", "id": "C", "x": 340, "y": 60, "label": "C", "side": "top_right"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "DA", "p1": "D", "p2": "A"},
            {"type": "quadrilateral_isosceles_trapezoid", "id": "trap", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            # Высота: из D перпендикуляр на AB
            {"type": "altitude", "id": "h", "p1": "D", "p2": "A", "p3": "B", "dashed": True},
        ]
    },

    # G9: Трапеция + диагонали + точка O
    "A_G9_GEO": {
        "canvas": {"width": 420, "height": 420, "margin": 30},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 80, "y": 340, "label": "A", "side": "bottom_left"},
            {"type": "free_point", "id": "B", "x": 340, "y": 340, "label": "B", "side": "bottom_right"},
            {"type": "free_point", "id": "D", "x": 140, "y": 60, "label": "D", "side": "top_left"},
            {"type": "free_point", "id": "C", "x": 300, "y": 60, "label": "C", "side": "top_right"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "DA", "p1": "D", "p2": "A"},
            # Диагонали
            {"type": "segment", "id": "AC", "p1": "A", "p2": "C", "dashed": True},
            {"type": "segment", "id": "BD", "p1": "B", "p2": "D", "dashed": True},
            # Точка пересечения диагоналей
            {"type": "intersect_lines", "id": "O", "line1": "AC", "line2": "BD", "label": "O", "side": "left"},
            {"type": "quadrilateral_trapezoid", "id": "trap", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
        ]
    },

    # G10: Окружность + две параллельные хорды
    "A_G10_GEO": {
        "canvas": {"width": 420, "height": 420, "margin": 30},
        "constructions": [
            # Центр окружности
            {"type": "free_point", "id": "O", "x": 210, "y": 210, "label": "O", "side": "right"},
            # Окружность
            {"type": "circle_center_radius", "id": "circle_omega", "center": "O", "radius": 150},
            # Точки для хорд на окружности
            # Хорда 1 (длина 40 в R=25, но здесь в масштабе) — верхняя
            {"type": "free_point", "id": "C1", "x": 110, "y": 130, "label": "", "side": "auto"},
            {"type": "free_point", "id": "D1", "x": 310, "y": 130, "label": "", "side": "auto"},
            # Хорда 2 (длина 30) — ниже
            {"type": "free_point", "id": "C2", "x": 135, "y": 270, "label": "", "side": "auto"},
            {"type": "free_point", "id": "D2", "x": 285, "y": 270, "label": "", "side": "auto"},
            {"type": "segment", "id": "chord1", "p1": "C1", "p2": "D1"},
            {"type": "segment", "id": "chord2", "p1": "C2", "p2": "D2"},
            # Расстояние между хордами (пунктир)
            {"type": "midpoint", "id": "M1", "p1": "C1", "p2": "D1", "label": "", "side": "auto"},
            {"type": "midpoint", "id": "M2", "p1": "C2", "p2": "D2", "label": "", "side": "auto"},
            {"type": "segment", "id": "dist", "p1": "M1", "p2": "M2", "dashed": True},
            # Радиус к центру хорды
            {"type": "segment", "id": "r1", "p1": "O", "p2": "M1", "dashed": True},
        ]
    },

    # G11: Параллелограмм + диагонали
    "A_G11_GEO": {
        "canvas": {"width": 420, "height": 380, "margin": 30},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 60, "y": 320, "label": "A", "side": "bottom_left"},
            {"type": "free_point", "id": "B", "x": 340, "y": 320, "label": "B", "side": "bottom_right"},
            {"type": "free_point", "id": "C", "x": 380, "y": 80, "label": "C", "side": "top_right"},
            {"type": "free_point", "id": "D", "x": 100, "y": 80, "label": "D", "side": "top_left"},
            {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "CD", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "DA", "p1": "D", "p2": "A"},
            {"type": "segment", "id": "AC", "p1": "A", "p2": "C", "dashed": True},
            {"type": "segment", "id": "BD", "p1": "B", "p2": "D", "dashed": True},
            {"type": "quadrilateral_parallelogram", "id": "par", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
        ]
    },
}


def rebuild_all():
    engine = GeometricEngine(SETTINGS)
    results = []

    for uid, desc in FIGURES.items():
        json_path = os.path.join(ANCHORS_DIR, f"{uid}.json")
        svg_path = os.path.join(ANCHORS_DIR, f"{uid}.svg")

        # Сохраняем JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(desc, f, ensure_ascii=False, indent=2)
        print(f"[SAVED] {json_path}")

        # Строим SVG
        errors = engine.validate_description(desc)
        if errors:
            print(f"[ERROR] {uid}: validation errors: {'; '.join(errors)}")
            results.append((uid, False, errors))
            continue

        try:
            svg, ctx, attempts, violations = engine.build_with_retry(desc, seed=42)
        except Exception as e:
            print(f"[ERROR] {uid}: build exception: {e}")
            results.append((uid, False, [str(e)]))
            continue

        if violations:
            print(f"[WARN] {uid}: built but {len(violations)} violations after {attempts} attempts")
            # Всё равно сохраняем
        else:
            print(f"[OK] {uid}: built in {attempts} attempts")

        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"[SAVED] {svg_path} ({len(svg)} bytes)")

        results.append((uid, True, [] if not violations else violations))

    # Итог
    print("\n" + "=" * 60)
    all_ok = True
    for uid, ok, issues in results:
        status = "OK" if ok else "FAIL"
        if issues:
            print(f"  {status}: {uid} — {len(issues)} issue(s)")
            for iss in issues[:3]:
                print(f"    - {iss}")
        else:
            print(f"  {status}: {uid}")
        if not ok:
            all_ok = False
    print("=" * 60)
    return all_ok


if __name__ == "__main__":
    ok = rebuild_all()
    print(f"\nAll good: {ok}")
