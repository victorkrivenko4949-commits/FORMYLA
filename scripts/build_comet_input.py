"""
scripts/build_comet_input.py

Создаёт батч задач для Perplexity Comet — чтобы он нашёл
официальные авторские решения и вернул их в found_solutions.json.

ВАЖНО: AdaptiveTask не имеет полей olympiad/year/grade —
это задачи адаптивного теста, сгенерированные AI.
Поэтому Comet будет искать решения по тексту задачи и теме.

Запуск: python scripts/build_comet_input.py [--limit 20] [--topic number_theory]

Выход: batches/batch_01.json
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.abspath('.'))

# ── Добавляем колонку official_solution_latex если её нет ──
try:
    from app import app, db
    from sqlalchemy import text
    with app.app_context():
        # Проверяем наличие колонки
        result = db.session.execute(
            text("PRAGMA table_info(adaptive_tasks)")
        ).fetchall()
        cols = [r[1] for r in result]
        if 'official_solution_latex' not in cols:
            db.session.execute(text(
                "ALTER TABLE adaptive_tasks "
                "ADD COLUMN official_solution_latex TEXT"
            ))
            db.session.commit()
            print("[MIGRATION] ✓ Добавлена колонка official_solution_latex")
        else:
            print("[MIGRATION] ✓ Колонка official_solution_latex уже существует")
except Exception as e:
    print(f"[MIGRATION] Warning: {e}")

from app import app, db
from models import AdaptiveTask
from sqlalchemy import text

parser = argparse.ArgumentParser()
parser.add_argument('--limit', type=int, default=20,
                    help='Сколько задач включить в батч (default: 20)')
parser.add_argument('--topic', type=str, default=None,
                    help='Фильтр по теме (например: number_theory)')
parser.add_argument('--class_level', type=int, default=None,
                    help='Фильтр по классу (5-11)')
parser.add_argument('--output', type=str, default='batches/batch_01.json',
                    help='Путь к выходному файлу')
args = parser.parse_args()

os.makedirs('batches', exist_ok=True)

with app.app_context():
    # Строим запрос
    q = AdaptiveTask.query.filter(
        AdaptiveTask.is_flagged == False,  # только активные задачи
    )

    # Фильтр по теме
    if args.topic:
        q = q.filter(AdaptiveTask.topic.ilike(f'%{args.topic}%'))

    # Фильтр по классу
    if args.class_level:
        q = q.filter(AdaptiveTask.class_level == args.class_level)

    # Фильтруем задачи без official_solution_latex (если колонка есть)
    try:
        q = q.filter(
            db.or_(
                AdaptiveTask.official_solution_latex.is_(None),
                AdaptiveTask.official_solution_latex == ''
            )
        )
    except Exception:
        pass  # Колонка ещё не добавлена в модель — пропускаем фильтр

    tasks = q.order_by(AdaptiveTask.difficulty_level.desc()).limit(args.limit).all()

    if not tasks:
        print("❌ Задачи не найдены с заданными фильтрами!")
        sys.exit(1)

    output = []
    for t in tasks:
        output.append({
            "task_id": t.id,
            "class_level": t.class_level,
            "difficulty_level": t.difficulty_level,
            "topic": t.topic,
            "subtopic": t.subtopic or "",
            "statement": t.task_text,
            "current_answer": t.correct_answer or "",
            "current_solution_preview": (t.solution or "")[:300],
            # Поля для Comet — он должен заполнить:
            "official_solution_latex": None,
            "source_url": None,
            "confidence": None,
            # Инструкция для Comet:
            "_comet_instruction": (
                f"Найди официальное решение этой задачи по математике "
                f"для {t.class_level} класса по теме '{t.topic}'. "
                f"Правильный ответ: {t.correct_answer}. "
                f"Верни решение в LaTeX-формате в поле official_solution_latex. "
                f"Если не нашёл — оставь null."
            )
        })

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ Сохранено {len(output)} задач в {args.output}")
    print()
    print("Распределение по темам:")
    from collections import Counter
    topics = Counter(t['topic'] for t in output)
    for topic, cnt in topics.most_common():
        print(f"  {topic}: {cnt}")
    print()
    print("Распределение по классам:")
    classes = Counter(t['class_level'] for t in output)
    for cls, cnt in sorted(classes.items()):
        print(f"  Класс {cls}: {cnt}")
    print()
    print(f"Следующий шаг: передай {args.output} в Perplexity Comet.")
    print(f"Comet должен заполнить поле 'official_solution_latex' для каждой задачи")
    print(f"и сохранить результат в batches/found_solutions.json")
