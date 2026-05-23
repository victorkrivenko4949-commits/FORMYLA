#!/usr/bin/env python3
"""Safe bulk image repair for diagram assets.

Two operations:

  --remove-kopiya
      Delete files matching " — копия*.png" that are byte-identical to their
      base file. The base file is kept. Files without a base or with diverged
      contents are NOT touched.

  --pad
      For PNGs flagged by image_qa.py as 'boundary_touch', add a small white
      padding ring (default 24px) so labels at the edge stop being clipped.
      Backup of the original is saved next to it as `<name>.bak.png`.

Run with --dry-run first to see what would change. Use --apply to write.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageOps

KOPIYA_RE = re.compile(r" — копия( \(\d+\))?\.png$")


def remove_kopiya(root: Path, apply: bool) -> dict:
    files = sorted(root.glob("*.png"))
    by_name = {f.name: f for f in files}
    removed, skipped = [], []
    for f in files:
        if not KOPIYA_RE.search(f.name):
            continue
        base_name = KOPIYA_RE.sub(".png", f.name)
        base = by_name.get(base_name)
        if base is None:
            skipped.append({"file": f.name, "reason": "no base"})
            continue
        if f.read_bytes() != base.read_bytes():
            skipped.append({"file": f.name, "reason": "diverged from base"})
            continue
        removed.append(f.name)
        if apply:
            f.unlink()
    return {"removed": removed, "skipped": skipped}


def pad_image(path: Path, pad: int, apply: bool, backup: bool) -> bool:
    with Image.open(path) as img:
        img = img.convert("RGB")
        padded = ImageOps.expand(img, border=pad, fill="white")
    if not apply:
        return True
    if backup:
        bak = path.with_suffix(".bak.png")
        if not bak.exists():
            shutil.copy2(path, bak)
    padded.save(path, format="PNG")
    return True


def pad_from_report(report_path: Path, root: Path, pad: int, apply: bool, backup: bool) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    targets = report.get("boundary_touch", [])
    padded, missing, errors = [], [], []
    for name in targets:
        p = root / name
        if not p.exists():
            missing.append(name)
            continue
        try:
            pad_image(p, pad, apply, backup)
            padded.append(name)
        except Exception as e:
            errors.append({"file": name, "error": str(e)})
    return {"padded": padded, "missing": missing, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="static/images/problems")
    ap.add_argument("--report", default="scripts/_image_qa_report.json")
    ap.add_argument("--remove-kopiya", action="store_true")
    ap.add_argument("--pad", action="store_true")
    ap.add_argument("--pad-px", type=int, default=24)
    ap.add_argument("--apply", action="store_true", help="actually write changes")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    summary = {}
    if args.remove_kopiya:
        summary["remove_kopiya"] = remove_kopiya(root, args.apply)
        print(f"remove_kopiya: would remove {len(summary['remove_kopiya']['removed'])}, "
              f"skipped {len(summary['remove_kopiya']['skipped'])}"
              f" (apply={args.apply})")
    if args.pad:
        rep = Path(args.report)
        if not rep.exists():
            print(f"report not found: {rep} — run scripts/image_qa.py first", file=sys.stderr)
            return 2
        summary["pad"] = pad_from_report(rep, root, args.pad_px, args.apply, not args.no_backup)
        print(f"pad: would pad {len(summary['pad']['padded'])}, "
              f"missing {len(summary['pad']['missing'])}, errors {len(summary['pad']['errors'])}"
              f" (apply={args.apply}, pad_px={args.pad_px})")
    if not (args.remove_kopiya or args.pad):
        ap.print_help()
        return 1

    out = Path("scripts/_image_repair_log.json")
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
