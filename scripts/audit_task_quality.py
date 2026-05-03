#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit: verify every task matches its assigned topic/category and grade level.
Checks all 9773 tasks in local SQLite for mismatches.

Categories (6 canonical topics):
  1. Algebra     - algebra, equations, functions, expressions
  2. Geometry    - triangles, circles, areas, angles
  3. Number Theory - divisibility, primes, GCD, LCM
  4. Combinatorics - counting, probability, permutations
  5. Movement    - speed, distance, time, trains, bikes
  6. Knights & Liars - logic puzzles with truth-tellers and liars
"""

import sys
import io
import sqlite3
import os
import re
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

LOCAL_DB = os.path.join(os.path.dirname(__file__), '..', 'instance', 'formyla.db')

# ---- Topic detection keywords (applied to task_text) ----

# Each canonical topic has keywords that SHOULD appear in the task text
TOPIC_VALIDATORS = {
    'movement': {
        'positive': [
            'скорост', 'км/ч', 'м/с', 'движен', 'навстречу', 'поезд', 'велосипед',
            'автомобил', 'пешеход', 'катер', 'лодк', 'расстояни', 'путь', 'время в пути',
            'догон', 'обгон', 'течени', 'по реке', 'против течен', 'мотоцикл',
            'автобус', 'самолет', 'вертолет', 'машин', 'ехал', 'шел ', 'шёл',
            'проехал', 'прошел', 'прошёл', 'проплыл', 'пролетел', 'выехал',
            'вышел', 'отправил', 'прибыл', 'доехал', 'добрал', 'маршрут',
            'из пункта', 'из города', 'из точки А', 'пункт А', 'пункт Б',
            'одновременно выш', 'одновременно выех', 'встретил',
            'совместн', 'работ', 'бассейн', 'наполн', 'труб', 'кран',
            'покрас', 'выполн', 'производительн'
        ],
        'negative': [
            'рыцар', 'лжец', 'правд', 'лож', 'остров'
        ]
    },
    'knights_liars': {
        'positive': [
            'рыцар', 'лжец', 'правд', 'лож', 'остров', 'житель',
            'всегда говор', 'всегда лж', 'истин', 'ложн',
            'сказал правду', 'сказал ложь', 'говорит правду', 'говорит ложь',
            'племя', 'туземц', 'абориген'
        ],
        'negative': [
            'скорост', 'км/ч', 'движен', 'треугольник', 'окружност'
        ]
    },
    'algebra': {
        'positive': [
            'уравнен', 'неравенств', 'выражен', 'формул', 'многочлен',
            'одночлен', 'корн', 'степен', 'логарифм', 'функци', 'график',
            'парабол', 'тригонометр', 'производн', 'интеграл', 'систем',
            'дроб', 'процент', 'пропорц', 'прогресс', 'последовательн',
            'вычисл', 'упрост', 'разлож', 'факториз', 'тождеств',
            'модуль', 'абсолютн', 'квадратн', 'линейн', 'показательн',
            'арифметик', 'сумм', 'произведен', 'разност'
        ],
        'negative': []
    },
    'geometry': {
        'positive': [
            'треугольник', 'четырехугольник', 'окружност', 'круг', 'площад',
            'периметр', 'угол', 'градус', 'вектор', 'координат', 'прямоугольн',
            'параллелограмм', 'ромб', 'трапеци', 'квадрат', 'диагонал',
            'медиан', 'биссектрис', 'высот', 'вписан', 'описан', 'касательн',
            'хорд', 'дуг', 'сектор', 'сегмент', 'подоб', 'конгруэнт',
            'симметри', 'отражен', 'поворот', 'параллельн', 'перпендикуляр',
            'теорем', 'пифагор', 'стереометр', 'многогранник', 'призм',
            'пирамид', 'конус', 'цилиндр', 'сфер', 'объем', 'геометр',
            'клетчат', 'разрезан', 'замощен', 'фигур'
        ],
        'negative': []
    },
    'number_theory': {
        'positive': [
            'делимост', 'делител', 'кратн', 'остаток', 'НОД', 'НОК',
            'простое число', 'простых чисел', 'составно', 'разложен',
            'факторизац', 'цифр', 'последняя цифра', 'сумма цифр',
            'натуральн', 'целое число', 'целых чисел', 'четн', 'нечетн',
            'чётн', 'нечётн', 'модул', 'сравнен', 'диофантов',
            'ребус', 'крипторифм'
        ],
        'negative': []
    },
    'combinatorics': {
        'positive': [
            'комбинатор', 'перестановк', 'размещен', 'сочетан', 'вероятност',
            'подсчет', 'подсчёт', 'сколько способ', 'сколько вариант',
            'правило суммы', 'правило произведен', 'биномиальн', 'Паскал',
            'принцип включен', 'принцип Дирихле', 'раскраск', 'шахматн',
            'турнир', 'граф', 'дерев', 'путь в граф', 'маршрут',
            'инвариант', 'четност', 'чередован', 'взвешиван', 'переливан',
            'алгоритм', 'стратеги', 'игр'
        ],
        'negative': []
    }
}

# Map DB topic names to canonical categories
def classify_topic(topic_name):
    """Map a DB topic name to one of 6 canonical categories."""
    t = topic_name.lower()
    
    # Movement
    if any(kw in t for kw in ['движен', 'скорост', 'текстовые задачи']):
        return 'movement'
    
    # Knights & Liars
    if any(kw in t for kw in ['рыцар', 'лжец']):
        return 'knights_liars'
    
    # Geometry
    if any(kw in t for kw in ['геометр', 'треугольник', 'четырехугольник', 'окружност',
                               'площад', 'периметр', 'стереометр', 'многогранник',
                               'вектор', 'координат', 'разрезан', 'замощен', 'клетчат']):
        return 'geometry'
    
    # Number Theory
    if any(kw in t for kw in ['делимост', 'остатк', 'НОД', 'НОК', 'натуральн',
                               'теория чисел', 'ребус', 'крипторифм', 'цифр',
                               'простых', 'простое']):
        return 'number_theory'
    
    # Combinatorics
    if any(kw in t for kw in ['комбинатор', 'вероятност', 'перестановк', 'размещен',
                               'сочетан', 'принцип Дирихле', 'принцип дирихле',
                               'инвариант', 'четност', 'чередован', 'взвешиван',
                               'переливан', 'граф', 'турнир', 'раскраск',
                               'стратеги', 'игр']):
        return 'combinatorics'
    
    # Algebra (catch-all for math topics)
    if any(kw in t for kw in ['алгебр', 'уравнен', 'неравенств', 'выражен', 'функци',
                               'график', 'многочлен', 'степен', 'логарифм', 'корн',
                               'дроб', 'процент', 'пропорц', 'прогресс', 'тождеств',
                               'тригонометр', 'производн', 'интеграл', 'систем',
                               'линейн', 'квадратн', 'показательн', 'модуль']):
        return 'algebra'
    
    # Fallback: check broader patterns
    if any(kw in t for kw in ['логик', 'логическ']):
        return 'knights_liars'  # logic often maps to knights_liars
    
    if any(kw in t for kw in ['числ', 'арифметик']):
        return 'number_theory'
    
    if any(kw in t for kw in ['математик', 'олимпиад', 'задач']):
        return 'algebra'  # generic math -> algebra
    
    return 'unknown'


def check_task_content(task_text, expected_category):
    """Check if task_text content matches the expected category."""
    if not task_text:
        return False, "empty task text"
    
    text_lower = task_text.lower()
    validator = TOPIC_VALIDATORS.get(expected_category)
    
    if not validator:
        return True, "no validator for category"
    
    # Check positive keywords
    positive_hits = [kw for kw in validator['positive'] if kw.lower() in text_lower]
    negative_hits = [kw for kw in validator['negative'] if kw.lower() in text_lower]
    
    if positive_hits:
        if negative_hits and not positive_hits:
            return False, f"has negative keywords: {negative_hits}"
        return True, f"matched: {positive_hits[:3]}"
    
    # No positive keywords found - suspicious
    return False, f"no topic keywords found in text"


def check_grade_appropriateness(task_text, grade):
    """Basic check if task complexity seems appropriate for grade."""
    if not task_text:
        return True, "empty"
    
    text_lower = task_text.lower()
    
    # Grade 5-6: should not have advanced topics
    if grade <= 6:
        advanced = ['производн', 'интеграл', 'логарифм', 'тригонометр',
                     'комплексн', 'предел', 'бесконечн']
        hits = [kw for kw in advanced if kw in text_lower]
        if hits:
            return False, f"too advanced for grade {grade}: {hits}"
    
    # Grade 10-11: should not be trivially simple
    if grade >= 10:
        trivial = ['сколько будет', 'посчитай', '2+2', '3+3']
        hits = [kw for kw in trivial if kw in text_lower]
        if hits:
            return False, f"too simple for grade {grade}: {hits}"
    
    return True, "ok"


def main():
    print("=" * 70)
    print("TASK QUALITY AUDIT")
    print("Checking all tasks match their topic, category, and grade")
    print("=" * 70)
    
    conn = sqlite3.connect(os.path.abspath(LOCAL_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"\nTotal tasks: {total}")
    
    # Fetch all tasks
    cur.execute("""
        SELECT id, class_level, difficulty_level, topic, task_text, correct_answer, is_flagged
        FROM adaptive_tasks
        ORDER BY topic, class_level, id
    """)
    tasks = cur.fetchall()
    
    # Audit results
    mismatches = []
    grade_issues = []
    empty_tasks = []
    no_answer = []
    stats = {
        'total': 0,
        'topic_ok': 0,
        'topic_mismatch': 0,
        'grade_ok': 0,
        'grade_issue': 0,
        'empty': 0,
        'no_answer': 0,
        'already_flagged': 0
    }
    
    # Per-category stats
    category_stats = {}
    
    for task in tasks:
        stats['total'] += 1
        task_id = task['id']
        grade = task['class_level']
        topic = task['topic'] or ''
        text = task['task_text'] or ''
        answer = task['correct_answer'] or ''
        flagged = task['is_flagged']
        
        if flagged:
            stats['already_flagged'] += 1
        
        # Classify topic
        category = classify_topic(topic)
        
        if category not in category_stats:
            category_stats[category] = {'total': 0, 'ok': 0, 'mismatch': 0, 'mismatched_ids': []}
        category_stats[category]['total'] += 1
        
        # Check empty
        if not text.strip() or len(text.strip()) < 10:
            stats['empty'] += 1
            empty_tasks.append({
                'id': task_id, 'grade': grade, 'topic': topic,
                'text': text[:100]
            })
            continue
        
        # Check no answer
        if not answer.strip():
            stats['no_answer'] += 1
            no_answer.append({
                'id': task_id, 'grade': grade, 'topic': topic,
                'text': text[:80]
            })
        
        # Check topic match
        ok, reason = check_task_content(text, category)
        if ok:
            stats['topic_ok'] += 1
            category_stats[category]['ok'] += 1
        else:
            stats['topic_mismatch'] += 1
            category_stats[category]['mismatch'] += 1
            category_stats[category]['mismatched_ids'].append(task_id)
            mismatches.append({
                'id': task_id, 'grade': grade, 'topic': topic,
                'category': category, 'reason': reason,
                'text': text[:150]
            })
        
        # Check grade appropriateness
        grade_ok, grade_reason = check_grade_appropriateness(text, grade)
        if grade_ok:
            stats['grade_ok'] += 1
        else:
            stats['grade_issue'] += 1
            grade_issues.append({
                'id': task_id, 'grade': grade, 'topic': topic,
                'reason': grade_reason, 'text': text[:150]
            })
    
    # ---- REPORT ----
    report = []
    report.append("\n" + "=" * 70)
    report.append("AUDIT RESULTS")
    report.append("=" * 70)
    report.append(f"\nTotal tasks audited: {stats['total']}")
    report.append(f"Already flagged: {stats['already_flagged']}")
    report.append(f"\nTopic match: {stats['topic_ok']} OK, {stats['topic_mismatch']} MISMATCH")
    report.append(f"Grade level: {stats['grade_ok']} OK, {stats['grade_issue']} ISSUES")
    report.append(f"Empty tasks: {stats['empty']}")
    report.append(f"No answer: {stats['no_answer']}")
    
    report.append(f"\n{'=' * 70}")
    report.append("PER-CATEGORY BREAKDOWN")
    report.append(f"{'=' * 70}")
    for cat in sorted(category_stats.keys()):
        s = category_stats[cat]
        pct = (s['ok'] / s['total'] * 100) if s['total'] > 0 else 0
        report.append(f"\n  {cat}: {s['total']} tasks, {s['ok']} OK ({pct:.1f}%), {s['mismatch']} mismatch")
        if s['mismatched_ids'][:10]:
            report.append(f"    Sample mismatch IDs: {s['mismatched_ids'][:10]}")
    
    if mismatches:
        report.append(f"\n{'=' * 70}")
        report.append(f"TOPIC MISMATCHES (first 30)")
        report.append(f"{'=' * 70}")
        for m in mismatches[:30]:
            report.append(f"\n  ID {m['id']} | Grade {m['grade']} | Topic: {m['topic']}")
            report.append(f"  Category: {m['category']} | Reason: {m['reason']}")
            report.append(f"  Text: {m['text']}")
    
    if grade_issues:
        report.append(f"\n{'=' * 70}")
        report.append(f"GRADE LEVEL ISSUES (first 20)")
        report.append(f"{'=' * 70}")
        for g in grade_issues[:20]:
            report.append(f"\n  ID {g['id']} | Grade {g['grade']} | Topic: {g['topic']}")
            report.append(f"  Reason: {g['reason']}")
            report.append(f"  Text: {g['text']}")
    
    if empty_tasks:
        report.append(f"\n{'=' * 70}")
        report.append(f"EMPTY TASKS ({len(empty_tasks)})")
        report.append(f"{'=' * 70}")
        for e in empty_tasks[:10]:
            report.append(f"  ID {e['id']} | Grade {e['grade']} | Topic: {e['topic']} | Text: '{e['text']}'")
    
    # Print and save
    report_text = '\n'.join(report)
    print(report_text)
    
    # Save full report
    report_path = os.path.join(os.path.dirname(__file__), '..', 'data', '_audit_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
        
        # Also save full mismatch list as JSON
        f.write(f"\n\n{'=' * 70}\n")
        f.write(f"ALL MISMATCHES ({len(mismatches)} total)\n")
        f.write(f"{'=' * 70}\n")
        for m in mismatches:
            f.write(f"\nID {m['id']} | Grade {m['grade']} | {m['topic']} -> {m['category']}\n")
            f.write(f"  Reason: {m['reason']}\n")
            f.write(f"  Text: {m['text']}\n")
    
    # Save mismatches as JSON for further processing
    json_path = os.path.join(os.path.dirname(__file__), '..', 'data', '_audit_mismatches.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'stats': stats,
            'category_stats': {k: {'total': v['total'], 'ok': v['ok'], 'mismatch': v['mismatch']} 
                              for k, v in category_stats.items()},
            'mismatches': mismatches,
            'grade_issues': grade_issues,
            'empty_tasks': empty_tasks,
            'no_answer': no_answer[:50]
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\nReport saved to: {os.path.abspath(report_path)}")
    print(f"Mismatches JSON: {os.path.abspath(json_path)}")
    
    conn.close()


if __name__ == '__main__':
    main()
