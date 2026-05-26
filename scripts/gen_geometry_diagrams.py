#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Шаг 2 пайплайна: генерируем ВСЕ чертежи из плана через FORMYLA drawing pipeline
(Brief Expander → Architect → Claude Opus 4.7 → Sandbox → Critic + Cosmetic Critic).

Вход:   scripts/_geometry_diagrams_plan.json     (создаётся scripts/gen_geometry_diagrams_plan.py)
Выход:  static/generated/secrets/<diagram_id>.png   — сам PNG
        scripts/_geometry_diagrams_done.json         — журнал результатов

Запуск:
    python scripts/gen_geometry_diagrams.py
    python scripts/gen_geometry_diagrams.py --workers 30
    python scripts/gen_geometry_diagrams.py --limit 5            # тест на 5 штук
    python scripts/gen_geometry_diagrams.py --resume             # пропускать уже готовые
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Гарантируем все стадии pipeline-а ВКЛЮЧЁНЫМИ (максимум качества)
os.environ.setdefault("DRAWING_CRITIC_ENABLED", "1")
os.environ.setdefault("DRAWING_ARCHITECT", "1")
os.environ.setdefault("DRAWING_BRIEF_EXPANDER", "1")
os.environ.setdefault("DRAWING_COSMETIC_CRITIC", "1")

from services.drawing_service import generate_drawing  # noqa: E402

PLAN_FILE = REPO_ROOT / "scripts" / "_geometry_diagrams_plan.json"
DONE_FILE = REPO_ROOT / "scripts" / "_geometry_diagrams_done.json"
OUT_DIR = REPO_ROOT / "static" / "generated" / "secrets"


# ─────────────────────────────────────────────────────────────────────
def build_problem_text(item: dict) -> str:
    """Собираем итоговый промт для drawing pipeline.

    Pipeline уже сам пропустит текст через Brief Expander → Architect.
    Поэтому даём максимально насыщенный, но «человеческий» текст.
    """
    title = (item.get("title") or "").strip()
    brief = (item.get("brief") or "").strip()
    secret_title = (item.get("secret_title") or "").strip()
    parts = []
    parts.append(f"Тема секрета: {secret_title}")
    parts.append(f"Заголовок чертежа: {title}")
    parts.append("")
    parts.append("Задание для построения чертежа:")
    parts.append(brief)
    parts.append("")
    parts.append(
        "Чертёж должен быть аккуратным: подписи точек заглавными латинскими буквами, "
        "ничего не должно пересекаться, все важные объекты подписаны, без лишних осей и сеток."
    )
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────
class State:
    """Потокобезопасный реестр результатов с инкрементальным сохранением."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.done: dict[str, dict] = {}
        if DONE_FILE.exists():
            try:
                data = json.loads(DONE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for r in data:
                        if r.get("diagram_id"):
                            self.done[r["diagram_id"]] = r
                elif isinstance(data, dict):
                    self.done = data
            except Exception:
                self.done = {}

    def is_done_ok(self, diagram_id: str) -> bool:
        rec = self.done.get(diagram_id)
        if not rec:
            return False
        if not rec.get("ok"):
            return False
        # PNG обязан физически существовать
        png = OUT_DIR / f"{diagram_id}.png"
        return png.exists()

    def record(self, diagram_id: str, payload: dict) -> None:
        with self._lock:
            self.done[diagram_id] = payload
            # инкрементальное сохранение
            arr = list(self.done.values())
            DONE_FILE.write_text(
                json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8"
            )


# ─────────────────────────────────────────────────────────────────────
def process_one(item: dict, state: State) -> dict:
    diagram_id = item["diagram_id"]
    png_path = OUT_DIR / f"{diagram_id}.png"

    problem = build_problem_text(item)
    started = time.time()
    try:
        result = generate_drawing(
            problem, app_root=str(REPO_ROOT), use_cache=True
        )
        png_path.parent.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(result.image_bytes)
        rec = {
            "diagram_id": diagram_id,
            "ok": True,
            "secret_index": item.get("secret_index"),
            "secret_title": item.get("secret_title"),
            "title": item.get("title"),
            "png": str(png_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "cache_hit": bool(result.cache_hit),
            "model": result.model,
            "cost_usd": round(result.cost_usd or 0.0, 4),
            "render_ms": result.render_ms,
            "wall_s": round(time.time() - started, 2),
        }
        state.record(diagram_id, rec)
        print(
            f"[OK ] {diagram_id}  "
            f"({rec['wall_s']:>6.1f}s  ${rec['cost_usd']:.3f}  "
            f"{'cache' if rec['cache_hit'] else 'gen'})  "
            f"{item.get('title', '')[:55]}"
        )
        return rec
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        rec = {
            "diagram_id": diagram_id,
            "ok": False,
            "secret_index": item.get("secret_index"),
            "secret_title": item.get("secret_title"),
            "title": item.get("title"),
            "error": err[:500],
            "wall_s": round(time.time() - started, 2),
        }
        state.record(diagram_id, rec)
        # Полный traceback в stderr
        traceback.print_exc()
        print(
            f"[ERR] {diagram_id}  ({rec['wall_s']:>6.1f}s)  "
            f"{item.get('title', '')[:55]}  →  {err[:120]}"
        )
        return rec


# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0,
                    help="0 = все; иначе обработать первые N штук")
    ap.add_argument("--resume", action="store_true",
                    help="Пропускать уже успешно сгенерированные (по умолчанию).")
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.set_defaults(resume=True)
    args = ap.parse_args()

    if not PLAN_FILE.exists():
        print(f"[err] plan-файл не найден: {PLAN_FILE}")
        print("[err] сначала запустите scripts/gen_geometry_diagrams_plan.py")
        return 1

    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    print(f"[gen] план: {len(plan)} чертежей")

    state = State()
    todo: list[dict] = []
    skipped = 0
    for item in plan:
        if not isinstance(item, dict) or not item.get("diagram_id"):
            continue
        if args.resume and state.is_done_ok(item["diagram_id"]):
            skipped += 1
            continue
        todo.append(item)

    if args.limit and args.limit > 0:
        todo = todo[: args.limit]

    print(f"[gen] пропущено уже готовых: {skipped}")
    print(f"[gen] в работу: {len(todo)}")
    print(f"[gen] параллелизм: {args.workers} потоков")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    started = time.time()
    ok_n = 0
    err_n = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_one, it, state): it for it in todo}
        for fut in as_completed(futures):
            try:
                rec = fut.result()
            except Exception as exc:  # noqa: BLE001
                err_n += 1
                print(f"[!!!] worker crash: {exc!r}")
                continue
            if rec.get("ok"):
                ok_n += 1
            else:
                err_n += 1

    total = ok_n + err_n
    elapsed = time.time() - started
    print()
    print("─" * 60)
    print(f"[gen] готово за {elapsed:.1f}s")
    print(f"[gen] успех: {ok_n}/{total}    ошибок: {err_n}")
    print(f"[gen] PNG-файлы: {OUT_DIR}")
    print(f"[gen] журнал:    {DONE_FILE}")
    # суммарный $
    total_cost = 0.0
    for rec in state.done.values():
        if rec.get("ok"):
            total_cost += float(rec.get("cost_usd") or 0.0)
    print(f"[gen] суммарная стоимость (только успешные): ${total_cost:.2f}")
    return 0 if err_n == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
