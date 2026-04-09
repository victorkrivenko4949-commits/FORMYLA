# scripts/audit_olympiads.py
import sys

sys.path.insert(0, ".")

try:
    from olympiads import OLYMPIADS_DB
except ImportError:
    try:
        from olympiads_backup_before_rebuild import OLYMPIADS_DB
    except ImportError:
        print("Ошибка: Не найден файл базы олимпиад.")
        sys.exit(1)

# Создаем структуру для подсчета: Олимпиада -> Этап -> Класс -> Количество вариантов
audit = {}

for combo in OLYMPIADS_DB:
    oly = combo.get('olympiad_title', combo.get('olympiad', 'Unknown'))
    round_name = combo.get('round_title', combo.get('round', 'Unknown'))
    grade = combo.get('grade', 0)
    
    if oly not in audit:
        audit[oly] = {}
    if round_name not in audit[oly]:
        audit[oly][round_name] = {}
    if grade not in audit[oly][round_name]:
        audit[oly][round_name][grade] = 0
        
    audit[oly][round_name][grade] += 1

print("\n" + "="*50)
print("АУДИТ БАЗЫ ОЛИМПИАД (ГДЕ ЕСТЬ ДЫРЫ)")
print("="*50)

for oly, rounds in sorted(audit.items()):
    print(f"\n{oly.upper()}:")
    for round_name, grades in sorted(rounds.items()):
        print(f"  {round_name}:")
        
        # Проверяем классы с 5 по 11
        for g in range(5, 12):
            count = grades.get(g, 0)
            if count > 0:
                print(f"      [OK] {g} класс: {count} вариантов")
            else:
                print(f"      [EMPTY] {g} класс: ПУСТО")
