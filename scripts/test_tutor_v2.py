"""
Standalone-тест AI-тьютора v2.
Запуск: python scripts/test_tutor_v2.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

# Подавляем лишний вывод Flask при импорте
os.environ.setdefault('FLASK_ENV', 'testing')

from app import app, db
from models import AdaptiveTask
from services.ai_tutor_v2 import tutor_explain
from ai.deepseek_client import DeepSeekClient


def pretty(label, text, limit=2500):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    if text is None:
        print('(None)')
    else:
        s = str(text)
        print(s[:limit])
        if len(s) > limit:
            print(f"... [обрезано, всего {len(s)} символов]")


with app.app_context():
    # ── 1. Ищем проблемную задачу ──────────────────────────────
    task = AdaptiveTask.query.filter(
        AdaptiveTask.task_text.like('%n и 16%')
    ).first()

    if not task:
        # Попробуем более широкий поиск
        task = AdaptiveTask.query.filter(
            AdaptiveTask.task_text.like('%16%'),
            AdaptiveTask.task_text.like('%24%'),
            AdaptiveTask.task_text.like('%делителя%'),
        ).first()

    if not task:
        print("❌ Задача 'n и 16' не найдена в adaptive_tasks!")
        print("   Ищем любую задачу по теории чисел для теста...")
        task = AdaptiveTask.query.filter(
            AdaptiveTask.topic.like('%number%')
        ).first()
        if not task:
            task = AdaptiveTask.query.first()
        if task:
            print(f"   Используем задачу id={task.id} для теста")
        else:
            print("❌ База данных пуста!")
            sys.exit(1)

    # ── 2. Показываем задачу ────────────────────────────────────
    pretty("ЗАДАЧА",
           f"id={task.id}\n"
           f"topic={task.topic}\n"
           f"class_level={task.class_level}\n"
           f"difficulty_level={task.difficulty_level}\n"
           f"correct_answer={repr(task.correct_answer)}\n"
           f"solution exists: {bool(task.solution)}\n"
           f"solution length: {len(task.solution) if task.solution else 0}\n"
           f"\nTASK TEXT:\n{task.task_text}")

    pretty("SOLUTION В БД (первые 1500 симв)",
           task.solution or '(NULL)', 1500)

    # ── 3. Запускаем тьютор ─────────────────────────────────────
    user_answer = '10'
    print(f"\n🚀 Вызываем tutor_explain(task, user_answer='{user_answer}', ai_client)...")
    print("   (ждём ответа DeepSeek, ~10-30 сек)")

    ai_client = DeepSeekClient()
    result = tutor_explain(task, user_answer, ai_client)

    # ── 4. Выводим результаты ───────────────────────────────────
    pretty("STATUS", result['status'])
    pretty("VALIDATION ERRORS", str(result.get('errors', [])))

    pretty("RAW RESPONSE (полный вывод DeepSeek, с <thinking>)",
           result.get('raw_response', '(нет)'))

    pretty("EXTRACTED SOLUTION (что УВИДИТ ученик)",
           result['solution'])

    # ── 5. Итог ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  ИТОГ")
    print('='*60)

    if result['status'] == 'ok':
        print("✅ Модель прошла валидацию — статус OK")
    else:
        print(f"⚠️  Сработал FALLBACK, причины: {result['errors']}")

    # Проверяем запрещённые слова
    bad_words = ['возможно', 'вероятно', 'скорее всего',
                 'наверное', 'не уверен', 'к сожалению']
    sol_low = result['solution'].lower()
    found_bad = [w for w in bad_words if w in sol_low]
    if found_bad:
        print(f"❌ В EXTRACTED SOLUTION есть запрещённые слова: {found_bad}")
    else:
        print("✅ Нет запрещённых слов в выводе ученику")

    # Проверяем наличие тегов в raw
    raw = result.get('raw_response', '')
    has_thinking = '<thinking>' in raw.lower()
    has_solution = '<solution>' in raw.lower()
    print(f"{'✅' if has_thinking else '❌'} RAW содержит <thinking>: {has_thinking}")
    print(f"{'✅' if has_solution else '❌'} RAW содержит <solution>: {has_solution}")

    # Проверяем что extracted != raw (теги сработали)
    if result['status'] == 'ok':
        extracted_len = len(result['solution'])
        raw_len = len(raw)
        if extracted_len < raw_len * 0.9:
            print(f"✅ Extracted ({extracted_len} симв) < Raw ({raw_len} симв) — теги сработали")
        else:
            print(f"⚠️  Extracted ({extracted_len} симв) ≈ Raw ({raw_len} симв) — теги могли не сработать")

    print()
