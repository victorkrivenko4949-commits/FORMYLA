# builder.py — упрощённый: вводим только условие, ИИ решает уже на сайте
import json
import re
from pathlib import Path

DB_PATH = Path("problems_new.py")

SUBJECTS = {
    "1": ("algebra", "Алгебра"),
    "2": ("geometry", "Геометрия"),
    "3": ("combinatorics", "Комбинаторика"),
    "4": ("number_theory", "Теория чисел"),
}

LEVELS = {
    "1": ("easy", "Лёгкий"),
    "2": ("medium", "Средний"),
    "3": ("hard", "Сложный"),
}


def load_db():
    if not DB_PATH.exists():
        return []

    text = DB_PATH.read_text(encoding="utf-8")
    match = re.search(r"PROBLEMS_DB\s*=\s*(\[.*\])", text, re.S)
    if not match:
        return []

    data_str = match.group(1)
    return json.loads(data_str)


def save_db(problems):
    with DB_PATH.open("w", encoding="utf-8") as f:
        f.write("PROBLEMS_DB = ")
        json.dump(problems, f, ensure_ascii=False, indent=4)


def main():
    problems = load_db()
    next_id = max((p.get("id", 0) for p in problems), default=0) + 1

    print("=== Редактор задач FORMYLA (только условия) ===")
    print("Существующих задач:", len(problems))
    print("Следующий id:", next_id)
    print("Пустое УСЛОВИЕ — завершить.\n")

    while True:
        print("Предмет:")
        for k, (_, name) in SUBJECTS.items():
            print(f"  {k}. {name}")
        subject_choice = input("Выбери цифру (1-4): ").strip()
        if subject_choice not in SUBJECTS:
            print("Неверный выбор, попробуй ещё.\n")
            continue
        subject, subject_name = SUBJECTS[subject_choice]

        grade_str = input("Класс (5-9): ").strip()
        if not grade_str.isdigit():
            print("Нужно число 5-9.\n")
            continue
        grade = int(grade_str)

        print("Уровень:")
        for k, (_, name) in LEVELS.items():
            print(f"  {k}. {name}")
        level_choice = input("Выбери цифру (1-3): ").strip()
        if level_choice not in LEVELS:
            print("Неверный выбор, попробуй ещё.\n")
            continue
        level, level_name = LEVELS[level_choice]

        title = input("Краткое название задачи: ").strip()

        print("\nВведи УСЛОВИЕ задачи (одной строкой). Пусто — выход.")
        statement = input("Условие: ").strip()
        if not statement:
            break

        problem = {
            "id": next_id,
            "subject": subject,
            "grade": grade,
            "level": level,
            "title": title,
            "statement": statement
            # solution не нужен, решит ИИ
        }
        problems.append(problem)
        print(f"\nЗадача #{next_id} добавлена: {subject_name}, {grade} класс, {level_name}.\n")

        next_id += 1

    save_db(problems)
    print("\nГотово! Всего задач теперь:", len(problems))
    print("Файл обновлён:", DB_PATH)


if __name__ == "__main__":
    main()
