#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/batch_draw.py — Пакетный прогон построения чертежей.

Берёт задачи со статусом «описание есть» (figure_status='has_description'),
строит чертежи через GeometricEngine, обновляет статус, пишет журнал.

Аргументы:
    --limit N              максимум задач за прогон
    --class N              фильтр по классу (5-11)
    --section S            фильтр по разделу (subject: algebra, geometry, etc.)
    --resume               продолжить после остановки (пропускать уже figure_built)
    --retry-failures       повторный прогон только отказов (figure_status='engine_rejected')
    --dry-run              только показать что будет, не строить

Примеры:
    python scripts/batch_draw.py --limit 20 --class 7 --section geometry
    python scripts/batch_draw.py --retry-failures --limit 10
    python scripts/batch_draw.py --resume --limit 50
"""

import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Пакетный прогон построения чертежей")
    parser.add_argument("--limit", type=int, default=None, help="Максимум задач за прогон")
    parser.add_argument("--class", dest="class_level", type=int, default=None,
                        help="Фильтр по классу (5-11)")
    parser.add_argument("--section", type=str, default=None,
                        help="Фильтр по разделу (subject: algebra, geometry, etc.)")
    parser.add_argument("--resume", action="store_true",
                        help="Пропускать задачи со статусом figure_built")
    parser.add_argument("--retry-failures", action="store_true",
                        help="Только задачи со статусом engine_rejected")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только показать, не строить")
    args = parser.parse_args()

    # Импорт после разбора аргументов
    from app import app
    from models import db, AdaptiveTask
    from sqlalchemy import text

    log_lines = []
    t0_total = time.perf_counter()

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        log_lines.append(line)

    log("=" * 60)
    log("BATCH DRAW — пакетный прогон построения чертежей")
    log(f"  limit={args.limit}, class={args.class_level}, section={args.section}")
    log(f"  resume={args.resume}, retry_failures={args.retry_failures}, dry_run={args.dry_run}")
    log("=" * 60)

    with app.app_context():
        # Строим запрос
        q = db.session.query(AdaptiveTask)

        if args.retry_failures:
            q = q.filter(AdaptiveTask.figure_status == 'engine_rejected')
        elif args.resume:
            q = q.filter(
                AdaptiveTask.figure_status.in_(['has_description', 'engine_rejected'])
            )
        else:
            q = q.filter(AdaptiveTask.figure_status == 'has_description')

        if args.class_level:
            q = q.filter(AdaptiveTask.class_level == args.class_level)
        if args.section:
            q = q.filter(AdaptiveTask.subject == args.section)

        total_candidates = q.count()
        log(f"  Кандидатов всего: {total_candidates}")

        if args.limit:
            q = q.limit(args.limit)

        tasks = q.all()
        log(f"  Взято в прогон: {len(tasks)}")

        if not tasks:
            log("  Нет задач для обработки.")
            _write_log(log_lines)
            return

        from services.figure_cache import build_figure, figure_hash

        stats = {
            'total': len(tasks),
            'built': 0,
            'cached': 0,
            'rejected': 0,
            'error': 0,
        }

        for i, task in enumerate(tasks):
            t0 = time.perf_counter()
            try:
                figure_json = task.figure_json
                if not figure_json:
                    log(f"  [{i+1}/{len(tasks)}] task#{task.id}: нет figure_json — skip")
                    continue

                if args.dry_run:
                    log(f"  [{i+1}/{len(tasks)}] task#{task.id}: [DRY-RUN] would draw "
                        f"(class={task.class_level}, subject={task.subject})")
                    continue

                svg, h, elapsed, was_cached = build_figure(figure_json, task.id)

                task.figure_status = 'figure_built'
                db.session.commit()

                if was_cached:
                    stats['cached'] += 1
                    log(f"  [{i+1}/{len(tasks)}] task#{task.id}: CACHED "
                        f"(hash={h[:12]}…) in {elapsed*1000:.0f}ms")
                else:
                    stats['built'] += 1
                    log(f"  [{i+1}/{len(tasks)}] task#{task.id}: BUILT "
                        f"(hash={h[:12]}…, {len(svg)} bytes) in {elapsed:.1f}s")

            except ValueError as e:
                db.session.rollback()
                task.figure_status = 'engine_rejected'
                db.session.commit()
                stats['rejected'] += 1
                elapsed = time.perf_counter() - t0
                log(f"  [{i+1}/{len(tasks)}] task#{task.id}: REJECTED "
                    f"({e}) in {elapsed:.1f}s")

            except RuntimeError as e:
                db.session.rollback()
                task.figure_status = 'engine_rejected'
                db.session.commit()
                stats['rejected'] += 1
                elapsed = time.perf_counter() - t0
                log(f"  [{i+1}/{len(tasks)}] task#{task.id}: ENGINE REJECTED "
                    f"({e}) in {elapsed:.1f}s")

            except Exception as e:
                db.session.rollback()
                stats['error'] += 1
                elapsed = time.perf_counter() - t0
                log(f"  [{i+1}/{len(tasks)}] task#{task.id}: ERROR "
                    f"({type(e).__name__}: {e}) in {elapsed:.1f}s")

        # Итоговая таблица
        elapsed_total = time.perf_counter() - t0_total
        log("")
        log("─" * 60)
        log("ИТОГИ ПРОГОНА")
        log(f"  Всего задач:       {stats['total']}")
        log(f"  Построено:         {stats['built']}")
        log(f"  Из кеша:           {stats['cached']}")
        log(f"  Отказов движка:    {stats['rejected']}")
        log(f"  Ошибок:            {stats['error']}")
        log(f"  Общее время:       {elapsed_total:.1f}s")

        # Итоговая таблица по статусам в БД
        log("")
        log("─" * 60)
        log("РАСПРЕДЕЛЕНИЕ ПО СТАТУСАМ (вся БД)")
        rows = db.session.execute(text(
            "SELECT figure_status, COUNT(*) FROM adaptive_tasks "
            "WHERE figure_status IS NOT NULL "
            "GROUP BY figure_status ORDER BY COUNT(*) DESC"
        )).fetchall()
        for status, count in rows:
            log(f"  {status}: {count}")

        _write_log(log_lines)


def _write_log(log_lines):
    """Записать журнал в файл."""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f'batch_draw_{ts}.log')
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    print(f"\nЖурнал сохранён: {log_path}")


if __name__ == "__main__":
    main()
