"""Keep drawings in the 102-method atlas only for the geometry section.

The HTML files are self-contained: both the public index and the older direct
atlas URL carry their own JSON. Run this script after regenerating the atlas.
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from atlas_geometry_fixes import FIXES


ROOT = Path(__file__).resolve().parents[1]
FILES = (ROOT / "static/methods/index.html", ROOT / "static/methods/atlas.html")
STAGES = ("condition", "construction", "result")


def embedded(html, name):
    pattern = rf'(<script type="application/json" id="{name}">)(.*?)(</script>)'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        raise ValueError(f"Missing {name}")
    return match, json.loads(match.group(2))


def clean(path, check=False):
    original = path.read_text(encoding="utf-8")
    html = original
    methods_match, methods = embedded(html, "methods-data")
    visuals_match, visuals = embedded(html, "visuals-data")
    stats_match, stats = embedded(html, "build-stats")
    if len(methods) != 102:
        raise ValueError(f"{path}: expected 102 methods, found {len(methods)}")

    keep = set()
    example_count = 0
    for method in methods:
        for example in method.get("examples", []):
            example_count += 1
            if method["section"] == "F" and example.get("visual_id"):
                keep.add(example["visual_id"])
            else:
                for field in ("visual_id", "visual_type", "visual_spec", "visual_need", "stage_notes"):
                    example.pop(field, None)

    kept_visuals = {}
    for visual_id in sorted(keep):
        for stage in STAGES:
            key = f"{visual_id}:{stage}"
            svg = visuals.get(key)
            if not svg:
                raise ValueError(f"{path}: missing geometry drawing {key}")
            if visual_id in FIXES:
                svg = FIXES[visual_id](stage)
            ET.fromstring(svg)
            kept_visuals[key] = svg
    if example_count != 306 or len(keep) != 63:
        raise ValueError(f"{path}: unexpected examples ({example_count}) or geometry drawings ({len(keep)})")

    stats.update(methods=len(methods), examples=example_count,
                 rendered=len(keep), stages=len(kept_visuals))
    replacements = {
        "methods-data": json.dumps(methods, ensure_ascii=False, separators=(",", ":")),
        "visuals-data": json.dumps(kept_visuals, ensure_ascii=False),
        "build-stats": json.dumps(stats, ensure_ascii=False),
    }
    # Work backwards so each JSON payload is replaced at its original offset.
    for match, name in sorted(
        ((methods_match, "methods-data"), (visuals_match, "visuals-data"), (stats_match, "build-stats")),
        key=lambda item: item[0].start(), reverse=True,
    ):
        html = html[:match.start(2)] + replacements[name] + html[match.end(2):]
    html = re.sub(
        r'102 метода, 306 разобранных задач и 828 встроенных SVG-стадий: условие → построение → результат\.',
        "102 метода, 306 разобранных задач и геометрические чертежи.",
        html,
        count=1,
    )
    if check:
        if html != original:
            raise ValueError(f"{path}: run tools/clean_methods_atlas.py")
    elif html != original:
        path.write_text(html, encoding="utf-8")
    return len(visuals), len(kept_visuals)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if either file needs cleaning")
    args = parser.parse_args()
    try:
        for file in FILES:
            before, after = clean(file, check=args.check)
            print(f"{file.name}: {before} -> {after} SVG stages; 63 geometry examples kept")
    except ValueError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
