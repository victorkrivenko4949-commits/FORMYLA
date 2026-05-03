#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test: один вызов generate_task() через реальные API.

Запуск:
    python scripts/smoke_pipeline.py

Что делает:
    1. Создаёт DeepSeekClient + GeminiClient
    2. Вызывает pipeline.generate_task() для одной задачи
    3. Печатает stages_log и финальный текст
    4. Проверяет что задача сохранилась в БД
"""
import sys
import os
import json
import time

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import OlympiadVariant, OlympiadTask
from ai.deepseek_client import DeepSeekClient
from ai.gemini_client import GeminiClient
from services.pipeline import OlympiadPipeline
from services.pipeline.types import PipelineError


def main():
    print("=" * 70)
    print("🔬 SMOKE TEST: Pipeline generate_task()")
    print("=" * 70)

    with app.app_context():
        # ── Инициализация клиентов ──
        deepseek = DeepSeekClient()
        print(f"✅ DeepSeekClient: {deepseek.base_url}")

        # OpenRouter ключ — берём из app.py (hardcoded) или env
        openrouter_key = os.environ.get('OPENROUTER_API_KEY')
        if not openrouter_key or openrouter_key == 'your_api_key_here':
            # Fallback: берём из app.py глобальной переменной
            try:
                from app import OPENROUTER_API_KEY
                openrouter_key = OPENROUTER_API_KEY
                print(f"✅ OpenRouter key from app.py: {openrouter_key[:20]}...")
            except ImportError:
                print("❌ OPENROUTER_API_KEY не найден!")
                sys.exit(1)

        gemini = GeminiClient(api_key=openrouter_key)
        print(f"✅ GeminiClient: {gemini.model}")

        # ── Создаём пайплайн (без search backend для smoke) ──
        pipeline = OlympiadPipeline(deepseek, gemini, search_backend=None)
        print(f"✅ Pipeline initialized (search_backend=None)")

        # ── Параметры задачи ──
        import uuid
        variant_id = str(uuid.uuid4())
        olympiad = "Всероссийская олимпиада"
        stage = "municipal"
        grade = 8

        print(f"\n📋 Параметры:")
        print(f"   variant_id: {variant_id}")
        print(f"   olympiad:   {olympiad}")
        print(f"   stage:      {stage}")
        print(f"   grade:      {grade}")

        # Создаём OlympiadVariant вручную (generate_task не создаёт его)
        variant = OlympiadVariant(
            id=variant_id,
            olympiad_slug="vos",
            olympiad_title=olympiad,
            round_key=stage,
            round_title="Муниципальный этап",
            grade=grade,
        )
        db.session.add(variant)
        db.session.flush()

        # ── Запуск ──
        print(f"\n🚀 Запуск generate_task()...")
        t0 = time.time()

        try:
            result = pipeline.generate_task(
                variant_id=variant_id,
                position=1,
                olympiad=olympiad,
                stage=stage,
                grade=grade,
            )
            elapsed = time.time() - t0

            print(f"\n✅ Задача сгенерирована за {elapsed:.1f}с")
            print(f"   task_id:  {result.task_id}")
            print(f"   topic:    {result.topic}")
            print(f"   year:     {result.source_year}")
            print(f"   problem:  {result.source_problem}")
            print(f"   author:   {result.author}")

            print(f"\n📝 Финальный текст ({len(result.final_text)} символов):")
            print("-" * 50)
            print(result.final_text)
            print("-" * 50)

            if result.final_solution:
                print(f"\n📐 Решение ({len(result.final_solution)} символов):")
                print("-" * 50)
                print(result.final_solution[:500])
                if len(result.final_solution) > 500:
                    print(f"... (ещё {len(result.final_solution) - 500} символов)")
                print("-" * 50)

            if result.final_answer:
                print(f"\n🎯 Ответ: {result.final_answer}")

            print(f"\n📊 Stages log:")
            for entry in result.stages_log:
                stage_num = entry.get('stage', '?')
                ok = entry.get('ok', entry.get('unique', entry.get('valid', '?')))
                attempt = entry.get('attempt', '')
                extra = {k: v for k, v in entry.items()
                         if k not in ('stage', 'ok', 'unique', 'valid', 'attempt')}
                att_str = f" (attempt {attempt})" if attempt else ""
                ext_str = f" {extra}" if extra else ""
                status = "✅" if ok else "❌"
                print(f"   Stage {stage_num}{att_str}: {status}{ext_str}")

            # ── Проверка в БД ──
            db.session.commit()
            task_in_db = OlympiadTask.query.get(result.task_id)
            if task_in_db:
                print(f"\n💾 Задача в БД: id={task_in_db.id}, "
                      f"status={task_in_db.status}, "
                      f"variant_id={task_in_db.variant_id}")
                print(f"   text length: {len(task_in_db.text)}")
                print(f"   pipeline_version: {task_in_db.pipeline_version}")
            else:
                print(f"\n❌ Задача НЕ найдена в БД по id={result.task_id}")

            print(f"\n{'=' * 70}")
            print(f"🎉 SMOKE TEST PASSED ({elapsed:.1f}s)")
            print(f"{'=' * 70}")

        except PipelineError as e:
            elapsed = time.time() - t0
            db.session.rollback()
            print(f"\n❌ PipelineError ({elapsed:.1f}s): {e}")
            print(f"   stage:    {e.stage}")
            print(f"   attempts: {e.attempts}")
            sys.exit(1)

        except Exception as e:
            elapsed = time.time() - t0
            db.session.rollback()
            print(f"\n❌ Unexpected error ({elapsed:.1f}s): {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
