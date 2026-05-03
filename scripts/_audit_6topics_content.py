#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Focused audit: check tasks that appear in each of the 6 adaptive test topics.
Simulates the exact same filtering logic as adaptive_test_start_simple().
"""
import sys, io, json, sqlite3, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Import the topic mapping
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from services.adaptive_topic_mapping import get_keywords_for_grade_topic

LOCAL_DB = os.path.join(os.path.dirname(__file__), '..', 'instance', 'formyla.db')

# Same topic_keywords as in app.py adaptive_test_start_simple()
BASE_KEYWORDS = {
    'algebra': ['алгебра', 'выражения', 'одночлен', 'многочлен', 'формул'],
    'geometry': ['геометрия', 'треугольник', 'четырехугольник', 'окружность', 'вектор',
                 'площад', 'стереометр', 'многогранник', 'тела вращения', 'объем'],
    'combinatorics': ['комбинатор', 'вероятност', 'перестановк', 'размещен', 'сочетан'],
    'number_theory': ['натуральн', 'делимост', 'положительн', 'отрицательн', 'рациональн',
                      'числ', 'НОД', 'НОК'],
    'movement': ['движен', 'текстовые задачи', 'совместная работа'],
    'knights_liars': ['рыцар', 'лжец', 'логика']
}

# Content validators - keywords that SHOULD appear in task text for each topic
CONTENT_VALIDATORS = {
    'movement': [
        'скорост', 'км/ч', 'м/с', 'движен', 'навстречу', 'поезд', 'велосипед',
        'автомобил', 'пешеход', 'катер', 'лодк', 'расстояни', 'путь',
        'догон', 'обгон', 'течени', 'по реке', 'мотоцикл', 'автобус',
        'ехал', 'шел', 'шёл', 'проехал', 'прошел', 'прошёл', 'выехал',
        'вышел', 'прибыл', 'доехал', 'из пункта', 'из города',
        'одновременно', 'встретил', 'совместн', 'работ', 'бассейн',
        'наполн', 'труб', 'кран', 'покрас', 'производительн',
        'вместе', 'отдельно', 'быстрее', 'медленнее', 'за час',
        'за минут', 'за день', 'часов', 'минут'
    ],
    'knights_liars': [
        'рыцар', 'лжец', 'правд', 'лож', 'остров', 'житель',
        'всегда говор', 'всегда лж', 'истин', 'ложн',
        'сказал правду', 'говорит правду', 'племя', 'туземц',
        'абориген', 'кто из них', 'кем является'
    ],
    'algebra': [
        'уравнен', 'неравенств', 'выражен', 'формул', 'многочлен',
        'корн', 'степен', 'логарифм', 'функци', 'график',
        'тригонометр', 'производн', 'интеграл', 'систем',
        'дроб', 'процент', 'пропорц', 'прогресс', 'последовательн',
        'вычисл', 'упрост', 'разлож', 'тождеств', 'модуль',
        'квадратн', 'линейн', 'показательн', 'арифметик',
        'сумм', 'произведен', 'разност', 'числ', 'найдите',
        'решите', 'докажите', 'определите', 'сколько'
    ],
    'geometry': [
        'треугольник', 'четырехугольник', 'окружност', 'круг', 'площад',
        'периметр', 'угол', 'градус', 'вектор', 'координат',
        'параллелограмм', 'ромб', 'трапеци', 'квадрат', 'диагонал',
        'медиан', 'биссектрис', 'высот', 'вписан', 'описан',
        'хорд', 'подоб', 'симметри', 'параллельн', 'перпендикуляр',
        'пифагор', 'многогранник', 'призм', 'пирамид', 'конус',
        'цилиндр', 'сфер', 'объем', 'геометр', 'клетчат',
        'разрезан', 'замощен', 'фигур', 'сторон', 'точк',
        'прямоугольн', 'отрезок', 'прямая', 'плоскост'
    ],
    'number_theory': [
        'делимост', 'делител', 'кратн', 'остаток', 'НОД', 'НОК',
        'простое', 'простых', 'составно', 'цифр', 'натуральн',
        'целое', 'целых', 'четн', 'нечетн', 'чётн', 'нечётн',
        'ребус', 'крипторифм', 'числ', 'разложен', 'факторизац'
    ],
    'combinatorics': [
        'комбинатор', 'перестановк', 'размещен', 'сочетан', 'вероятност',
        'сколько способ', 'сколько вариант', 'правило суммы',
        'принцип', 'Дирихле', 'раскраск', 'шахматн', 'турнир',
        'граф', 'дерев', 'маршрут', 'инвариант', 'четност',
        'взвешиван', 'переливан', 'алгоритм', 'стратеги', 'игр',
        'логик', 'логическ', 'доказ', 'опровер'
    ]
}

def main():
    conn = sqlite3.connect(os.path.abspath(LOCAL_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    results = {}
    wrong_tasks = []
    
    for topic_key in ['algebra', 'geometry', 'number_theory', 'combinatorics', 'movement', 'knights_liars']:
        results[topic_key] = {'total': 0, 'ok': 0, 'suspicious': 0, 'wrong': []}
        
        for grade in range(5, 12):
            # Get keywords exactly as app.py does
            keywords = list(BASE_KEYWORDS.get(topic_key, []))
            
            # Special case for grade 5 algebra
            if grade == 5 and topic_key == 'algebra':
                keywords = ['математик', 'числ', 'выражен', 'уравнен', 'задач',
                           'вычислен', 'арифметик', 'олимпиад']
            
            # Override with grade-specific keywords
            grade_kw = get_keywords_for_grade_topic(grade, topic_key)
            if grade_kw:
                keywords = grade_kw
            
            if not keywords:
                continue
            
            # Fetch tasks for this grade
            cur.execute(
                "SELECT id, class_level, topic, task_text, correct_answer FROM adaptive_tasks WHERE class_level = ? AND is_flagged = 0",
                (grade,)
            )
            all_tasks = cur.fetchall()
            
            # Filter by topic keywords (same as app.py)
            filtered = []
            for task in all_tasks:
                topic_lower = (task['topic'] or '').lower()
                if any(kw.lower() in topic_lower for kw in keywords):
                    filtered.append(task)
            
            # Now check each filtered task's CONTENT
            validator_kws = CONTENT_VALIDATORS.get(topic_key, [])
            
            for task in filtered:
                results[topic_key]['total'] += 1
                text = (task['task_text'] or '').lower()
                
                if not validator_kws:
                    results[topic_key]['ok'] += 1
                    continue
                
                # Check if task text contains at least one content keyword
                has_match = any(kw.lower() in text for kw in validator_kws)
                
                if has_match:
                    results[topic_key]['ok'] += 1
                else:
                    results[topic_key]['suspicious'] += 1
                    wrong_tasks.append({
                        'id': task['id'],
                        'grade': task['class_level'],
                        'topic_key': topic_key,
                        'db_topic': task['topic'],
                        'text': (task['task_text'] or '')[:200],
                        'answer': task['correct_answer']
                    })
    
    # Print results
    print("=" * 70)
    print("ADAPTIVE TEST CONTENT AUDIT")
    print("Simulates exact filtering from adaptive_test_start_simple()")
    print("=" * 70)
    
    total_all = 0
    ok_all = 0
    sus_all = 0
    
    for topic_key in ['algebra', 'geometry', 'number_theory', 'combinatorics', 'movement', 'knights_liars']:
        r = results[topic_key]
        total_all += r['total']
        ok_all += r['ok']
        sus_all += r['suspicious']
        pct = (r['ok'] / r['total'] * 100) if r['total'] > 0 else 0
        status = "OK" if r['suspicious'] == 0 else f"!! {r['suspicious']} suspicious"
        print(f"\n  {topic_key:20s}: {r['total']:5d} tasks | {r['ok']:5d} OK ({pct:.1f}%) | {status}")
    
    print(f"\n  {'TOTAL':20s}: {total_all:5d} tasks | {ok_all:5d} OK | {sus_all} suspicious")
    
    # Show suspicious tasks grouped by topic
    for topic_key in ['movement', 'knights_liars', 'algebra', 'geometry', 'number_theory', 'combinatorics']:
        topic_wrong = [w for w in wrong_tasks if w['topic_key'] == topic_key]
        if topic_wrong:
            print(f"\n{'=' * 70}")
            print(f"SUSPICIOUS TASKS in {topic_key.upper()} ({len(topic_wrong)}):")
            print(f"{'=' * 70}")
            for w in topic_wrong[:15]:
                print(f"\n  ID {w['id']} | Grade {w['grade']} | DB topic: {w['db_topic']}")
                print(f"  Answer: {w['answer']}")
                print(f"  Text: {w['text']}")
    
    # Save results
    out_path = os.path.join(os.path.dirname(__file__), '..', 'data', '_audit_6topics_content.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {k: {'total': v['total'], 'ok': v['ok'], 'suspicious': v['suspicious']} 
                       for k, v in results.items()},
            'wrong_tasks': wrong_tasks
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\nSaved to: {os.path.abspath(out_path)}")
    conn.close()

if __name__ == '__main__':
    main()
