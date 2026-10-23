#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пересобрать чертёж job'а и измерить углы/длины.

Usage: python scripts/recon/measure_figure.py <job_id>
"""
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from geometric_engine.engine import GeometricEngine
from geometric_engine import geom


def _db_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "instance", "formyla.db",
    )


def main():
    job_id = int(sys.argv[1])
    con = sqlite3.connect(_db_path())
    row = con.execute(
        "SELECT problem_text, base_plan_json FROM figure_build_jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    if row is None:
        print(f"job {job_id} not found")
        return
    condition, plan_raw = row
    print("CONDITION:", condition)
    plan = json.loads(plan_raw)

    engine = GeometricEngine()
    engine.settings.auto_fit = False
    svg, ctx = engine.build(plan)

    pts = ctx.points
    print("\nPOINTS:")
    for k, v in sorted(pts.items()):
        print(f"  {k} = ({v[0]:.1f}, {v[1]:.1f})")

    def ang(a, b, c):
        if a in pts and b in pts and c in pts:
            return math.degrees(geom.angle_between_three(pts[a], pts[b], pts[c]))
        return None

    def dist(a, b):
        if a in pts and b in pts:
            return geom.dist(pts[a], pts[b])
        return None

    lines = []
    lines.append("\nANGLES:")
    for name, (a, b, c) in {
        "BAC": ("B", "A", "C"),
        "ABC": ("A", "B", "C"),
        "BCA": ("A", "C", "B"),
        "BOC": ("B", "O", "C"),
    }.items():
        v = ang(a, b, c)
        lines.append(f"  {name} = {v:.2f} deg" if v is not None else f"  {name} = N/A")

    lines.append("\nDISTANCES:")
    for name, (a, b) in {
        "AB": ("A", "B"), "AC": ("A", "C"), "BC": ("B", "C"),
        "BD": ("B", "D"), "CE": ("C", "E"),
        "OA": ("O", "A"), "OB": ("O", "B"), "OC": ("O", "C"),
    }.items():
        d = dist(a, b)
        lines.append(f"  {name} = {d:.2f} px" if d is not None else f"  {name} = N/A")

    if dist("B", "D") and dist("C", "E"):
        lines.append(f"\n  BD - CE = {dist('B','D') - dist('C','E'):.2f} px")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", f"job_{job_id}_measure.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("CONDITION: " + condition + "\n")
        f.write("POINTS:\n")
        for k, v in sorted(pts.items()):
            f.write(f"  {k} = ({v[0]:.1f}, {v[1]:.1f})\n")
        f.write("\n".join(lines))
    print(f"written {out_path}")


if __name__ == "__main__":
    main()
