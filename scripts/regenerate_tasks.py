#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI для регенерации задач Адаптивного теста через 3-нейросетевой пайплайн.

Запуск:
    python scripts/regenerate_tasks.py \\
        --subject algebra --grade 9 --level 2 --count 10 \\
        --max-cost-usd 1.0

Опции:
    --subject       algebra | geometry | number_theory | combinatorics | logic | probability
    --grade         7..13
    --level         1..7
    --count         сколько задач сгенерировать
    --max-cost-usd  бюджет в долларах (остановка при превышении)
    --deprecate-old пометить старые задачи этой ячейки как deprecated
    --topic-hint    подсказка по теме (например "квадратичные уравнения")
    --dry-run       не писать в БД, только печатать результат
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from typing import Optional

# Windows: переключаем stdout/stderr на UTF-8 — иначе cp1251 крашится на emoji
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("regenerate_tasks")


async def main_async(args: argparse.Namespace) -> int:
    from pipeline.config import SUBJECTS
    from pipeline.openrouter_client import OpenRouterClient, OpenRouterError
    from pipeline.runner import run_pipeline
    from pipeline.persistence import (
        save_task_to_adaptive,
        log_generation_attempt,
        push_to_manual_review,
        deprecate_old_tasks,
    )

    # Валидация аргументов
    if args.subject not in SUBJECTS:
        logger.error("Неизвестный subject: %s. Доступно: %s", args.subject, SUBJECTS)
        return 2

    if not (1 <= args.level <= 7):
        logger.error("level должен быть 1..7")
        return 2

    if not (7 <= args.grade <= 13):
        logger.error("grade должен быть 7..13")
        return 2

    # Импорт Flask app для контекста БД (если не dry-run)
    app_ctx = None
    if not args.dry_run:
        try:
            from app import app
            app_ctx = app.app_context()
            app_ctx.push()
        except Exception as e:
            logger.error("Не удалось загрузить Flask app для БД: %s", e)
            logger.warning("Продолжаю в dry-run режиме")
            args.dry_run = True

    try:
        if not args.dry_run and args.deprecate_old:
            from models import db
            n = deprecate_old_tasks(args.subject, args.grade, args.level)
            db.session.commit()
            print(f"📦 Помечено как deprecated: {n} старых задач")

        # ─── Основной цикл генерации ────────────────────────────────────────
        print(f"\n{'='*70}")
        print(f"REGENERATE: subject={args.subject} grade={args.grade} level={args.level}")
        print(f"count={args.count}  max_cost=${args.max_cost_usd}")
        print(f"{'='*70}\n")

        total_cost = 0.0
        ok_count = 0
        review_count = 0
        fail_count = 0
        saved_ids: list[int] = []

        async with OpenRouterClient() as client:
            for i in range(1, args.count + 1):
                if total_cost >= args.max_cost_usd:
                    logger.warning(
                        "💰 Достигнут бюджет $%.2f (потрачено $%.2f). Останавливаюсь.",
                        args.max_cost_usd, total_cost,
                    )
                    break

                run_id = str(uuid.uuid4())
                print(f"\n─── Задача {i}/{args.count} (run_id={run_id[:8]}…) ───")

                try:
                    result, iter_logs = await run_pipeline(
                        subject=args.subject,
                        grade=args.grade,
                        level=args.level,
                        topic_hint=args.topic_hint,
                        client=client,
                    )
                except OpenRouterError as e:
                    logger.error("OpenRouter error: %s", e)
                    fail_count += 1
                    continue
                except Exception as e:
                    logger.exception("Pipeline error: %s", e)
                    fail_count += 1
                    continue

                total_cost += result.total_cost_usd

                # Отчёт по этой задаче
                print(f"  итераций: {result.iterations}")
                print(f"  стоимость: ${result.total_cost_usd:.4f}")
                print(f"  токены: in={result.total_tokens_input}, out={result.total_tokens_output}")
                print(f"  итого потрачено: ${total_cost:.4f} / ${args.max_cost_usd}")

                saved_task_id: Optional[int] = None

                if result.success:
                    ok_count += 1
                    print(f"  ✓ SUCCESS")
                    print(f"  условие: {result.task.statement[:120]}…" if result.task else "")
                    print(f"  ответ:   {result.task.expected_answer_short}" if result.task else "")

                    if not args.dry_run:
                        from models import db
                        saved_task_id = save_task_to_adaptive(
                            result, args.subject, args.grade, args.level, run_id,
                        )
                        saved_ids.append(saved_task_id)
                        log_generation_attempt(
                            run_id, args.subject, args.grade, args.level,
                            result, iter_logs, saved_task_id,
                        )
                        db.session.commit()
                        print(f"  💾 Saved AdaptiveTask id={saved_task_id}")

                elif result.sent_to_review:
                    review_count += 1
                    print(f"  ⚠️  MANUAL REVIEW (не сошлось за {result.iterations} итераций)")
                    if not args.dry_run:
                        from models import db
                        push_to_manual_review(
                            run_id, args.subject, args.grade, args.level, result,
                        )
                        log_generation_attempt(
                            run_id, args.subject, args.grade, args.level,
                            result, iter_logs, None,
                        )
                        db.session.commit()
                else:
                    fail_count += 1
                    print(f"  ❌ FAIL: {result.error}")

        # ─── Финальный отчёт ────────────────────────────────────────────────
        print(f"\n{'='*70}")
        print(f"ИТОГО:")
        print(f"  ✓ успешно:        {ok_count}")
        print(f"  ⚠ на ревью:       {review_count}")
        print(f"  ✗ ошибок:         {fail_count}")
        print(f"  💰 потрачено:     ${total_cost:.4f}")
        if saved_ids:
            print(f"  📝 saved ids:     {saved_ids}")
        print(f"{'='*70}\n")

        return 0

    finally:
        if app_ctx is not None:
            app_ctx.pop()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Регенерация задач Адаптивного теста через OpenRouter pipeline",
    )
    parser.add_argument("--subject", required=True,
                        help="algebra | geometry | number_theory | combinatorics | logic | probability")
    parser.add_argument("--grade", type=int, required=True, help="7..13")
    parser.add_argument("--level", type=int, required=True, help="1..7")
    parser.add_argument("--count", type=int, default=10, help="Сколько задач сгенерировать")
    parser.add_argument("--max-cost-usd", type=float, default=5.0,
                        help="Максимальный бюджет в долларах")
    parser.add_argument("--topic-hint", type=str, default=None,
                        help="Подсказка по теме")
    parser.add_argument("--deprecate-old", action="store_true",
                        help="Пометить старые задачи этой ячейки как deprecated")
    parser.add_argument("--dry-run", action="store_true",
                        help="Не писать в БД, только печатать результат")
    args = parser.parse_args()

    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n⏹  Остановлено пользователем")
        return 130


if __name__ == "__main__":
    sys.exit(main())
