#!/usr/bin/env python3
"""Code-first regeneration runner for FORMYLA course diagrams.

Workflow per manifest entry:

    1. Render: call the named generator from scripts.diagram_specs with given
       params -> matplotlib Figure.
    2. Save the figure to a temp file with consistent DPI/bbox.
    3. QA: scripts.diagram_qa.qa_check(temp).
    4. If QA fails, retry with relaxed params (larger figsize, more pad)
       up to MAX_RETRIES times.
    5. On accept: move temp -> target path (after backing up original to
       .bak.png unless it already exists or --no-backup is set).
    6. On reject: leave the original untouched and report.

Manifest schema (JSON):

    [
        {
            "id": "method_F1_triangles_circumcircle",
            "target": "static/images/methods/F1_circumcircle.png",
            "mode": "code",
            "generator": "triangle_with_circumcircle",
            "params": {"a": [0,0], "b": [4,0], "c": [1.4,3.0]}
        },
        {
            "id": "fu_2018_g5_fig1_replacement",
            "target": "static/images/problems/fu_2018_g5_fig1.png",
            "mode": "code",
            "generator": "isoceles_triangle",
            "params": {"base": 4.0, "height": 3.0}
        }
    ]

The mode "llm" is reserved for future LLM-driven regeneration via
services/drawing_service.py; the runner will skip these entries when no
OPENROUTER_API_KEY is present in env, and record them under
"needs_manual_or_api" in the report.

Usage:
    python3 scripts/regen_diagrams.py --manifest scripts/diagram_manifest.json --apply
    python3 scripts/regen_diagrams.py --manifest scripts/diagram_manifest.json --dry-run

Report: scripts/_regen_report.json and scripts/_regen_report.md
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.diagram_qa import QAResult, qa_check  # noqa: E402
from scripts.diagram_specs import get_generator  # noqa: E402

MAX_RETRIES = 3


def render_to_bytes(name: str, params: Dict[str, Any], pad: float) -> bytes:
    gen = get_generator(name)
    fig = gen(params)
    # ensure consistent margin across retries
    for ax in fig.get_axes():
        ax.margins(pad)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.20 + pad * 0.4,
                facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def attempt_render(entry: Dict[str, Any]) -> Tuple[bytes | None, QAResult, List[Dict[str, Any]]]:
    """Render with progressive padding/figure-size retries; return (bytes, last_qa, attempts)."""
    attempts: List[Dict[str, Any]] = []
    pads = [0.18, 0.28, 0.40]
    last_qa = None
    for i, pad in enumerate(pads):
        try:
            data = render_to_bytes(entry["generator"], entry.get("params", {}), pad)
        except Exception as e:
            attempts.append({"i": i, "pad": pad, "ok": False, "error": str(e),
                             "tb": traceback.format_exc()[-2000:]})
            last_qa = QAResult(path="<memory>", ok=False, issues=[f"render_error: {e}"])
            continue
        tmp = Path(f"/tmp/regen_attempt_{os.getpid()}_{i}.png")
        tmp.write_bytes(data)
        qr = qa_check(tmp)
        attempts.append({"i": i, "pad": pad, "ok": qr.ok, "issues": qr.issues, "size": qr.size})
        last_qa = qr
        if qr.ok:
            tmp.unlink(missing_ok=True)
            return data, qr, attempts
        tmp.unlink(missing_ok=True)
    return None, last_qa, attempts


def run(manifest_path: Path, apply: bool, backup: bool, root: Path) -> Dict[str, Any]:
    has_key = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_KEY"))
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = {
        "manifest": str(manifest_path),
        "total": len(entries),
        "accepted": [],
        "rejected": [],
        "needs_manual_or_api": [],
        "errors": [],
        "ts": int(time.time()),
        "apply": apply,
    }
    for entry in entries:
        eid = entry.get("id") or entry.get("target") or "<unknown>"
        target_rel = entry.get("target")
        if not target_rel:
            report["errors"].append({"id": eid, "error": "missing 'target'"})
            continue
        target = root / target_rel if not Path(target_rel).is_absolute() else Path(target_rel)
        mode = entry.get("mode", "code")
        if mode == "llm" and not has_key:
            report["needs_manual_or_api"].append({"id": eid, "target": str(target)})
            continue
        if mode == "keep":
            continue
        if mode != "code":
            report["errors"].append({"id": eid, "error": f"unsupported mode {mode!r}"})
            continue

        try:
            data, qr, attempts = attempt_render(entry)
        except Exception as e:
            report["errors"].append({"id": eid, "error": str(e), "tb": traceback.format_exc()[-2000:]})
            continue
        if data is None:
            report["rejected"].append({"id": eid, "target": str(target),
                                       "issues": qr.issues if qr else [],
                                       "attempts": attempts})
            continue
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and backup:
                bak = target.with_suffix(".bak.png")
                if not bak.exists():
                    shutil.copy2(target, bak)
            target.write_bytes(data)
        report["accepted"].append({"id": eid, "target": str(target), "size": qr.size, "attempts": attempts})
    return report


def write_md(report: Dict[str, Any], out_md: Path) -> None:
    lines = []
    lines.append("# FORMYLA diagram regeneration report\n")
    lines.append(f"Manifest: `{report['manifest']}`  ")
    lines.append(f"apply={report['apply']}  ")
    lines.append(f"Total entries: **{report['total']}**\n")
    lines.append("## Counts\n")
    lines.append(f"- Accepted: **{len(report['accepted'])}**")
    lines.append(f"- Rejected after retries: **{len(report['rejected'])}**")
    lines.append(f"- Needs manual / API (LLM mode, no key): **{len(report['needs_manual_or_api'])}**")
    lines.append(f"- Errors: **{len(report['errors'])}**\n")
    if report["accepted"]:
        lines.append("## Accepted\n")
        for it in report["accepted"][:200]:
            lines.append(f"- `{it['target']}` size={it['size']} attempts={len(it['attempts'])}")
        if len(report["accepted"]) > 200:
            lines.append(f"- … and {len(report['accepted']) - 200} more")
        lines.append("")
    if report["rejected"]:
        lines.append("## Rejected\n")
        for it in report["rejected"]:
            lines.append(f"- `{it['target']}` issues={it['issues']}")
        lines.append("")
    if report["needs_manual_or_api"]:
        lines.append("## Needs API access (LLM mode, no OPENROUTER_API_KEY)\n")
        for it in report["needs_manual_or_api"]:
            lines.append(f"- `{it['target']}`")
        lines.append("")
    if report["errors"]:
        lines.append("## Errors\n")
        for it in report["errors"]:
            lines.append(f"- {it.get('id')}: `{it.get('error')}`")
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="scripts/diagram_manifest.json")
    ap.add_argument("--root", default=".", help="repo root; targets resolved relative to it")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--out-json", default="scripts/_regen_report.json")
    ap.add_argument("--out-md", default="scripts/_regen_report.md")
    args = ap.parse_args()

    if args.dry_run and args.apply:
        print("--dry-run and --apply are mutually exclusive", file=sys.stderr)
        return 2
    apply = bool(args.apply) and not args.dry_run

    manifest = Path(args.manifest)
    if not manifest.exists():
        print(f"manifest not found: {manifest}", file=sys.stderr)
        return 2

    report = run(manifest, apply=apply, backup=not args.no_backup, root=Path(args.root).resolve())
    Path(args.out_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(report, Path(args.out_md))
    print(f"manifest={manifest}  apply={apply}  "
          f"accepted={len(report['accepted'])}  rejected={len(report['rejected'])}  "
          f"needs_api={len(report['needs_manual_or_api'])}  errors={len(report['errors'])}")
    print(f"report: {args.out_md}")
    return 0 if not report["errors"] and not report["rejected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
