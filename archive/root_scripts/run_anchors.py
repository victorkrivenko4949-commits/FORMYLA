"""
run_anchors.py - прогон 7 геометрических якорей через движок.
Собирает статистику: попытки, отказы, нарушения.
"""
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from geometric_engine.engine import GeometricEngine


ANCHOR_DESCRIPTIONS = {

    "A_G5_GEO": {
        "canvas": {"width": 800, "height": 500, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 150, "y": 350},
            {"type": "free_point", "id": "B", "x": 650, "y": 350},
            {"type": "free_point", "id": "C", "x": 650, "y": 150},
            {"type": "free_point", "id": "D", "x": 150, "y": 150},
            {"type": "quadrilateral_rectangle", "id": "rect", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            {"type": "free_point", "id": "E", "x": 300, "y": 350},
            {"type": "free_point", "id": "F", "x": 300, "y": 150},
            {"type": "segment", "id": "cut", "p1": "E", "p2": "F", "dashed": True}
        ]
    },

    "A_G6_GEO": {
        "canvas": {"width": 800, "height": 600, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 250, "y": 420},
            {"type": "free_point", "id": "B", "x": 450, "y": 420},
            {"type": "free_point", "id": "C", "x": 450, "y": 220},
            {"type": "free_point", "id": "D", "x": 250, "y": 220},
            {"type": "quadrilateral_square", "id": "front", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            {"type": "free_point", "id": "A2", "x": 330, "y": 340},
            {"type": "free_point", "id": "B2", "x": 530, "y": 340},
            {"type": "free_point", "id": "C2", "x": 530, "y": 140},
            {"type": "free_point", "id": "D2", "x": 330, "y": 140},
            {"type": "quadrilateral_square", "id": "back", "p1": "A2", "p2": "B2", "p3": "C2", "p4": "D2"},
            {"type": "segment", "id": "e1", "p1": "A", "p2": "A2"},
            {"type": "segment", "id": "e2", "p1": "B", "p2": "B2"},
            {"type": "segment", "id": "e3", "p1": "C", "p2": "C2"},
            {"type": "segment", "id": "e4", "p1": "D", "p2": "D2"}
        ]
    },

    "A_G7_GEO": {
        "canvas": {"width": 800, "height": 600, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 150, "y": 450},
            {"type": "free_point", "id": "B", "x": 600, "y": 450},
            {"type": "free_point", "id": "C", "x": 350, "y": 120},
            {"type": "triangle_arbitrary", "id": "tri", "p1": "A", "p2": "B", "p3": "C"},
            {"type": "altitude", "id": "h_C", "p1": "C", "p2": "A", "p3": "B", "dashed": True},
            {"type": "angle_bisector", "id": "bis_C", "p1": "A", "p2": "C", "p3": "B"},
            {"type": "right_angle_mark", "id": "ra", "p1": "C", "p2": "h_C_foot", "p3": "A"},
            {"type": "point_label", "id": "lbl_foot", "p1": "h_C_foot", "label": "H", "side": "bottom"},
            {"type": "point_label", "id": "lbl_C", "p1": "C", "label": "C", "side": "top"}
        ]
    },

    "A_G8_GEO": {
        "canvas": {"width": 800, "height": 550, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 200, "y": 420},
            {"type": "free_point", "id": "B", "x": 600, "y": 420},
            {"type": "free_point", "id": "C", "x": 500, "y": 120},
            {"type": "free_point", "id": "D", "x": 300, "y": 120},
            {"type": "quadrilateral_isosceles_trapezoid", "id": "trap", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            {"type": "segment", "id": "s1", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "s2", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "s3", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "s4", "p1": "D", "p2": "A"},
            {"type": "foot_perpendicular", "id": "H", "p1": "D", "line1": "s1"},
            {"type": "segment", "id": "h", "p1": "D", "p2": "H", "dashed": True},
            {"type": "right_angle_mark", "id": "r1", "p1": "D", "p2": "H", "p3": "A"},
            {"type": "point_label", "id": "lbl_H", "p1": "H", "label": "H", "side": "bottom"}
        ]
    },

    "A_G9_GEO": {
        "canvas": {"width": 800, "height": 550, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 150, "y": 430},
            {"type": "free_point", "id": "B", "x": 650, "y": 430},
            {"type": "free_point", "id": "C", "x": 530, "y": 110},
            {"type": "free_point", "id": "D", "x": 270, "y": 110},
            {"type": "quadrilateral_trapezoid", "id": "trap", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            {"type": "segment", "id": "s1", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "s2", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "s3", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "s4", "p1": "D", "p2": "A"},
            {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
            {"type": "segment", "id": "BD", "p1": "B", "p2": "D"},
            {"type": "intersect_lines", "id": "O", "line1": "AC", "line2": "BD"}
        ]
    },

    "A_G10_GEO": {
        "canvas": {"width": 800, "height": 600, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "O", "x": 400, "y": 300},
            {"type": "circle_center_radius", "id": "circle", "center": "O", "radius": 200},
            {"type": "free_point", "id": "A", "x": 180, "y": 300},
            {"type": "free_point", "id": "B", "x": 300, "y": 480},
            {"type": "free_point", "id": "C", "x": 270, "y": 300},
            {"type": "free_point", "id": "D", "x": 420, "y": 480},
            {"type": "segment", "id": "chord1", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "chord2", "p1": "C", "p2": "D"},
            {"type": "foot_perpendicular", "id": "R1", "p1": "O", "line1": "chord1"},
            {"type": "foot_perpendicular", "id": "R2", "p1": "O", "line1": "chord2"},
            {"type": "segment", "id": "d1", "p1": "O", "p2": "R1", "dashed": True},
            {"type": "segment", "id": "d2", "p1": "O", "p2": "R2", "dashed": True},
            {"type": "right_angle_mark", "id": "ra1", "p1": "A", "p2": "R1", "p3": "O"},
            {"type": "right_angle_mark", "id": "ra2", "p1": "C", "p2": "R2", "p3": "O"}
        ]
    },

    "A_G11_GEO": {
        "canvas": {"width": 800, "height": 550, "margin": 40},
        "constructions": [
            {"type": "free_point", "id": "A", "x": 180, "y": 400},
            {"type": "free_point", "id": "B", "x": 480, "y": 400},
            {"type": "free_point", "id": "D", "x": 280, "y": 130},
            {"type": "free_point", "id": "C", "x": 580, "y": 130},
            {"type": "quadrilateral_parallelogram", "id": "para", "p1": "A", "p2": "B", "p3": "C", "p4": "D"},
            {"type": "segment", "id": "s1", "p1": "A", "p2": "B"},
            {"type": "segment", "id": "s2", "p1": "B", "p2": "C"},
            {"type": "segment", "id": "s3", "p1": "C", "p2": "D"},
            {"type": "segment", "id": "s4", "p1": "D", "p2": "A"},
            {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
            {"type": "segment", "id": "BD", "p1": "B", "p2": "D"},
            {"type": "length_label", "id": "lbl_AB", "p1": "A", "p2": "B", "label": "9"},
            {"type": "length_label", "id": "lbl_AD", "p1": "A", "p2": "D", "label": "7"},
            {"type": "length_label", "id": "lbl_AC", "p1": "A", "p2": "C", "label": "8"},
            {"type": "length_label", "id": "lbl_BD", "p1": "B", "p2": "D", "label": "?"}
        ]
    }
}


def run_all():
    engine = GeometricEngine()
    base_dir = Path("static/figures/anchors")
    base_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "total_geometric": 0,
        "first_try_success": 0,
        "retried": 0,
        "retry_counts": [],
        "failed": 0,
        "failure_reasons": [],
        "files_created": [],
    }

    for uid, desc in sorted(ANCHOR_DESCRIPTIONS.items()):
        sys.stdout.write(f"\n--- {uid} ---\n")
        sys.stdout.flush()
        stats["total_geometric"] += 1

        svg, ctx, attempts, violations = engine.build_with_retry(desc, seed=42)

        if violations:
            stats["failed"] += 1
            reasons = '; '.join(v[:80] if len(v) > 80 else v for v in violations[:3])
            stats["failure_reasons"].append(f"{uid}: {reasons}")
            sys.stdout.write(f"  FAILED after {attempts} attempts\n")
            for v in violations[:3]:
                sys.stdout.write(f"    {v[:120]}\n")
        elif attempts == 1:
            stats["first_try_success"] += 1
            sys.stdout.write(f"  OK (first try)\n")
        else:
            stats["retried"] += 1
            stats["retry_counts"].append(attempts)
            sys.stdout.write(f"  OK after {attempts} retries\n")

        if svg:
            fname = base_dir / f"{uid}.svg"
            fname.write_text(svg, encoding="utf-8")
            size = len(svg)
            stats["files_created"].append({"uid": uid, "path": str(fname), "size_bytes": size})
            sys.stdout.write(f"  Saved: {fname} ({size} bytes)\n")

        sys.stdout.flush()

    print("\n" + "=" * 60)
    print("STATISTICS")
    print("=" * 60)
    print(f"Geometric anchors:                {stats['total_geometric']}")
    print(f"First try success:                {stats['first_try_success']}")
    print(f"Required retries:                 {stats['retried']}")
    if stats['retry_counts']:
        print(f"  Retry counts:                   {stats['retry_counts']}")
    print(f"Failures:                         {stats['failed']}")
    if stats['failure_reasons']:
        print(f"  Reasons:")
        for r in stats['failure_reasons']:
            print(f"    {r[:200]}")

    print(f"\nFiles created:")
    for f in stats["files_created"]:
        print(f"  {f['uid']}.svg  -  {f['size_bytes']} bytes")

    return stats


if __name__ == "__main__":
    run_all()
