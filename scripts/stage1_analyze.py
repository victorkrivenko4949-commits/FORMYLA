# -*- coding: utf-8 -*-
"""CH30 ЭТАП 1: анализ SVG — какие рендер-фичи реально сработали."""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SVG_DIR = os.path.join(_ROOT, "output", "final_rehearsal", "svg")


def main():
    files = sorted(f for f in os.listdir(_SVG_DIR) if f.endswith(".svg"))
    stats = Counter()
    per_file = []

    for f in files:
        s = open(os.path.join(_SVG_DIR, f), encoding="utf-8").read()
        feats = {
            "right_angle_mark": "FFD166" in s,
            "key_point_orange": "F6B44C" in s,
            "aux_blue": "73B6E6" in s,
            "reference_purple": "B7A2E8" in s,
            "target_green": "55D6BE" in s,
        }
        for k, v in feats.items():
            if v:
                stats[k] += 1
        per_file.append((f, feats))

    print(f"Всего SVG: {len(files)}")
    print()
    print("Рендер-фичи (сколько файлов содержат):")
    for k, v in stats.most_common():
        print(f"  {k}: {v}")

    # Детали по aux-файлам (где должны быть высоты/окружности).
    print()
    print("Детали по файлам:")
    for f, feats in per_file:
        if any(feats.values()):
            marks = [k for k, v in feats.items() if v]
            print(f"  {f[:50]}: {', '.join(marks)}")


if __name__ == "__main__":
    main()
