"""
Утилита для массового импорта авторских решений в базу олимпиад
Использование: python import_olympiad_solutions.py solutions.json
"""
import json
import sys
import os

def load_olympiads():
    """Загрузить текущую базу олимпиад"""
    try:
        from olympiads import OLYMPIADS_DB
        return OLYMPIADS_DB
    except ImportError:
        print("❌ Ошибка: не удалось импортировать olympiads.py")
        sys.exit(1)

def update_solutions(solutions_file):
    """
    Обновить решения в базе олимпиад
    
    Формат JSON файла:
    {
        "1": {  // ID пробника (combo_id)
            "1": "Текст решения задачи №1",  // Номер задачи в пробнике
            "2": "Текст решения задачи №2",
            ...
        },
        "2": {
            "1": "Текст решения...",
            ...
        }
    }
    """
    # Загружаем файл с решениями
    if not os.path.exists(solutions_file):
        print(f"❌ Файл {solutions_file} не найден")
        sys.exit(1)
    
    with open(solutions_file, 'r', encoding='utf-8') as f:
        solutions_data = json.load(f)
    
    print(f"📂 Загружено решений для {len(solutions_data)} пробников")
    
    # Загружаем базу олимпиад
    olympiads_db = load_olympiads()
    
    # Обновляем решения
    updated_count = 0
    skipped_count = 0
    
    for combo_id_str, problems_solutions in solutions_data.items():
        combo_id = int(combo_id_str)
        
        # Находим пробник по ID
        combo = next((c for c in olympiads_db if c.get('id') == combo_id), None)
        
        if not combo:
            print(f"⚠️  Пробник с ID={combo_id} не найден, пропускаем")
            skipped_count += 1
            continue
        
        # Обновляем решения задач
        for problem_num_str, solution_text in problems_solutions.items():
            problem_num = int(problem_num_str)
            
            # Находим задачу по номеру
            problems = combo.get('problems', [])
            problem = next((p for p in problems if p.get('num') == problem_num), None)
            
            if not problem:
                print(f"⚠️  Задача №{problem_num} в пробнике ID={combo_id} не найдена")
                continue
            
            # Обновляем решение
            problem['solution'] = solution_text
            updated_count += 1
            print(f"✅ Обновлено решение: Пробник ID={combo_id}, Задача №{problem_num}")
    
    print(f"\n📊 Статистика:")
    print(f"   Обновлено решений: {updated_count}")
    print(f"   Пропущено пробников: {skipped_count}")
    
    # Сохраняем обновленную базу
    save_olympiads(olympiads_db)

def save_olympiads(olympiads_db):
    """Сохранить обновленную базу олимпиад в файл"""
    output_file = 'olympiads_updated.py'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Обновленная база олимпиад с авторскими решениями\n")
        f.write("OLYMPIADS_DB = ")
        f.write(json.dumps(olympiads_db, ensure_ascii=False, indent=4))
    
    print(f"\n💾 Обновленная база сохранена в {output_file}")
    print(f"⚠️  ВАЖНО: Замените olympiads.py на olympiads_updated.py вручную!")
    print(f"   Команда: mv olympiads_updated.py olympiads.py")

def main():
    if len(sys.argv) < 2:
        print("Использование: python import_olympiad_solutions.py solutions.json")
        print("\nФормат JSON файла:")
        print('''{
    "1": {
        "1": "Решение задачи 1 пробника 1",
        "2": "Решение задачи 2 пробника 1"
    },
    "2": {
        "1": "Решение задачи 1 пробника 2"
    }
}''')
        sys.exit(1)
    
    solutions_file = sys.argv[1]
    update_solutions(solutions_file)

if __name__ == '__main__':
    main()
