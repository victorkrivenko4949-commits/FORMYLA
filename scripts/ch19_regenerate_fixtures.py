# -*- coding: utf-8 -*-
"""Сгенерировать SVG для трёх регрессионных фикстур CH19 и проверить инварианты."""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.test_ch19_visual_defects import (  # noqa: E402
    fan_of_rays_5,
    triangle_with_var_labels,
    isosceles_ok,
)
from geometric_engine.engine import GeometricEngine, run_all_checks  # noqa: E402

OUT = os.path.join("output", "ch19", "fixtures")
NS = "{http://www.w3.org/2000/svg}"


def build_and_save(name, constructions, auto_fit):
    engine = GeometricEngine()
    engine.settings.semantic_colors = True
    engine.settings.auto_fit = auto_fit
    engine.settings.bg_color = "#0b1020"
    spec = {"canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": constructions}
    svg, ctx = engine.build(spec)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    check = run_all_checks(ctx, 600, 500, 40, engine.settings)
    return path, check


def main():
    results = []
    results.append(build_and_save("fan_of_rays_5", fan_of_rays_5(), auto_fit=True))
    results.append(build_and_save("triangle_with_var_labels", triangle_with_var_labels(), auto_fit=True))
    results.append(build_and_save("isosceles_ok", isosceles_ok(), auto_fit=True))

    for (path, check) in results:
        print(f"{os.path.basename(path)}: passed={check.passed}")
        for v in check.violations:
            print("   -", v)

    # Дополнительно: проверить, что "len_AB" не попал в SVG.
    tpath = os.path.join(OUT, "triangle_with_var_labels.svg")
    txt = open(tpath, encoding="utf-8").read()
    assert "len_AB" not in txt, "len_AB leaked into SVG!"
    print("triangle_with_var_labels: no 'len_AB' in SVG (OK)")


if __name__ == "__main__":
    main()
