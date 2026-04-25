"""
scripts/build_olympiad_batches.py

Создаёт батчи олимпиадных задач для Perplexity Comet.
Источник: olympiads.py (OLYMPIADS_DB) — реальные задачи ВсОШ, Физтех, ПВГ и т.д.

Comet должен найти официальные авторские решения по olympiad+year+grade+round+problem_num.

Запуск: python scripts/build_olympiad_batches.py [--limit 20] [--olympiad vsosh]

Выход: batches/batch_<olympiad>.json
"""
import sys
import os
import json
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath('.'))

parser = argparse.ArgumentParser()
parser.add_argument('--limit', type=int, default=20,
                    help='Задач на источник (default: 20)')
parser.add_argument('--olympiad', type=str, default=None,
                    help='Фильтр по олимпиаде (vsosh, phystech, pvg, ...)')
parser.add_argument('--no_solution_only', action='store_true',
                    help='Только задачи без solution')
args = parser.parse_args()

os.makedirs('batches', exist_ok=True)

# Импортируем данные
from olympiads import OLYMPIADS_DB

print(f"Загружено {len(OLYMPIADS_DB)} пробников из olympiads.py")

# Группируем задачи по олимпиаде
by_olympiad = defaultdict(list)

for combo in OLYMPIADS_DB:
    olympiad = combo.get('olympiad', 'unknown')

    # Фильтр по олимпиаде
    if args.olympiad and olympiad != args.olympiad:
        continue

    for problem in combo.get('problems', []):
        solution = problem.get('solution', '')

        # Фильтр: только без solution (если флаг задан)
        if args.no_solution_only and solution and len(solution) > 50:
            continue

        entry = {
            "combo_id": combo.get('id'),
            "olympiad": olympiad,
            "olympiad_title": combo.get('olympiad_title', ''),
            "year": combo.get('year'),
            "grade": combo.get('grade'),
            "round": combo.get('round', ''),
            "round_title": combo.get('round_title', ''),
            "problem_num": problem.get('num'),
            "statement": problem.get('text', ''),
            "current_answer": problem.get('answer', ''),
            "has_solution": bool(solution and len(solution) > 50),
            "solution_preview": solution[:200] if solution else '',
            # Поля для Comet:
            "official_solution_latex": None,
            "source_url": combo.get('source_url', ''),
            "confidence": None,
            "_comet_instruction": (
                f"Найди официальное решение задачи №{problem.get('num')} "
                f"олимпиады '{combo.get('olympiad_title')}' "
                f"{combo.get('year')} года, {combo.get('grade')} класс, "
                f"этап '{combo.get('round_title', '')}'. "
                f"Правильный ответ: {problem.get('answer', '')}. "
                f"Верни решение в LaTeX-формате в поле official_solution_latex. "
                f"Если не нашёл — оставь null."
            )
        }
        by_olympiad[olympiad].append(entry)

# Статистика
print(f"\nРаспределение по олимпиадам:")
for olympiad, tasks in sorted(by_olympiad.items(), key=lambda x: -len(x[1])):
    has_sol = sum(1 for t in tasks if t['has_solution'])
    no_sol = len(tasks) - has_sol
    print(f"  {olympiad:20s}: {len(tasks):4d} задач "
          f"(с решением: {has_sol}, без: {no_sol})")

print()

# Создаём батчи
created_files = []
for olympiad, tasks in by_olympiad.items():
    # Берём задачи без решения в приоритете, потом с решением
    no_sol = [t for t in tasks if not t['has_solution']]
    with_sol = [t for t in tasks if t['has_solution']]

    # Приоритет: без решения
    batch = (no_sol + with_sol)[:args.limit]

    if not batch:
        continue

    filename = f"batches/batch_{olympiad}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)

    created_files.append((filename, len(batch), len(no_sol), len(with_sol)))
    print(f"[OK] {filename}: {len(batch)} zadach "
          f"(bez resheniya: {min(len(no_sol), args.limit)}, "
          f"s resheniem: {max(0, len(batch)-len(no_sol))})")

print(f"\nИтого создано {len(created_files)} батчей")
print()

# Показываем примеры из каждого батча
print("=== Примеры задач из батчей ===")
for filename, total, no_sol, with_sol in created_files[:5]:
    with open(filename, encoding='utf-8') as f:
        data = json.load(f)
    if data:
        ex = data[0]
        print(f"\n{filename}:")
        print(f"  olympiad={ex['olympiad']}, year={ex['year']}, "
              f"grade={ex['grade']}, round={ex['round']}")
        print(f"  problem_num={ex['problem_num']}")
        print(f"  statement: {ex['statement'][:100]}...")
        print(f"  answer: {ex['current_answer'][:60]}")
        print(f"  has_solution: {ex['has_solution']}")
        print(f"  source_url: {ex['source_url'] or '(нет)'}")

print()
print("Следующий шаг: передай батчи в Perplexity Comet.")
print("Comet должен заполнить 'official_solution_latex' и сохранить")
print("результаты в batches/found_solutions_<olympiad>.json")
