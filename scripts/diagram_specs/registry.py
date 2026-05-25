"""Generator registry: short string keys -> callables."""
from __future__ import annotations

from typing import Any, Callable, Dict

from matplotlib.figure import Figure

from . import circles, combinatorial, quads, triangles

GENERATORS: Dict[str, Callable[[Dict[str, Any]], Figure]] = {
    # triangles
    "triangle_with_circumcircle": triangles.triangle_with_circumcircle,
    "triangle_with_incircle":     triangles.triangle_with_incircle,
    "triangle_with_median":       triangles.triangle_with_median,
    "triangle_with_altitude":     triangles.triangle_with_altitude,
    "right_triangle_with_hypotenuse_circle": triangles.right_triangle_with_hypotenuse_circle,
    "isoceles_triangle":          triangles.isoceles_triangle,
    # circles
    "two_circles_external_tangent": circles.two_circles_external_tangent,
    "two_circles_internal_tangent": circles.two_circles_internal_tangent,
    "chord_with_inscribed_angle":   circles.chord_with_inscribed_angle,
    "tangent_from_external_point":  circles.tangent_from_external_point,
    "two_intersecting_chords":      circles.two_intersecting_chords,
    # quads / polygons
    "parallelogram":            quads.parallelogram,
    "trapezoid":                quads.trapezoid,
    "cyclic_quadrilateral":     quads.cyclic_quadrilateral,
    "tangential_quadrilateral": quads.tangential_quadrilateral,
    "regular_polygon":          quads.regular_polygon,
    # combinatorial
    "grid_of_points":           combinatorial.grid_of_points,
    "colored_squares_4x4":      combinatorial.colored_squares_4x4,
    "number_line_segment":      combinatorial.number_line_segment,
}


def get_generator(name: str) -> Callable[[Dict[str, Any]], Figure]:
    if name not in GENERATORS:
        raise KeyError(f"unknown generator: {name!r} (known: {sorted(GENERATORS)})")
    return GENERATORS[name]
