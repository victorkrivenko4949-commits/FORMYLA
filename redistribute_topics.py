"""
Скрипт-реаниматор для равномерного распределения задач по сетке
Цель: Ровно по 3 задачи на каждую комбинацию (subject, subtopic, grade, level)
"""
import json
import random
from collections import defaultdict

# Определяем структуру сетки
GRADES = [5, 6, 7, 8, 9, 10, 11]
LEVELS = [1, 2, 3]

# Маппинг тем (subject -> subtopics)
SUBJECTS_MAP = {
    'algebra': ['equations', 'inequalities', 'progressions'],
    'geometry': ['basics', 'triangles', 'circles'],
    'number_theory': ['divisibility', 'primes_and_equations'],
    'combinatorics': ['counting', 'dirichlet_and_graphs'],
    'knights_liars': ['basic_logic'],
    'movement': ['linear', 'circular'],
    'games': ['strategy'],
    'coloring': ['graph_coloring']
}

def load_problems():
    """Загрузить текущую базу задач"""
    try:
        from problems import PROBLEMS_DB
        return PROBLEMS_DB
    except ImportError:
        print("[ERROR] Ne udalos importirovat problems.py")
        return []

def redistribute_problems():
    """Перераспределить задачи равномерно по сетке"""
    problems_db = load_problems()
    
    print(f"[INFO] Zagruzheno zadach: {len(problems_db)}")
    print("="*80)
    
    # Группируем задачи по subject
    by_subject = defaultdict(list)
    
    for problem in problems_db:
        subject = problem.get('subject', 'unknown')
        by_subject[subject].append(problem)
    
    print(f"[INFO] Najdeno tem (subjects): {len(by_subject)}")
    for subject, tasks in by_subject.items():
        print(f"  - {subject}: {len(tasks)} zadach")
    print("="*80)
    
    # Создаем пустую сетку
    grid = {}
    for subject, subtopics in SUBJECTS_MAP.items():
        for subtopic in subtopics:
            for grade in GRADES:
                for level in LEVELS:
                    key = (subject, subtopic, grade, level)
                    grid[key] = []
    
    print(f"[INFO] Sozdana setka: {len(grid)} yacheek")
    print(f"       (7 klassov x {sum(len(v) for v in SUBJECTS_MAP.values())} podtem x 3 urovnya)")
    print("="*80)
    
    # Распределяем задачи по сетке
    redistributed = []
    stats = {
        'filled': 0,
        'partial': 0,
        'empty': 0
    }
    
    for subject, tasks in by_subject.items():
        if subject not in SUBJECTS_MAP:
            print(f"[WARNING] Neizvestnaja tema: {subject}, propuskaem")
            continue
        
        subtopics = SUBJECTS_MAP[subject]
        tasks_copy = tasks.copy()
        random.shuffle(tasks_copy)  # Перемешиваем для случайного распределения
        
        task_index = 0
        
        # Распределяем по всем ячейкам этой темы
        for subtopic in subtopics:
            for grade in GRADES:
                for level in LEVELS:
                    key = (subject, subtopic, grade, level)
                    
                    # Берем 3 задачи для этой ячейки
                    for _ in range(3):
                        if task_index < len(tasks_copy):
                            task = tasks_copy[task_index].copy()
                            # Обновляем метаданные
                            task['subject'] = subject
                            task['subtopic'] = subtopic
                            task['grade'] = grade
                            task['difficulty'] = level
                            task['is_active'] = True
                            
                            grid[key].append(task)
                            task_index += 1
    
    # Собираем все задачи из сетки
    for key, tasks in grid.items():
        subject, subtopic, grade, level = key
        count = len(tasks)
        
        if count == 3:
            stats['filled'] += 1
        elif count > 0:
            stats['partial'] += 1
        else:
            stats['empty'] += 1
        
        redistributed.extend(tasks)
    
    print(f"\n[STATISTIKA RASPREDELENIJA]:")
    print("="*80)
    print(f"[OK] Polnostju zapolnennyh yacheek (3 zadachi): {stats['filled']}")
    print(f"[PARTIAL] Chastichno zapolnennyh (1-2 zadachi): {stats['partial']}")
    print(f"[EMPTY] Pustyh yacheek (0 zadach): {stats['empty']}")
    print(f"[TOTAL] Raspredeleno zadach: {len(redistributed)}")
    print("="*80)
    
    # Показываем примеры заполненных ячеек
    print(f"\n[PRIMERY ZAPOLNENNYH YACHEEK]:")
    print("="*80)
    sample_count = 0
    for key, tasks in grid.items():
        if len(tasks) == 3 and sample_count < 10:
            subject, subtopic, grade, level = key
            print(f"  {subject}/{subtopic} | Klass {grade} | Uroven {level} - 3 zadachi")
            sample_count += 1
    
    # Показываем ячейки с нехваткой
    print(f"\n[YACHEJKI S NEHVATKOJ]:")
    print("="*80)
    shortage_count = 0
    for key, tasks in grid.items():
        if 0 < len(tasks) < 3:
            subject, subtopic, grade, level = key
            shortage = 3 - len(tasks)
            print(f"  {subject}/{subtopic} | Klass {grade} | Uroven {level} | Est: {len(tasks)}, Nuzhno: {shortage}")
            shortage_count += 1
            if shortage_count >= 20:
                print(f"  ... i eshe {sum(1 for k, t in grid.items() if 0 < len(t) < 3) - 20} yacheek")
                break
    
    # Сохраняем результат
    save_redistributed_problems(redistributed)
    
    return stats

def save_redistributed_problems(problems):
    """Сохранить перераспределенную базу"""
    output_file = 'problems_redistributed.py'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("# Pereraspredelennaja baza zadach (rovno po 3 na kombinatsiju)\n\n")
        f.write("PROBLEMS_DB = ")
        # Используем repr() вместо json.dumps() для корректного Python синтаксиса
        f.write(repr(problems))
    
    print(f"\n[SAVE] Pereraspredelennaja baza sohranena v {output_file}")
    print(f"[WARNING] VAZHNO: Zamenite problems.py na problems_redistributed.py!")
    print(f"   Komanda: move problems_redistributed.py problems.py")

def main():
    print("PERERASPREDELENIE ZADACH RAZDELA 'TEMY'")
    print("="*80)
    print("Tsel: Ravnomerno raspredelit zadachi po setke")
    print("      Rovno po 3 zadachi na kazhduju kombinatsiju")
    print("="*80)
    
    stats = redistribute_problems()
    
    print("\n" + "="*80)
    print("PERERASPREDELENIE ZAVERSHENO!")
    print("="*80)

if __name__ == '__main__':
    main()
