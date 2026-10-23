#!/usr/bin/env python
"""Этап 1-2: Инвентаризация всех файлов и пересчёт фактов."""
import json, os, sys
from collections import Counter, defaultdict


def compute_quality_score(task):
    """Compute quality score for a generated task (mirrors _stage8_quality_audit.py:22)."""
    sol = task.get('solution', task.get('solution_text', ''))
    stmt = task.get('text', task.get('statement', task.get('task_text', '')))

    # solution_completeness (0.30)
    sol_len = len(sol.strip()) if sol else 0
    sol_completeness = min(1.0, sol_len / 500) if sol_len > 0 else 0.0

    # statement_clarity (0.25)
    stmt_len = len(stmt.strip()) if stmt else 0
    statement_clarity = min(1.0, stmt_len / 200) if stmt_len > 0 else 0.0

    # subtopic_relevance (0.20) - default 0.7 for generated
    subtopic_relevance = 0.7

    # difficulty_confidence (0.15) - no has_valid_solution for generated tasks
    has_valid = task.get('has_valid_solution', task.get('solution_verified', False))
    difficulty_confidence = 0.9 if has_valid else 0.5

    # source_quality (0.10)
    olympiad = task.get('_olympiad', task.get('olympiad', ''))
    if olympiad in ('vsosh', 'region', 'final'):
        source_quality = 1.0
    elif olympiad in ('euler', 'kysh', 'turloomath'):
        source_quality = 0.9
    elif olympiad in ('mos', 'spb', 'mipt'):
        source_quality = 0.8
    elif olympiad:
        source_quality = 0.7
    else:
        source_quality = 0.5

    score = (0.30 * sol_completeness +
             0.25 * statement_clarity +
             0.20 * subtopic_relevance +
             0.15 * difficulty_confidence +
             0.10 * source_quality)
    return round(score * 100, 1)


WORK_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WORK_DIR)

files = {
    "curated_bank_L1_L5_fixed": os.path.join(ROOT, "curated_bank_L1_L5_fixed.json"),
    "curated_bank_L4_L5_filled": os.path.join(ROOT, "l4_l5_fill_output", "curated_bank_L4_L5_filled.json"),
    "stage6_generated": os.path.join(ROOT, "l4_l5_completion_work", "stage6_generated_tasks.json"),
    "VICTOR2.0": os.path.join(ROOT, "VICTOR2.0"),
    "stage8_report": os.path.join(ROOT, "l4_l5_completion_work", "stage8_quality_report.txt"),
    "fill_audit": os.path.join(ROOT, "l4_l5_fill_output", "fill_audit.json"),
}

print("=" * 70)
print("  ЭТАП 1-2: ИНВЕНТАРИЗАЦИЯ И ПЕРЕСЧЁТ ФАКТОВ")
print("=" * 70)

data = {}
for name, path in files.items():
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    print(f"\n  [{name}]")
    print(f"    Путь: {path}")
    print(f"    Существует: {exists}")
    print(f"    Размер: {size} байт")
    if exists:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if path.endswith('.json'):
                    d = json.load(f)
                    data[name] = d
                    if isinstance(d, list):
                        print(f"    Записей: {len(d)}")
                    elif isinstance(d, dict):
                        print(f"    Ключи верхнего уровня: {list(d.keys())[:10]}")
                else:
                    content = f.read()
                    data[name] = content
                    print(f"    Строк: {len(content.splitlines())}")
        except Exception as e:
            print(f"    ОШИБКА ЧТЕНИЯ: {e}")

# ---- Анализ curated_bank_L1_L5_fixed ----
if "curated_bank_L1_L5_fixed" in data:
    cb = data["curated_bank_L1_L5_fixed"]
    print("\n" + "-" * 60)
    print("  АНАЛИЗ: curated_bank_L1_L5_fixed.json")
    print("-" * 60)

    levels = Counter()
    grades = Counter()
    cell_keys = Counter()
    topics = Counter()
    subtopics = Counter()
    empty_stmts = 0
    empty_answers = 0
    empty_solutions = 0
    task_ids = set()
    stmt_hashes = set()

    for t in cb:
        lvl = str(t.get("level", "?"))
        gr = str(t.get("grade", "?"))
        ck = str(t.get("cell_key", "?"))
        tp = str(t.get("theme_name", t.get("topic", "?")))[:40]
        st = str(t.get("subtopic", "?"))[:40]

        levels[lvl] += 1
        grades[gr] += 1
        cell_keys[ck] += 1
        topics[tp] += 1
        subtopics[st] += 1

        tid = t.get("task_id", t.get("id", ""))
        if tid:
            task_ids.add(str(tid))

        stmt = t.get("statement", "")
        if stmt:
            stmt_hashes.add(stmt.strip()[:100])
        else:
            empty_stmts += 1

        if not t.get("answer", ""):
            empty_answers += 1
        if not t.get("solution", ""):
            empty_solutions += 1

    print(f"  Всего задач: {len(cb)}")
    print(f"  Уникальных task_id: {len(task_ids)}")
    print(f"  Уникальных cell_keys: {len(cell_keys)}")
    print(f"  Пустых statement: {empty_stmts}")
    print(f"  Пустых answer: {empty_answers}")
    print(f"  Пустых solution: {empty_solutions}")
    print(f"  Распределение по уровням: {dict(levels)}")
    print(f"  Распределение по классам: {dict(grades)}")

    # Cell distribution
    cell_counts = Counter(cell_keys.values())
    print(f"  Распределение задач по ячейкам: {dict(sorted(cell_counts.items()))}")
    print(f"  Ячеек ровно с 5 задачами: {sum(1 for v in cell_keys.values() if v == 5)}")
    print(f"  Ячеек <5: {sum(1 for v in cell_keys.values() if v < 5)}")
    print(f"  Ячеек >5: {sum(1 for v in cell_keys.values() if v > 5)}")

    incomplete = {k: v for k, v in cell_keys.items() if v != 5}
    print(f"  Неполные ячейки (>0 и <5): {len(incomplete)}")
    for k in sorted(incomplete)[:20]:
        print(f"    {k}: {incomplete[k]}")

# ---- Анализ generated tasks ----
if "stage6_generated" in data:
    gen = data["stage6_generated"]
    print("\n" + "-" * 60)
    print("  АНАЛИЗ: stage6_generated_tasks.json")
    print("-" * 60)

    levels_g = Counter()
    grades_g = Counter()
    cell_keys_g = Counter()
    quality_scores = []
    below_60 = 0
    between_60_70 = 0
    above_70 = 0
    task_ids_g = set()
    stmt_hashes_g = set()

    for t in gen:
        lvl = str(t.get("level", "?"))
        gr = str(t.get("grade", "?"))
        ck = str(t.get("cell_key", "?"))
        # FIX: compute quality score properly instead of reading non-existent field
        qs = compute_quality_score(t)

        levels_g[lvl] += 1
        grades_g[gr] += 1
        cell_keys_g[ck] += 1
        quality_scores.append(qs)

        if qs < 60:
            below_60 += 1
        elif qs < 70:
            between_60_70 += 1
        else:
            above_70 += 1

        tid = t.get("task_id", "")
        if tid:
            task_ids_g.add(str(tid))

        stmt = t.get("statement", "")
        if stmt:
            stmt_hashes_g.add(stmt.strip()[:100])

    print(f"  Всего задач: {len(gen)}")
    print(f"  Уникальных task_id: {len(task_ids_g)}")
    print(f"  Уникальных cell_keys: {len(cell_keys_g)}")
    print(f"  Уровни: {dict(levels_g)}")
    print(f"  Классы: {dict(grades_g)}")
    print(f"  Quality scores (correctly computed via compute_quality_score()):")
    print(f"    < 60: {below_60}")
    print(f"    60-69.99: {between_60_70}")
    print(f"    >= 70: {above_70}")

    if quality_scores:
        print(f"    Средний: {sum(quality_scores)/len(quality_scores):.1f}")
        print(f"    Мин: {min(quality_scores):.1f}")
        print(f"    Макс: {max(quality_scores):.1f}")

    # List weak tasks
    print(f"\n  Задачи с quality_score < 60:")
    for t in gen:
        qs = compute_quality_score(t)
        if qs < 60:
            print(f"    task_id={t.get('task_id','?')}, cell={t.get('cell_key','?')}, qs={qs:.1f}")
            print(f"      statement: {str(t.get('statement',''))[:100]}...")

    print(f"\n  Задачи с quality_score 60-69.99:")
    weak_60_70 = [(compute_quality_score(t), t) for t in gen]
    weak_60_70.sort(key=lambda x: x[0])
    for qs, t in weak_60_70:
        if 60 <= qs < 70:
            print(f"    task_id={t.get('task_id','?')}, cell={t.get('cell_key','?')}, qs={qs:.1f}")
            print(f"      statement: {str(t.get('statement',''))[:100]}...")

    # Cell distribution in generated
    print(f"\n  Распределение по ячейкам (generated):")
    cell_counts_g = Counter(cell_keys_g.values())
    print(f"    {dict(sorted(cell_counts_g.items()))}")
    for ck, cnt in sorted(cell_keys_g.items()):
        print(f"    {ck}: {cnt} задач")

    # Find cells with avg quality < 60 or < 70
    cell_qualities = defaultdict(list)
    for t in gen:
        ck = str(t.get("cell_key", "?"))
        qs = compute_quality_score(t)
        cell_qualities[ck].append(qs)

    print(f"\n  Ячейки со средним quality < 60:")
    for ck, scores in sorted(cell_qualities.items()):
        avg = sum(scores) / len(scores)
        if avg < 60:
            print(f"    {ck}: avg={avg:.1f}, scores={[f'{s:.1f}' for s in scores]}")

    print(f"\n  Ячейки со средним quality 60-70:")
    for ck, scores in sorted(cell_qualities.items()):
        avg = sum(scores) / len(scores)
        if 60 <= avg < 70:
            print(f"    {ck}: avg={avg:.1f}, scores={[f'{s:.1f}' for s in scores]}")

# ---- Analysis of VICTOR2.0 ----
if "VICTOR2.0" in data:
    v = data["VICTOR2.0"]
    print("\n" + "-" * 60)
    print("  АНАЛИЗ: VICTOR2.0")
    print("-" * 60)
    if isinstance(v, list):
        print(f"  Тип: список, {len(v)} записей")
        if v:
            print(f"  Ключи первой записи: {list(v[0].keys()) if isinstance(v[0], dict) else 'не dict'}")
    elif isinstance(v, dict):
        print(f"  Тип: словарь, ключи: {list(v.keys())[:10]}")
    else:
        print(f"  Тип: {type(v).__name__}")

# ---- Analysis of filled bank ----
if "curated_bank_L4_L5_filled" in data:
    fb = data["curated_bank_L4_L5_filled"]
    print("\n" + "-" * 60)
    print("  АНАЛИЗ: curated_bank_L4_L5_filled.json")
    print("-" * 60)

    cell_keys_f = Counter()
    levels_f = Counter()

    for t in fb:
        ck = str(t.get("cell_key", "?"))
        cell_keys_f[ck] += 1
        levels_f[str(t.get("level", "?"))] += 1

    print(f"  Всего задач: {len(fb)}")
    print(f"  Уникальных cell_keys: {len(cell_keys_f)}")
    print(f"  Уровни: {dict(levels_f)}")

    cell_counts_f = Counter(cell_keys_f.values())
    print(f"  Распределение задач по ячейкам: {dict(sorted(cell_counts_f.items()))}")
    print(f"  Ячеек ровно с 5 задачами: {sum(1 for v in cell_keys_f.values() if v == 5)}")
    print(f"  Ячеек <5: {sum(1 for v in cell_keys_f.values() if v < 5)}")
    print(f"  Ячеек >5: {sum(1 for v in cell_keys_f.values() if v > 5)}")

    # List under-filled cells
    under_filled = {}
    for t in fb:
        ck = str(t.get("cell_key", "?"))
        if cell_keys_f[ck] < 5:
            under_filled[ck] = cell_keys_f[ck]
    if under_filled:
        print(f"\n  Ячейки <5 задач:")
        for ck in sorted(under_filled):
            print(f"    {ck}: {under_filled[ck]}")

# Create backup
print("\n" + "-" * 60)
print("  СОЗДАНИЕ РЕЗЕРВНЫХ КОПИЙ")
print("-" * 60)

backup_dir = os.path.join(WORK_DIR, "backups")
os.makedirs(backup_dir, exist_ok=True)

for name, path in files.items():
    if os.path.exists(path):
        import shutil
        backup_path = os.path.join(backup_dir, os.path.basename(path))
        shutil.copy2(path, backup_path)
        print(f"  {name} -> {backup_path}")

print("\n" + "=" * 70)
print("  ИНВЕНТАРИЗАЦИЯ ЗАВЕРШЕНА")
print("=" * 70)
