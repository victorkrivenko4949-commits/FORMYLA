#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke-тест пайплайна: одна задача в dry-run режиме, без записи в БД.

Запуск:
    python scripts/test_pipeline_smoke.py
"""
import asyncio
import logging
import os
import sys

# Windows: переключаем stdout/stderr на UTF-8, иначе cp1251 крашится на emoji/unicode
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


async def main():
    from pipeline.runner import run_pipeline

    print("\n" + "=" * 70)
    print("SMOKE TEST: 1 задача (algebra, grade=9, level=2)")
    print("=" * 70)

    result, iter_logs = await run_pipeline(
        subject="algebra", grade=9, level=2,
        topic_hint="квадратные уравнения",
    )

    print("\n" + "-" * 70)
    print(f"Success:     {result.success}")
    print(f"Iterations:  {result.iterations}")
    print(f"Cost:        ${result.total_cost_usd:.4f}")
    print(f"Tokens:      in={result.total_tokens_input}  out={result.total_tokens_output}")

    if result.task:
        print(f"\nУсловие:\n  {result.task.statement}")
        print(f"\nОтвет: {result.task.expected_answer_short}")
        print(f"Тип:   {result.task.answer_type}")
        print(f"Шаги:  {result.task.estimated_steps}")
        print(f"Идеи:  {result.task.key_ideas}")

    print("\n--- ITERATIONS ---")
    for il in iter_logs:
        print(f"  [{il.iteration}] {il.stage:10s}  {il.verdict or '-':6s}  "
              f"{il.model:35s}  ${il.cost_usd:.4f}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
