"""
Скрипт нормализации базы задач раздела "Темы"
Оставляет ровно по 3 задачи на каждую комбинацию (grade, subject, subtopic, difficulty)
"""
import json
import random
from collections import defaultdict

def load_problems():
    """Загрузить текущую базу задач"""
    try:
        from problems import PROBLEMS_DB
        return PROBLEMS_DB
    except ImportError:
        print("❌ Ошибка: не удалось импортировать problems.py")
        return []

def normalize_problems():
    """Нормализовать базу задач до 3 задач на комбинацию"""
    problems_db = load_problems()
    
    print(f"[INFO] Zagruzheno zadach: {len(problems_db)}")
    print("="*80)
    
    # Группируем задачи по (subject, subtopic, grade, difficulty)
    groups = defaultdict(list)
    
    for problem in problems_db:
        key = (
            problem.get('subject'),
            problem.get('subtopic'),
            problem.get('grade'),
            problem.get('difficulty')
        )
        groups[key].append(problem)
    
    print(f"[INFO] Najdeno unikalnyh kombinatsij: {len(groups)}")
    print("="*80)
    
    # Статистика
    total_kept = 0
    total_hidden = 0
    groups_with_shortage = []
    groups_with_excess = []
    
    normalized_problems = []
    
    for key, tasks in groups.items():
        subject, subtopic, grade, difficulty = key
        count = len(tasks)
        
        if count < 3:
            # Нехватка задач
            groups_with_shortage.append({
                'subject': subject,
                'subtopic': subtopic,
                'grade': grade,
                'difficulty': difficulty,
                'count': count
            })
            # Добавляем все, что есть
            for task in tasks:
                task['is_active'] = True
                normalized_problems.append(task)
            total_kept += count
            
        elif count == 3:
            # Идеально - ровно 3 задачи
            for task in tasks:
                task['is_active'] = True
                normalized_problems.append(task)
            total_kept += 3
            
        else:
            # Избыток задач - оставляем первые 3
            groups_with_excess.append({
                'subject': subject,
                'subtopic': subtopic,
                'grade': grade,
                'difficulty': difficulty,
                'total': count,
                'hidden': count - 3
            })
            
            # Берем первые 3 задачи (можно сделать random.sample для случайного выбора)
            selected = tasks[:3]  # Или: random.sample(tasks, 3)
            hidden = tasks[3:]
            
            for task in selected:
                task['is_active'] = True
                normalized_problems.append(task)
            
            for task in hidden:
                task['is_active'] = False
                normalized_problems.append(task)
            
            total_kept += 3
            total_hidden += (count - 3)
    
    # Выводим отчет
    print("\n[STATISTIKA NORMALIZATSII]:")
    print("="*80)
    print(f"[OK] Aktivnyh zadach (is_active=True): {total_kept}")
    print(f"[HIDDEN] Skrytyh zadach (is_active=False): {total_hidden}")
    print(f"[TOTAL] Vsego zadach v baze: {len(normalized_problems)}")
    print("="*80)
    
    # Группы с избытком
    if groups_with_excess:
        print(f"\n[WARNING] GRUPPY S IZBYTKOM (skryto lishnih zadach):")
        print("="*80)
        for i, group in enumerate(groups_with_excess[:20], 1):  # Показываем первые 20
            print(f"{i}. {group['subject']}/{group['subtopic']} | "
                  f"Класс {group['grade']} | Уровень {group['difficulty']} | "
                  f"Было: {group['total']}, Скрыто: {group['hidden']}")
        if len(groups_with_excess) > 20:
            print(f"... и еще {len(groups_with_excess) - 20} групп")
        print(f"\nВсего групп с избытком: {len(groups_with_excess)}")
    
    # Группы с нехваткой
    if groups_with_shortage:
        print(f"\n[WARNING] GRUPPY S NEHVATKOJ (nuzhno dogenerirovat):")
        print("="*80)
        for i, group in enumerate(groups_with_shortage, 1):
            shortage = 3 - group['count']
            print(f"{i}. {group['subject']}/{group['subtopic']} | "
                  f"Класс {group['grade']} | Уровень {group['difficulty']} | "
                  f"Есть: {group['count']}, Нужно: {shortage}")
        print(f"\nВсего групп с нехваткой: {len(groups_with_shortage)}")
    
    # Сохраняем результат
    save_normalized_problems(normalized_problems)
    
    return {
        'total_kept': total_kept,
        'total_hidden': total_hidden,
        'groups_with_excess': len(groups_with_excess),
        'groups_with_shortage': len(groups_with_shortage)
    }

def save_normalized_problems(problems):
    """Сохранить нормализованную базу"""
    output_file = 'problems_normalized.py'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("# Нормализованная база задач (по 3 задачи на комбинацию)\n\n")
        f.write("PROBLEMS_DB = ")
        f.write(json.dumps(problems, ensure_ascii=False, indent=0))
    
    print(f"\n[SAVE] Normalizovannaja baza sohranena v {output_file}")
    print(f"[WARNING] VAZHNO: Zamenite problems.py na problems_normalized.py vruchnuju!")
    print(f"   Команда: mv problems_normalized.py problems.py")

def main():
    print("NORMALIZATSIYA BAZY ZADACH RAZDELA 'TEMY'")
    print("="*80)
    print("Tsel: Ostavit rovno po 3 zadachi na kazhduju kombinatsiju")
    print("      (subject, subtopic, grade, difficulty)")
    print("="*80)
    
    stats = normalize_problems()
    
    print("\n" + "="*80)
    print("NORMALIZATSIYA ZAVERSHENA!")
    print("="*80)

if __name__ == '__main__':
    main()
