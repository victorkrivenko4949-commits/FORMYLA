# -*- coding: utf-8 -*-
"""Render CH15.1 quality fixtures to SVG for visual inspection."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from geometric_engine.engine import GeometricEngine

from tests.test_ch15_quality_pass import (
    _isosceles_base,
    _isosceles_aux,
    _right_triangle_base,
    _right_triangle_aux,
)


def main():
    engine = GeometricEngine()
    engine.settings.bg_color = "#0f172a"
    engine.settings.auto_fit = True

    # Fixture 1: isosceles triangle + altitude AH
    base1 = _isosceles_base()
    merged1 = dict(base1)
    merged1["constructions"] = list(base1["constructions"]) + _isosceles_aux()["constructions"]

    base1_svg, _, _, b1v = engine.build_with_retry(dict(base1))
    aux1_svg, _, _, a1v = engine.build_with_retry(merged1)
    print("fixture1 base violations:", b1v)
    print("fixture1 aux violations:", a1v)

    with open("ch151_f1_base.svg", "w", encoding="utf-8") as f:
        f.write(base1_svg)
    with open("ch151_f1_aux.svg", "w", encoding="utf-8") as f:
        f.write(aux1_svg)

    # Fixture 2: right triangle + circumcircle
    base2 = _right_triangle_base()
    merged2 = dict(base2)
    merged2["constructions"] = list(base2["constructions"]) + _right_triangle_aux()["constructions"]

    base2_svg, _, _, b2v = engine.build_with_retry(dict(base2))
    aux2_svg, _, _, a2v = engine.build_with_retry(merged2)
    print("fixture2 base violations:", b2v)
    print("fixture2 aux violations:", a2v)

    with open("ch151_f2_base.svg", "w", encoding="utf-8") as f:
        f.write(base2_svg)
    with open("ch151_f2_aux.svg", "w", encoding="utf-8") as f:
        f.write(aux2_svg)

    print("Wrote ch151_f1_base.svg, ch151_f1_aux.svg, ch151_f2_base.svg, ch151_f2_aux.svg")


if __name__ == "__main__":
    main()
