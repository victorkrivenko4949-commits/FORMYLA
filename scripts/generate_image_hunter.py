#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор IMAGE_HUNTER.html - список всех задач с рисунками
С персональными ссылками на архивы
"""

import sys
sys.path.insert(0, '.')
from olympiads import OLYMPIADS_DB


def get_archive_url(olympiad, year, grade):
    """Получить персональную ссылку на архив"""
    if olympiad == 'formula_unity':
        return f"https://www.formulo.org/ru/olymp/{year}-math/"
    elif olympiad == 'lomonosov':
        return "https://olymp.msu.ru/rus/page/main/29/page/arhiv-zadanij-i-otvetov-olimpiady-shkolnikov-lomonosov"
    elif olympiad == 'vsosh':
        return f"https://olimpiada.ru/activity/74/tasks"
    elif olympiad == 'kurchatov':
        return "https://old.olimpiadakurchatov.ru/archive"
    elif olympiad == 'vysshaya_proba':
        return "https://olymp.hse.ru/mmo/tasks-math"
    elif olympiad == 'pvg':
        return "https://pvg.mk.ru/archive/"
    else:
        # Google поиск для остальных
        olympiad_title = olympiad.replace('_', ' ').title()
        return f"https://www.google.com/search?q={olympiad_title}+{year}+{grade}+класс+задания+pdf"


def find_tasks_with_images():
    """Найти все задачи с упоминанием рисунка"""
    tasks = []
    keywords = ['рисунок', 'чертеж', 'схема', 'график', 'диаграмм', 'см. рис', 'на рисунке']
    
    for combo in OLYMPIADS_DB:
        combo_id = combo.get('id')
        olympiad = combo.get('olympiad')
        olympiad_title = combo.get('olympiad_title', olympiad)
        year = combo.get('year')
        grade = combo.get('grade')
        round_title = combo.get('round_title', '')
        
        for problem in combo.get('problems', []):
            prob_num = problem.get('num')
            text = problem.get('text', '')
            
            if any(word in text.lower() for word in keywords):
                tasks.append({
                    'combo_id': combo_id,
                    'olympiad': olympiad,
                    'olympiad_title': olympiad_title,
                    'year': year,
                    'grade': grade,
                    'round': round_title,
                    'prob_num': prob_num,
                    'text': text
                })
    
    # Сортируем по олимпиаде, году, классу
    tasks.sort(key=lambda x: (x['olympiad'], x['year'], x['grade'], x['prob_num']))
    return tasks


def generate_html():
    """Генерация HTML"""
    tasks = find_tasks_with_images()
    
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Hunter - 235 задач с рисунками</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1400px;
            margin: 20px auto;
            padding: 20px;
            background: #1a1a2e;
            color: #e0e0e0;
        }}
        h1 {{
            color: #00bcd4;
            text-align: center;
        }}
        .stats {{
            background: #2a2a3e;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 30px;
            text-align: center;
            font-size: 18px;
        }}
        .task-row {{
            background: #25252b;
            padding: 15px;
            margin: 10px 0;
            border-radius: 6px;
            border-left: 3px solid #00bcd4;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .task-info {{
            flex: 1;
        }}
        .task-meta {{
            color: #00bcd4;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .task-text {{
            color: #ccc;
            font-size: 14px;
        }}
        .archive-btn {{
            padding: 10px 20px;
            background: #d32f2f;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-weight: bold;
            white-space: nowrap;
        }}
        .archive-btn:hover {{
            background: #b71c1c;
        }}
    </style>
</head>
<body>
    <h1>🎯 Image Hunter</h1>
    
    <div class="stats">
        Всего задач с рисунками: {task_count}
    </div>
"""
    
    # Генерируем строки для каждой задачи
    for i, task in enumerate(tasks, 1):
        archive_url = get_archive_url(task['olympiad'], task['year'], task['grade'])
        text_preview = task['text'][:100].replace('\n', ' ')
        
        html += f"""
    <div class="task-row">
        <div class="task-info">
            <div class="task-meta">
                [{i}] {task['olympiad_title']} {task['year']}, класс {task['grade']}, {task['round']}, Задача {task['prob_num']}
            </div>
            <div class="task-text">
                {text_preview}...
            </div>
        </div>
        <a href="{archive_url}" target="_blank" class="archive-btn">
            📄 Архив
        </a>
    </div>
"""
    
    html += """
</body>
</html>
"""
    
    return html.replace('{task_count}', str(len(tasks)))


def main():
    """Главная функция"""
    print("="*70)
    print("ГЕНЕРАЦИЯ IMAGE_HUNTER.HTML - СПИСОК ВСЕХ ЗАДАЧ")
    print("="*70)
    
    html = generate_html()
    
    output_file = "IMAGE_HUNTER.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    import os
    full_path = os.path.abspath(output_file)
    
    print(f"\n[OK] Файл создан: {full_path}")
    print(f"\nОткройте в браузере:")
    print(f"  file:///{full_path}")
    print("\n" + "="*70)


if __name__ == "__main__":
    main()
