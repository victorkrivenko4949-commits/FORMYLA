#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/figure_validator.py — Проверяльщик JSON-ответа ризонера.

Разбирает JSON, сверяет со схемой geometric_engine, проверяет:
- Все упомянутые точки (через p1, p2, p3, p4, center) объявлены ранее
- Нет ссылок в никуда (dangling references)
- Движок может построить (валидация через GeometricEngine.validate_description)
- Все обязательные поля (canvas, constructions) присутствуют

Возвращает: {"valid": true} или {"valid": false, "errors": [...]}
"""

import json
import os
import sys
from typing import Any, Dict, List, Tuple

# Добавляем корень проекта
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)


# Поля, которые содержат ссылки на id точек/линий/окружностей
_REFERENCE_FIELDS = ['p1', 'p2', 'p3', 'p4', 'center', 'line1', 'line2',
                     'circle', 'circle1', 'circle2', 'origin']

_KNOWN_TYPES = {
    # Точки
    'free_point', 'midpoint', 'point_on_segment', 'foot_perpendicular',
    'intersect_lines', 'intersect_line_circle', 'intersect_circles',
    'reflect_point_over_point', 'reflect_point_over_line',
    'circumcenter', 'incenter', 'centroid', 'orthocenter', 'incircle_touch',
    # Линии
    'segment', 'ray', 'line', 'line_extension',
    'altitude', 'median', 'angle_bisector', 'perpendicular_bisector',
    'tangent_from_point', 'tangent_at_point',
    # Фигуры
    'triangle_arbitrary', 'triangle_acute', 'triangle_right',
    'triangle_isosceles', 'triangle_equilateral',
    'quadrilateral_arbitrary', 'quadrilateral_parallelogram',
    'quadrilateral_rectangle', 'quadrilateral_square',
    'quadrilateral_rhombus', 'quadrilateral_trapezoid',
    'quadrilateral_isosceles_trapezoid',
    'regular_polygon',
    # Окружности
    'circle_center_radius', 'circumcircle', 'incircle', 'circle_three_points',
    # Дуги
    'arc',
    # Пометки
    'equal_segments_mark', 'equal_angles_mark', 'right_angle_mark',
    'angle_label', 'length_label', 'hatch_region', 'dashed_style',
    # Подписи
    'point_label', 'line_label',
}


def validate_figure_json(figure_data) -> Dict[str, Any]:
    """Проверить JSON-описание чертежа.

    Аргументы:
        figure_data: строка JSON или dict

    Возвращает:
        {"valid": true} или {"valid": false, "errors": ["...", ...]}
    """
    errors = []

    # --- 1. Разбор ---
    if isinstance(figure_data, str):
        try:
            description = json.loads(figure_data)
        except json.JSONDecodeError as e:
            return {"valid": False, "errors": [f"Invalid JSON: {e}"]}
    elif isinstance(figure_data, dict):
        description = figure_data
    else:
        return {"valid": False, "errors": ["Expected JSON string or dict"]}

    # --- 2. Верхний уровень ---
    if not isinstance(description, dict):
        return {"valid": False, "errors": ["Top-level must be an object"]}

    if 'canvas' not in description:
        errors.append("Missing required field: canvas")
    if 'constructions' not in description:
        errors.append("Missing required field: constructions")

    if errors:
        return {"valid": False, "errors": errors}

    # --- 3. Проверка canvas ---
    canvas = description.get('canvas', {})
    if not isinstance(canvas, dict):
        errors.append("canvas must be an object")
    else:
        for field in ['width', 'height', 'margin']:
            if field not in canvas:
                errors.append(f"canvas missing field: {field}")
            elif not isinstance(canvas[field], (int, float)):
                errors.append(f"canvas.{field} must be a number")
            elif canvas[field] < 0:
                errors.append(f"canvas.{field} must be non-negative")

    # --- 4. Проверка constructions ---
    constructions = description.get('constructions', [])
    if not isinstance(constructions, list):
        errors.append("constructions must be an array")
        return {"valid": False, "errors": errors}

    if len(constructions) == 0:
        errors.append("constructions must have at least 1 item")

    # --- 5. Проверка каждого построения + сбор объявленных id ---
    declared_ids = set()
    seen_ids = set()

    for i, c in enumerate(constructions):
        prefix = f"constructions[{i}]"

        if not isinstance(c, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Проверка type
        ctype = c.get('type')
        if not ctype:
            errors.append(f"{prefix}: missing 'type'")
        elif ctype not in _KNOWN_TYPES:
            errors.append(f"{prefix}: unknown type '{ctype}'")

        # Проверка id
        cid = c.get('id')
        if not cid:
            errors.append(f"{prefix}: missing 'id'")
        elif not isinstance(cid, str):
            errors.append(f"{prefix}: 'id' must be a string")
        else:
            if cid in seen_ids:
                errors.append(f"{prefix}: duplicate id '{cid}'")
            seen_ids.add(cid)
            declared_ids.add(cid)

        # Проверка ссылок на другие объекты
        for field in _REFERENCE_FIELDS:
            if field in c:
                ref = c[field]
                if not isinstance(ref, str):
                    errors.append(f"{prefix}: {field} must be a string (id reference)")
                elif ref not in declared_ids:
                    errors.append(f"{prefix}: {field}='{ref}' references undefined id")

    # --- 6. Кросс-проверка: все использованные ссылки — на существующие ---
    for i, c in enumerate(constructions):
        if not isinstance(c, dict):
            continue
        prefix = f"constructions[{i}]"
        for field in _REFERENCE_FIELDS:
            if field in c:
                ref = c[field]
                if isinstance(ref, str) and ref not in declared_ids:
                    errors.append(f"{prefix}: {field}='{ref}' — dangling reference")

    # --- 7. Валидация движком ---
    try:
        from geometric_engine.engine import GeometricEngine
        engine = GeometricEngine()
        engine_errors = engine.validate_description(description)
        for e in engine_errors:
            errors.append(f"Engine validation: {e}")
    except ImportError as e:
        errors.append(f"Engine import failed: {e}")
    except Exception as e:
        errors.append(f"Engine validation error: {e}")

    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True}


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python services/figure_validator.py <figure.json>")
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"File not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)

    result = validate_figure_json(data)
    if result['valid']:
        print("VALID: description is correct")
    else:
        print("INVALID:")
        for err in result['errors']:
            print(f"  - {err}")
    sys.exit(0 if result['valid'] else 1)
