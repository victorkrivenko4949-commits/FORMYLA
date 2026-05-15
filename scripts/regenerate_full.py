#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Батчевая регенерация всей матрицы Адаптивного теста.

Матрица:
    6 предметов × 7 классов (7-13) × 7 уровней (1-7) × 25 задач = 7350 задач

Особенности:
    - Чекпоинты в logs/regen_progress.json — при перезапуске продолжает с места
    - Логи в logs/full_regen_<timestamp>.log
    - Старые задачи ячейки → is_flagged='deprecated_by_pipeline' (перед генерацией)
    - Если в ячейке >40% review → помечается problematic_cell, прогон продолжается
    - 3 problematic_cell подряд → STOP с подробным логом
    - Между ячейками пауза 3с
    - Никаких глобальных бюджетных лимитов (отключены по запросу)

Запуск:
    python scripts/regenerate_full.py
    python scripts/regenerate_full.py --resume          # явно продолжить с checkpoint
    python scripts/regenerate_full.py --only-subject geometry
    python scripts/regenerate_full.py --count-per-cell 25 --max-cost-per-cell 4.0
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Windows: UTF-8 для консоли
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Параметры матрицы ────────────────────────────────────────────────────────
SUBJECTS_FULL = ["algebra", "geometry", "number_theory",
                 "combinatorics", "logic", "set_theory"]
GRADES = [7, 8, 9, 10, 11, 12, 13]
LEVELS = [1, 2, 3, 4, 5, 6, 7]

# Skip-list: helper, который учитывает и generic-комбинации, и subject-specific.
from pipeline.config import is_skipped_cell, SKIP_CELLS  # SKIP_CELLS оставляем для backward-compat

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = LOGS_DIR / "regen_progress.json"
LOG_FILE = LOGS_DIR / f"full_regen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


# ─── Логирование ──────────────────────────────────────────────────────────────
def setup_logging() -> logging.Logger:
    """Логи параллельно в файл и в консоль."""
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Очищаем существующих handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    file_h = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_h.setFormatter(fmt)
    root.addHandler(file_h)

    cons_h = logging.StreamHandler(sys.stdout)
    cons_h.setFormatter(fmt)
    root.addHandler(cons_h)

    # Убираем шум от httpx/httpcore
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    return logging.getLogger("regen_full")


# ─── Progress / checkpoint ────────────────────────────────────────────────────
def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"cells": {}, "started_at": None, "global_cost": 0.0}
    return {"cells": {}, "started_at": None, "global_cost": 0.0}


def save_progress(data: dict) -> None:
    PROGRESS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cell_key(subject: str, grade: int, level: int) -> str:
    return f"{subject}/g{grade}/l{level}"


# ─── Прогон одной ячейки ──────────────────────────────────────────────────────
async def run_cell(
    logger: logging.Logger,
    subject: str,
    grade: int,
    level: int,
    count: int,
    max_cost: float,
    deprecate_old: bool,
    db_lock: Optional[asyncio.Lock] = None,
) -> dict:
    """
    Прогон одной ячейки матрицы.

    Returns dict:
        {success, review, errors, cost, avg_iter, saved_ids, problematic, duplicates}
    """
    from pipeline.openrouter_client import OpenRouterClient, OpenRouterError
    from pipeline.runner import run_pipeline
    from pipeline.persistence import (
        save_task_to_adaptive,
        log_generation_attempt,
        push_to_manual_review,
        deprecate_old_tasks,
    )
    from pipeline.dedup import get_embedding, is_duplicate
    from pipeline.config import DEDUP_COSINE_THRESHOLD
    from models import db

    cell = cell_key(subject, grade, level)
    logger.info("═══ START CELL %s (count=%d, max_cost=$%.2f) ═══", cell, count, max_cost)

    # Helper: безопасный commit с локом (если несколько ячеек параллельно)
    async def safe_db(fn):
        if db_lock is None:
            return fn()
        async with db_lock:
            return fn()

    if deprecate_old:
        try:
            n = await safe_db(lambda: (
                deprecate_old_tasks(subject, grade, level),
                db.session.commit(),
            )[0])
            logger.info("[%s]  deprecated old tasks: %d", cell, n)
        except Exception as e:
            logger.exception("[%s]  deprecate_old_tasks failed: %s", cell, e)
            db.session.rollback()

    success = 0
    review = 0
    errors = 0
    duplicates = 0
    saved_ids: List[int] = []
    iter_history: List[int] = []
    total_cost = 0.0

    # Эмбеддинги уже сохранённых задач этой ячейки — для дедупа
    saved_embeddings: List[List[float]] = []

    async with OpenRouterClient() as client:
        for i in range(1, count + 1):
            if total_cost >= max_cost:
                logger.warning("  💰 cell budget $%.2f reached, stop at task %d/%d",
                               max_cost, i, count)
                break

            run_id = str(uuid.uuid4())
            logger.info("  [%2d/%d] run=%s", i, count, run_id[:8])

            try:
                result, iter_logs = await run_pipeline(
                    subject=subject, grade=grade, level=level,
                    client=client,
                )
            except OpenRouterError as e:
                logger.error("  OpenRouter error: %s", e)
                errors += 1
                continue
            except Exception as e:
                logger.exception("  Pipeline error: %s", e)
                errors += 1
                continue

            total_cost += result.total_cost_usd
            iter_history.append(result.iterations)

            saved_task_id: Optional[int] = None
            try:
                if result.success:
                    # ─── Дедуп по эмбеддингам перед save ──────────────────
                    try:
                        emb, emb_cost = await get_embedding(result.task.statement)
                        total_cost += emb_cost
                        is_dup, max_sim = is_duplicate(
                            emb, saved_embeddings, DEDUP_COSINE_THRESHOLD
                        )
                        if is_dup:
                            duplicates += 1
                            logger.info(
                                "    ⊘ DUPLICATE (cos=%.3f ≥ %.2f) — skipping",
                                max_sim, DEDUP_COSINE_THRESHOLD,
                            )
                            # пишем в log как fail-by-dedup, в БД не сохраняем
                            result.success = False
                            result.error = f"duplicate_of_cell_task (cos={max_sim:.3f})"
                            async def _save_dup():
                                log_generation_attempt(
                                    run_id, subject, grade, level, result, iter_logs, None,
                                )
                                db.session.commit()
                            if db_lock is None:
                                await _save_dup()
                            else:
                                async with db_lock:
                                    await _save_dup()
                            continue
                        saved_embeddings.append(emb)
                    except Exception as e:
                        # Если эмбеддинг не получился — пропускаем дедуп, сохраняем как есть
                        logger.warning("    dedup failed: %s — saving without dedup", e)

                    async def _save_success():
                        nonlocal saved_task_id
                        saved_task_id = save_task_to_adaptive(
                            result, subject, grade, level, run_id,
                        )
                        log_generation_attempt(
                            run_id, subject, grade, level, result, iter_logs, saved_task_id,
                        )
                        db.session.commit()
                    if db_lock is None:
                        await _save_success()
                    else:
                        async with db_lock:
                            await _save_success()
                    saved_ids.append(saved_task_id)
                    success += 1
                    logger.info("    ✓ saved id=%d  iters=%d  $%.4f  (cell $%.4f)",
                                saved_task_id, result.iterations,
                                result.total_cost_usd, total_cost)
                elif result.sent_to_review:
                    async def _save_review():
                        push_to_manual_review(run_id, subject, grade, level, result)
                        log_generation_attempt(
                            run_id, subject, grade, level, result, iter_logs, None,
                        )
                        db.session.commit()
                    if db_lock is None:
                        await _save_review()
                    else:
                        async with db_lock:
                            await _save_review()
                    review += 1
                    logger.info("    ⚠ REVIEW  iters=%d  $%.4f  (cell $%.4f)",
                                result.iterations, result.total_cost_usd, total_cost)
                else:
                    errors += 1
                    logger.warning("    ✗ FAIL %s", result.error)
            except Exception as e:
                db.session.rollback()
                logger.exception("    DB save failed: %s", e)
                errors += 1

    avg_iter = round(sum(iter_history) / len(iter_history), 2) if iter_history else 0.0
    review_pct = (review / count * 100) if count else 0.0
    problematic = review_pct > 40.0

    logger.info("═══ END CELL %s: success=%d review=%d dup=%d err=%d cost=$%.4f avg_iter=%.2f%s ═══",
                cell, success, review, duplicates, errors, total_cost, avg_iter,
                "  ⚠ PROBLEMATIC" if problematic else "")

    return {
        "success": success,
        "review": review,
        "duplicates": duplicates,
        "errors": errors,
        "cost": round(total_cost, 4),
        "avg_iter": avg_iter,
        "saved_ids": saved_ids,
        "problematic": problematic,
        "review_pct": round(review_pct, 1),
    }


# ─── Главный цикл ─────────────────────────────────────────────────────────────
async def main_async(args: argparse.Namespace) -> int:
    logger = setup_logging()

    # Flask app context (один на весь прогон)
    from app import app
    ctx = app.app_context()
    ctx.push()

    try:
        # Подбираем ячейки матрицы
        subjects = [args.only_subject] if args.only_subject else SUBJECTS_FULL
        progress = load_progress()
        if not progress.get("started_at"):
            progress["started_at"] = datetime.now().isoformat()
            progress["global_cost"] = 0.0
            progress["cells"] = progress.get("cells", {})
            save_progress(progress)

        # Формируем список ячеек
        if args.cells:
            # Явно заданные ячейки в формате subject/g7/l3,subject/g9/l5
            all_cells = []
            for spec in args.cells.split(","):
                spec = spec.strip()
                try:
                    s, g_part, l_part = spec.split("/")
                    g = int(g_part.lstrip("g"))
                    lvl = int(l_part.lstrip("l"))
                    all_cells.append((s, g, lvl))
                except Exception as e:
                    logger.error("Bad --cells spec '%s': %s", spec, e)
                    return 2
        else:
            all_cells = [
                (s, g, lvl)
                for s in subjects
                for g in GRADES
                for lvl in LEVELS
            ]

        total_cells = len(all_cells)
        logger.info("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
        logger.info("┃ FULL REGEN: %d ячеек × %d задач = %d задач               ┃",
                    total_cells, args.count_per_cell, total_cells * args.count_per_cell)
        logger.info("┃ Log: %s", LOG_FILE)
        logger.info("┃ Progress: %s", PROGRESS_FILE)
        logger.info("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")

        problematic_streak = 0
        processed_cells = 0
        skipped_cells = 0
        global_cost = float(progress.get("global_cost", 0.0))
        start_time = time.time()

        # ─── Фаза 1: классификация ячеек ──────────────────────────────────
        # Если ячейки явно заданы через --cells, skip-list НЕ применяется
        # (пользователь явно хочет именно их — например для тестового прогона).
        skip_enabled = not bool(args.cells)
        to_run: List[tuple] = []
        for idx, (subject, grade, level) in enumerate(all_cells, start=1):
            key = cell_key(subject, grade, level)
            if skip_enabled and is_skipped_cell(subject, grade, level):
                logger.info("[%d/%d] SKIP_UNREALISTIC_COMBO %s", idx, total_cells, key)
                progress["cells"][key] = {
                    "subject": subject, "grade": grade, "level": level,
                    "success": 0, "review": 0, "duplicates": 0, "errors": 0,
                    "cost": 0.0, "avg_iter": 0.0, "saved_ids": [],
                    "problematic": False, "review_pct": 0.0,
                    "skipped_reason": "skipped_unrealistic_combo",
                    "finished_at": datetime.now().isoformat(),
                }
                save_progress(progress)
                skipped_cells += 1
                continue
            if key in progress["cells"] and not args.force:
                cached = progress["cells"][key]
                logger.info("[%d/%d] SKIP %s (cached: success=%d, review=%d, $%.4f)",
                            idx, total_cells, key,
                            cached.get("success", 0), cached.get("review", 0),
                            cached.get("cost", 0.0))
                skipped_cells += 1
                continue
            to_run.append((idx, subject, grade, level))

        batch_size = max(1, int(args.batch_size))
        logger.info("\n→ Cells to run: %d (skipped %d)", len(to_run), skipped_cells)
        logger.info("→ Parallelism: %d cells per batch, %.1fs pause between batches",
                    batch_size, args.batch_pause)

        # ─── Lock для безопасного доступа к Flask-SQLAlchemy session ───────
        db_lock = asyncio.Lock()

        # ─── Фаза 2: параллельная обработка батчами ────────────────────────
        async def _run_one_cell(idx: int, subject: str, grade: int, level: int):
            key = cell_key(subject, grade, level)
            try:
                stats = await run_cell(
                    logger=logger,
                    subject=subject, grade=grade, level=level,
                    count=args.count_per_cell,
                    max_cost=args.max_cost_per_cell,
                    deprecate_old=not args.no_deprecate,
                    db_lock=db_lock,
                )
            except Exception as e:
                logger.exception("UNEXPECTED CELL ERROR for %s: %s", key, e)
                stats = {
                    "success": 0, "review": 0, "duplicates": 0,
                    "errors": args.count_per_cell,
                    "cost": 0.0, "avg_iter": 0.0, "saved_ids": [],
                    "problematic": True, "review_pct": 0.0,
                    "fatal_error": str(e),
                }
            return idx, subject, grade, level, stats

        for batch_start in range(0, len(to_run), batch_size):
            batch = to_run[batch_start:batch_start + batch_size]
            batch_keys = ", ".join(cell_key(s, g, l) for _, s, g, l in batch)
            logger.info(
                "\n━━━ BATCH %d-%d / %d ━━━ %s",
                batch_start + 1, batch_start + len(batch), len(to_run), batch_keys,
            )
            try:
                results = await asyncio.gather(
                    *[_run_one_cell(idx, s, g, lvl) for idx, s, g, lvl in batch],
                    return_exceptions=False,
                )
            except KeyboardInterrupt:
                logger.warning("⏹ Interrupted")
                save_progress(progress)
                return 130

            # Сохранение прогресса и проверка problematic_streak
            for idx, subject, grade, level, stats in results:
                key = cell_key(subject, grade, level)
                progress["cells"][key] = {
                    "subject": subject, "grade": grade, "level": level,
                    **stats,
                    "finished_at": datetime.now().isoformat(),
                }
                global_cost += stats["cost"]
                processed_cells += 1

                if stats["problematic"]:
                    problematic_streak += 1
                    logger.warning(
                        "  ⚠ problematic_cell (%d in a row): %s — %.0f%% review",
                        problematic_streak, key, stats["review_pct"],
                    )
                else:
                    problematic_streak = 0

            progress["global_cost"] = round(global_cost, 4)
            save_progress(progress)

            elapsed = time.time() - start_time
            eta_per_cell = elapsed / max(processed_cells, 1)
            eta_remaining = eta_per_cell * (len(to_run) - processed_cells)
            logger.info(
                "  PROGRESS: %d/%d processed, $%.4f spent, ETA ~%.1fh",
                processed_cells, len(to_run), global_cost, eta_remaining / 3600,
            )

            if problematic_streak >= 3:
                logger.error("\n🛑 STOP: 3 problematic cells in a row")
                return 1

            # Пауза между батчами
            if batch_start + batch_size < len(to_run):
                await asyncio.sleep(args.batch_pause)

        # ─── ИТОГ ───────────────────────────────────────────────────────────
        logger.info("\n" + "═" * 70)
        logger.info("DONE")
        logger.info("  processed cells:  %d", processed_cells)
        logger.info("  skipped (cached): %d", skipped_cells)
        logger.info("  total cost:       $%.4f", global_cost)
        logger.info("  elapsed:          %.1f hours", (time.time() - start_time) / 3600)
        logger.info("═" * 70)

        return 0

    finally:
        ctx.pop()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Полная регенерация матрицы Адаптивного теста"
    )
    p.add_argument("--count-per-cell", type=int, default=25)
    p.add_argument("--max-cost-per-cell", type=float, default=4.0)
    p.add_argument("--batch-size", type=int, default=3,
                   help="Сколько ячеек параллельно (asyncio.gather)")
    p.add_argument("--batch-pause", type=float, default=2.0,
                   help="Пауза в секундах между батчами (F-6: 1.0 -> 2.0 для смягчения 429)")
    p.add_argument("--only-subject", type=str, default=None,
                   help="Прогнать только один предмет")
    p.add_argument("--cells", type=str, default=None,
                   help="Явный список ячеек через запятую, например "
                        "'algebra/g7/l1,algebra/g7/l3,algebra/g9/l5'")
    p.add_argument("--no-deprecate", action="store_true",
                   help="НЕ помечать старые задачи как deprecated")
    p.add_argument("--force", action="store_true",
                   help="Игнорировать checkpoint, прогонять заново")
    p.add_argument("--resume", action="store_true",
                   help="(noop, чекпоинт читается всегда)")
    args = p.parse_args()

    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n⏹ Interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
