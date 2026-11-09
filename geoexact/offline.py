# -*- coding: utf-8 -*-
"""Офлайн-вход в конвейер GeoExact: план пишет не роутер, а внешний «эксперт».

Детерминированная часть (валидация → решатель → гейты → отметки → aux → рендер)
остаётся настоящей; заменяются только вызовы LLM — ровно как в
test_aux_pipeline_final_view. Используется бенчмарком и пакетной генерацией
чертежей банка.

Спецификация (JSON):
    {"uid": "...", "problem": "текст условия",
     "plan": {...FigurePlan...},            # основной чертёж (режим A/B)
     "aux": {"idea": ..., "steps": [...], "aux_segments": [...], ...} | null,
     "expert_text": "словами: какие построения" (необязательно),
     "with_aux": true}

CLI:
    python -m geoexact.offline spec.json [-o out.svg] [--png out.png] [--json]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import threading

from .core import llm as L
from .core import pipeline
from .core.schema import FigurePlan, PlanError

_LOCK = threading.RLock()


def _formalize_from(plan_dict):
    def fake(*_a, **_k):
        d = json.loads(json.dumps(plan_dict))
        if isinstance(d, dict) and "error" in d:
            raise PlanError(str(d["error"]), d.get("notes", ""))
        L._declare_helper_points(d)
        plan = FigurePlan.from_dict(d)
        from .core.schema import validate_plan
        return plan, validate_plan(plan)
    return fake


@contextlib.contextmanager
def offline_llm(plan: dict, aux: dict | None = None, expert_text: str | None = None,
                cls: str = "M"):
    """Подменить LLM-вызовы заранее написанными ответами (потокобезопасно через lock)."""
    aux_data = dict(aux) if isinstance(aux, dict) else {"idea": "", "steps": []}
    said = expert_text or aux_data.get("idea") or ""
    if said:
        aux_data.setdefault("_expert_text", said)
    names = ("formalize", "classify", "expert_text", "aux_plan_from_text", "aux_plan",
             "aux_plan_repair")
    with _LOCK:
        saved = {n: getattr(L, n) for n in names}
        try:
            L.formalize = _formalize_from(plan)
            L.classify = lambda *a, **k: {"ok": True, "class": cls, "space": "plane"}
            L.expert_text = lambda *a, **k: said
            L.aux_plan_from_text = lambda *a, **k: dict(aux_data)
            L.aux_plan = lambda *a, **k: dict(aux_data)
            L.aux_plan_repair = lambda *a, **k: dict(aux_data)
            yield
        finally:
            for n, f in saved.items():
                setattr(L, n, f)


def run_spec(spec: dict, with_aux: bool | None = None):
    """Прогнать спецификацию через настоящий конвейер. Возвращает pipeline.Result."""
    wa = spec.get("with_aux", True) if with_aux is None else with_aux
    with offline_llm(spec["plan"], spec.get("aux"), spec.get("expert_text"),
                     spec.get("cls", "M")):
        return pipeline.generate(spec["problem"], with_aux=wa, use_cache=False)


def svg_to_png(svg: str, path: str, width: int = 900) -> str:
    import cairosvg
    # cairosvg читает font-size="68%" как долю от 100% вьюпорта: подставляем px
    svg = re.sub(r'font-size="(\d+(?:\.\d+)?)%"',
                 lambda m: f'font-size="{float(m.group(1)) * 0.15:.2f}px"', svg)
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=path, output_width=width)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec")
    ap.add_argument("-o", "--out")
    ap.add_argument("--png")
    ap.add_argument("--no-aux", action="store_true")
    ap.add_argument("--json", action="store_true", help="печатать отчёт bench.check")
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec, encoding="utf-8"))
    res = run_spec(spec, with_aux=False if a.no_aux else None)
    print(res.brief(), res.stage, res.reason, res.detail[:300])
    for w in res.warnings:
        print("  W:", w[:200])
    if res.svg and a.out:
        open(a.out, "w", encoding="utf-8").write(res.svg)
    if res.svg and a.png:
        svg_to_png(res.svg, a.png)
    if a.json:
        from .bench import check
        print(json.dumps(check(spec, res), ensure_ascii=False, indent=1))
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
