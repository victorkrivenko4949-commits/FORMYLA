#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Обрезка 7 класса до 1050 задач.
Удаляет худшие задачи по приоритету:
  1. Точные дубли по task_text
  2. Близкие дубли (нормализованный хэш)
  3. Битый LaTeX
  4. Пустой answer или короткое условие (<30 символов)
  5. Выравнивание матрицы тема x сложность (срезаем самые раздутые ячейки)

Запуск:
  python scripts/trim_grade7_to_1050.py           # DRY-RUN
  python scripts/trim_grade7_to_1050.py --commit   # ПРИМЕНИТЬ
"""

import sys
import io
import sqlite3
import json
import re
import hashlib
import os
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"
TARGET = 1050
GRADE = 7
COMMIT = '--commit' in sys.argv
BACKUP_FILE = "scripts/trim_grade7_backup.json"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print(f"ОБРЕЗКА 7 КЛАССА ДО {TARGET} ЗАДАЧ")
print(f"Режим: {'COMMIT (реальное удаление)' if COMMIT else 'DRY-RUN (только анализ)'}")
print("=" * 70)

# Загружаем все задачи 7 класса
cur.execute("""
    SELECT id, topic, difficulty_level, task_text, correct_answer, solution,
           created_at, llm_quality_score, is_flagged
    FROM adaptive_tasks
    WHERE class_level = ?
    ORDER BY id
""", (GRADE,))
all_tasks = [dict(row) for row in cur.fetchall()]
total_before = len(all_tasks)
need_to_delete = max(0, total_before - TARGET)

print(f"\nВсего задач 7 класса: {total_before}")
print(f"Цель: {TARGET}")
print(f"Нужно удалить: {need_to_delete}")

if total_before <= TARGET:
    print(f"\nУже <= {TARGET} задач. Ничего удалять не нужно.")
    conn.close()
    sys.exit(0)

# Множество ID для удаления + причины
to_delete = {}  # id -> reason


def enough():
    """Проверяем, набрали ли уже достаточно для удаления."""
    return len(to_delete) >= need_to_delete


# ─── ЭТАП 1: Точные дубли по task_text ─────────────────────────────────────
print(f"\n{'─'*70}")
print(f"[ЭТАП 1] Точные дубли по task_text")
seen_texts = {}
exact_dupes = []
for task in all_tasks:
    text = (task['task_text'] or '').strip()
    if text in seen_texts:
        exact_dupes.append(task['id'])
        to_delete[task['id']] = 'exact_duplicate'
    else:
        seen_texts[text] = task['id']

print(f"  Найдено точных дублей: {len(exact_dupes)}")
if exact_dupes[:5]:
    print(f"  Примеры ID: {exact_dupes[:5]}")
print(f"  Итого к удалению после этапа 1: {len(to_delete)}")


# ─── ЭТАП 2: Близкие дубли (нормализованный хэш) ──────────────────────────
print(f"\n{'─'*70}")
print(f"[ЭТАП 2] Близкие дубли (нормализованный хэш)")


def normalize_text(text):
    """Нормализация текста для поиска near-duplicates."""
    if not text:
        return ""
    t = text.lower().strip()
    # Убираем все пробелы, переносы, знаки препинания
    t = re.sub(r'\s+', '', t)
    # Убираем LaTeX-обёртки
    t = re.sub(r'\\[a-zA-Z]+', '', t)
    t = re.sub(r'[{}\[\]()$\\]', '', t)
    # Убираем пунктуацию
    t = re.sub(r'[.,;:!?«»""\'—–\-]', '', t)
    return t


def text_hash(text):
    """MD5 хэш нормализованного текста."""
    normalized = normalize_text(text)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()


seen_hashes = {}
near_dupes = []
for task in all_tasks:
    if task['id'] in to_delete:
        continue
    h = text_hash(task['task_text'])
    if h in seen_hashes:
        near_dupes.append(task['id'])
        to_delete[task['id']] = 'near_duplicate'
    else:
        seen_hashes[h] = task['id']

print(f"  Найдено близких дублей: {len(near_dupes)}")
if near_dupes[:5]:
    print(f"  Примеры ID: {near_dupes[:5]}")
print(f"  Итого к удалению после этапа 2: {len(to_delete)}")


# ─── ЭТАП 3: Битый LaTeX ──────────────────────────────────────────────────
print(f"\n{'─'*70}")
print(f"[ЭТАП 3] Битый LaTeX")

BROKEN_LATEX_PATTERNS = [
    r'\$ *rac\{',           # $ rac{ (потерянный \f)
    r'\\frac\s*\{[^}]*$',  # незакрытый \frac
    r'\$[^$]*\{[^}]*$',    # незакрытая фигурная скобка в $...$
    r'\\\\[a-z]',           # двойной бэкслэш перед командой
    r'\$\s*\$',             # пустые $$ 
]

broken_latex = []
for task in all_tasks:
    if task['id'] in to_delete:
        continue
    text = task['task_text'] or ''
    is_broken = False
    
    # Проверка: непарные $
    dollar_count = text.count('$')
    if dollar_count % 2 != 0:
        is_broken = True
    
    # Проверка паттернов
    if not is_broken:
        for pattern in BROKEN_LATEX_PATTERNS:
            if re.search(pattern, text):
                is_broken = True
                break
    
    # Проверка: непарные фигурные скобки
    if not is_broken:
        open_braces = text.count('{')
        close_braces = text.count('}')
        if open_braces != close_braces and (open_braces > 0 or close_braces > 0):
            is_broken = True
    
    if is_broken:
        broken_latex.append(task['id'])
        to_delete[task['id']] = 'broken_latex'

print(f"  Найдено с битым LaTeX: {len(broken_latex)}")
if broken_latex[:5]:
    print(f"  Примеры ID: {broken_latex[:5]}")
print(f"  Итого к удалению после этапа 3: {len(to_delete)}")


# ─── ЭТАП 4: Пустой answer или короткое условие (<30 символов) ─────────────
print(f"\n{'─'*70}")
print(f"[ЭТАП 4] Пустой answer / короткое условие (<30 символов)")

short_or_empty = []
for task in all_tasks:
    if task['id'] in to_delete:
        continue
    
    answer = (task['correct_answer'] or '').strip()
    text = (task['task_text'] or '').strip()
    
    bad = False
    reason_detail = ''
    
    if not answer:
        bad = True
        reason_detail = 'empty_answer'
    elif len(text) < 30:
        bad = True
        reason_detail = f'short_text({len(text)}ch)'
    
    if bad:
        short_or_empty.append(task['id'])
        to_delete[task['id']] = reason_detail

print(f"  Найдено пустых/коротких: {len(short_or_empty)}")
if short_or_empty[:5]:
    print(f"  Примеры ID: {short_or_empty[:5]}")
print(f"  Итого к удалению после этапа 4: {len(to_delete)}")


# ─── ЭТАП 5: Выравнивание матрицы тема x сложность ─────────────────────────
print(f"\n{'─'*70}")
print(f"[ЭТАП 5] Выравнивание матрицы (срезаем раздутые ячейки)")

# Считаем, сколько ещё нужно удалить
still_need = need_to_delete - len(to_delete)
print(f"  Уже набрано к удалению: {len(to_delete)}")
print(f"  Ещё нужно удалить: {max(0, still_need)}")

if still_need > 0:
    # Строим матрицу оставшихся задач (не помеченных к удалению)
    remaining = [t for t in all_tasks if t['id'] not in to_delete]
    remaining_count = len(remaining)
    
    # Считаем ячейки
    cell_tasks = defaultdict(list)  # (topic, diff) -> [task_ids]
    for task in remaining:
        key = (task['topic'], task['difficulty_level'])
        cell_tasks[key].append(task)
    
    num_cells = len(cell_tasks)
    target_per_cell = max(1, TARGET // max(num_cells, 1))
    
    print(f"  Оставшихся задач: {remaining_count}")
    print(f"  Уникальных ячеек (тема x сложность): {num_cells}")
    print(f"  Целевое кол-во на ячейку: ~{target_per_cell}")
    
    # Сортируем ячейки по размеру (от самых раздутых)
    cells_sorted = sorted(cell_tasks.items(), key=lambda x: -len(x[1]))
    
    # Показываем топ-10 раздутых ячеек
    print(f"\n  Топ-10 раздутых ячеек:")
    for (topic, diff), tasks in cells_sorted[:10]:
        excess = len(tasks) - target_per_cell
        print(f"    {topic[:40]:<40} diff={diff}  count={len(tasks):>4}  excess={excess:>+4}")
    
    # Срезаем лишние из раздутых ячеек
    # Приоритет удаления внутри ячейки:
    #   1. is_flagged = 1
    #   2. llm_quality_score самый низкий (NULL = 0)
    #   3. Самый новый ID (сгенерированные позже — менее проверенные)
    matrix_trimmed = []
    
    for (topic, diff), tasks in cells_sorted:
        if still_need <= 0:
            break
        
        excess = len(tasks) - target_per_cell
        if excess <= 0:
            continue
        
        # Сколько реально срезаем из этой ячейки
        trim_count = min(excess, still_need)
        
        # Сортируем задачи по "качеству" (худшие первые)
        def sort_key(t):
            flagged = 1 if t.get('is_flagged') else 0
            quality = t.get('llm_quality_score') or 0.0
            return (-flagged, quality, -t['id'])  # flagged first, then low quality, then newest
        
        tasks_sorted = sorted(tasks, key=sort_key)
        
        for t in tasks_sorted[:trim_count]:
            to_delete[t['id']] = f'matrix_trim({topic[:20]},d={diff})'
            matrix_trimmed.append(t['id'])
            still_need -= 1
    
    print(f"\n  Удалено на этапе 5 (матрица): {len(matrix_trimmed)}")
    if matrix_trimmed[:5]:
        print(f"  Примеры ID: {matrix_trimmed[:5]}")
else:
    print(f"  Этап 5 не нужен — уже набрано достаточно.")

print(f"\n  Итого к удалению после этапа 5: {len(to_delete)}")


# ─── ИТОГОВАЯ СТАТИСТИКА ──────────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"ИТОГО")
print(f"{'='*70}")

# Подсчёт по причинам
reasons = defaultdict(int)
for task_id, reason in to_delete.items():
    # Группируем matrix_trim в одну категорию
    if reason.startswith('matrix_trim'):
        reasons['matrix_trim'] += 1
    elif reason.startswith('short_text'):
        reasons['short_text'] += 1
    else:
        reasons[reason] += 1

print(f"\n  Всего задач до:    {total_before}")
print(f"  К удалению:        {len(to_delete)}")
print(f"  Останется:         {total_before - len(to_delete)}")
print(f"\n  По причинам:")
for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
    print(f"    {reason:<25} {count:>5}")


# ─── РАСПРЕДЕЛЕНИЕ ПОСЛЕ ОБРЕЗКИ ──────────────────────────────────────────
print(f"\n{'─'*70}")
print(f"РАСПРЕДЕЛЕНИЕ ПОСЛЕ ОБРЕЗКИ (прогноз)")
print(f"{'─'*70}")

remaining_tasks = [t for t in all_tasks if t['id'] not in to_delete]

# По темам
topic_counts = defaultdict(int)
for t in remaining_tasks:
    topic_counts[t['topic']] += 1

print(f"\n  По темам:")
for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
    print(f"    {topic:<45} {count:>4}")

# По сложностям
diff_counts = defaultdict(int)
for t in remaining_tasks:
    diff_counts[t['difficulty_level']] += 1

print(f"\n  По сложностям:")
for diff in sorted(diff_counts.keys()):
    print(f"    Сложность {diff}: {diff_counts[diff]:>4}")

# Матрица тема x сложность
print(f"\n  Матрица тема x сложность (после обрезки):")
all_diffs = sorted(set(t['difficulty_level'] for t in remaining_tasks))
all_topics = sorted(set(t['topic'] for t in remaining_tasks))

# Заголовок
header = f"  {'Тема':<40}"
for d in all_diffs:
    header += f" d={d:>2}"
header += "  ИТОГО"
print(header)
print(f"  {'─'*40}" + "─────" * len(all_diffs) + "───────")

matrix = defaultdict(int)
for t in remaining_tasks:
    matrix[(t['topic'], t['difficulty_level'])] += 1

for topic in all_topics:
    row = f"  {topic[:40]:<40}"
    row_total = 0
    for d in all_diffs:
        c = matrix.get((topic, d), 0)
        row += f" {c:>4}"
        row_total += c
    row += f"  {row_total:>5}"
    print(row)

# Итого по сложностям
total_row = f"  {'ИТОГО':<40}"
for d in all_diffs:
    col_total = sum(matrix.get((topic, d), 0) for topic in all_topics)
    total_row += f" {col_total:>4}"
total_row += f"  {len(remaining_tasks):>5}"
print(f"  {'─'*40}" + "─────" * len(all_diffs) + "───────")
print(total_row)


# ─── БЭКАП И УДАЛЕНИЕ ─────────────────────────────────────────────────────
print(f"\n{'='*70}")

if COMMIT:
    # Сохраняем бэкап удалённых ID
    backup_data = {
        'timestamp': datetime.now().isoformat(),
        'grade': GRADE,
        'total_before': total_before,
        'total_deleted': len(to_delete),
        'total_after': total_before - len(to_delete),
        'deleted_ids': {str(k): v for k, v in to_delete.items()}
    }
    
    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    print(f"Бэкап сохранён: {BACKUP_FILE}")
    
    # Удаляем задачи
    delete_ids = list(to_delete.keys())
    batch_size = 100
    deleted_total = 0
    
    for i in range(0, len(delete_ids), batch_size):
        batch = delete_ids[i:i+batch_size]
        placeholders = ','.join('?' * len(batch))
        cur.execute(f"DELETE FROM adaptive_tasks WHERE id IN ({placeholders})", batch)
        deleted_total += cur.rowcount
    
    conn.commit()
    print(f"УДАЛЕНО: {deleted_total} задач")
    
    # Проверяем результат
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level = ?", (GRADE,))
    final_count = cur.fetchone()[0]
    print(f"Задач 7 класса после обрезки: {final_count}")
    
    if final_count != total_before - len(to_delete):
        print(f"⚠️  ВНИМАНИЕ: ожидалось {total_before - len(to_delete)}, получилось {final_count}")
    else:
        print(f"✅ Всё совпадает!")
else:
    print(f"DRY-RUN: ничего не удалено.")
    print(f"Для применения запустите:")
    print(f"  python scripts/trim_grade7_to_1050.py --commit")

conn.close()
print(f"\n{'='*70}")
print("Готово!")
