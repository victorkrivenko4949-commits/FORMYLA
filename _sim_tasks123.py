# -*- coding: utf-8 -*-
"""
Tasks 1-3 simulation: direct DB-based task assignment.
Distributes across levels proportionally - 2 tasks/level/day for 5 levels.
"""
import sqlite3, random, time, json
from collections import defaultdict, Counter
from datetime import date, timedelta

DB_PATH = r'c:\Users\Redmi\Desktop\Новая папка (2)\instance\formyla.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def load_tasks(conn, grade=None):
    if grade:
        cur = conn.execute(
            'SELECT id, class_level, difficulty_level, topic, subtopic, subject, task_text '
            'FROM adaptive_tasks WHERE class_level = ?', (grade,))
    else:
        cur = conn.execute(
            'SELECT id, class_level, difficulty_level, topic, subtopic, subject, task_text '
            'FROM adaptive_tasks')
    return [dict(r) for r in cur.fetchall()]

def simulate_student(tasks_by_level, norm, days, student_id, rng):
    seen_ids = set()
    day_sizes = []
    repeat_count = 0
    empty_sets = 0
    level_dist = Counter()
    topic_dist = Counter()
    first_short_day = None

    levels_sorted = sorted(tasks_by_level.keys())
    n_levels = len(levels_sorted)

    for day in range(1, days + 1):
        assigned = []
        per_level = norm // n_levels
        extra = norm - per_level * n_levels

        for idx, lvl in enumerate(levels_sorted):
            target = per_level + (1 if idx < extra else 0)
            tlist = tasks_by_level[lvl]
            available = [t for t in tlist
                         if t['id'] not in seen_ids
                         and t['id'] not in {a['id'] for a in assigned}]
            rng.shuffle(available)
            taken = available[:target]

            if len(taken) < target:
                for other_lvl in levels_sorted:
                    if len(taken) >= target:
                        break
                    if other_lvl == lvl:
                        continue
                    other_tasks = tasks_by_level[other_lvl]
                    pool = [t for t in other_tasks
                            if t['id'] not in seen_ids
                            and t['id'] not in {a['id'] for a in assigned}
                            and t['id'] not in {a['id'] for a in taken}]
                    rng.shuffle(pool)
                    taken.extend(pool[:target - len(taken)])

            for t in taken:
                if t['id'] in seen_ids:
                    repeat_count += 1
                seen_ids.add(t['id'])
                assigned.append(t)
                level_dist[t['difficulty_level']] += 1
                topic_dist[t.get('topic', '?')] += 1

        day_sizes.append(len(assigned))
        if len(assigned) < norm:
            empty_sets += 1
            if first_short_day is None:
                first_short_day = day

    return {
        'assignments': sum(day_sizes),
        'repeat_count': repeat_count,
        'empty_sets': empty_sets,
        'level_dist': dict(level_dist),
        'topic_dist': dict(topic_dist),
        'first_short_day': first_short_day,
        'days_with_short': sum(1 for n in day_sizes if n < norm),
    }

def task1():
    print("=" * 70)
    print("TASK 1: 100 students x 30 days x norm 10, grade 9")
    print("=" * 70)
    conn = get_db()
    all_tasks = load_tasks(conn, grade=9)
    conn.close()

    tasks_by_level = defaultdict(list)
    for t in all_tasks:
        tasks_by_level[t['difficulty_level']].append(t)

    print(f"\nGrade 9 tasks: {len(all_tasks)}")
    for lvl in sorted(tasks_by_level):
        print(f"  Level {lvl}: {len(tasks_by_level[lvl])}")

    rng = random.Random(42)
    t0 = time.time()
    results = [simulate_student(tasks_by_level, norm=10, days=30, student_id=i, rng=rng)
               for i in range(100)]
    elapsed = time.time() - t0

    total_assignments = sum(r['assignments'] for r in results)
    total_repeats = sum(r['repeat_count'] for r in results)
    total_empty = sum(r['empty_sets'] for r in results)

    level_dist = Counter()
    for r in results:
        for lvl, cnt in r['level_dist'].items():
            level_dist[lvl] += cnt

    topic_dist = Counter()
    for r in results:
        for topic, cnt in r['topic_dist'].items():
            topic_dist[topic] += cnt

    short_students = [r for r in results if r['days_with_short'] > 0]
    short_days = [r['first_short_day'] for r in short_students if r['first_short_day']]

    # Track cross-student task usage
    rng2 = random.Random(42)
    task_usage = Counter()
    for i in range(100):
        seen = set()
        levels_sorted = sorted(tasks_by_level.keys())
        n_levels = len(levels_sorted)
        for day in range(30):
            assigned = set()
            per_level = 10 // n_levels
            extra = 10 - per_level * n_levels
            for idx, lvl in enumerate(levels_sorted):
                target = per_level + (1 if idx < extra else 0)
                tlist = tasks_by_level[lvl]
                available = [t for t in tlist
                             if t['id'] not in seen and t['id'] not in assigned]
                rng2.shuffle(available)
                for t in available[:target]:
                    seen.add(t['id'])
                    assigned.add(t['id'])
                    task_usage[t['id']] += 1

    usage_counts = list(task_usage.values())
    avg_usage = sum(usage_counts) / len(usage_counts) if usage_counts else 0
    max_usage = max(usage_counts) if usage_counts else 0

    print(f"\n--- RESULTS ---")
    print(f"Total assignments: {total_assignments}")
    print(f"Total repeats (same student): {total_repeats}")
    print(f"Total empty sets: {total_empty}")
    print(f"Level distribution:")
    for lvl in sorted(level_dist):
        print(f"  L{lvl}: {level_dist[lvl]}")
    print(f"Topic distribution (top 10):")
    for topic, cnt in topic_dist.most_common(10):
        print(f"  {(topic or 'None')[:60]}: {cnt}")
    print(f"Students with short days: {len(short_students)}/100")
    if short_days:
        day_dist = Counter(short_days)
        print(f"First short day distribution:")
        for d in sorted(day_dist):
            print(f"  Day {d}: {day_dist[d]} students")
    print(f"Avg task usage across students: {avg_usage:.2f}")
    print(f"Max task usage across students: {max_usage}")
    print(f"Run time: {elapsed:.2f}s")
    return locals()

def task2():
    print("\n" + "=" * 70)
    print("TASK 2: 20 students per grade x 14 days, grades 5-11 (no 9)")
    print("=" * 70)
    conn = get_db()
    rng = random.Random(123)
    grades = [5, 6, 7, 8, 10, 11]
    results = {}
    for grade in grades:
        tasks = load_tasks(conn, grade=grade)
        tasks_by_level = defaultdict(list)
        for t in tasks:
            tasks_by_level[t['difficulty_level']].append(t)
        gr = [simulate_student(tasks_by_level, norm=10, days=14, student_id=i, rng=rng)
              for i in range(20)]
        total = sum(r['assignments'] for r in gr)
        avg_set = total / (20 * 14)
        empty = sum(r['empty_sets'] for r in gr)
        shorts = [r for r in gr if r['days_with_short'] > 0]
        sd = [r['first_short_day'] for r in shorts if r['first_short_day']]
        first = min(sd) if sd else 'N/A'
        results[grade] = {
            'total_assignments': total, 'avg_set_size': avg_set,
            'total_empty': empty, 'first_short_day': first,
            'total_tasks_available': len(tasks),
        }
    conn.close()

    print(f"\n{'Grade':<8} {'Total':<10} {'Avg set':<10} {'Empty':<8} {'First short':<14} {'Available':<12}")
    print("-" * 65)
    for grade in grades:
        r = results[grade]
        print(f"{grade:<8} {r['total_assignments']:<10} {r['avg_set_size']:<10.2f} "
              f"{r['total_empty']:<8} {str(r['first_short_day']):<14} {r['total_tasks_available']:<12}")
    return results

def task3():
    print("\n" + "=" * 70)
    print("TASK 3: Volume rule test")
    print("=" * 70)
    conn = get_db()
    tasks = load_tasks(conn, grade=9)
    conn.close()
    tasks_by_level = defaultdict(list)
    for t in tasks:
        tasks_by_level[t['difficulty_level']].append(t)
    levels_sorted = sorted(tasks_by_level.keys())
    n_levels = len(levels_sorted)

    print(f"\nTotal grade 9 tasks: {len(tasks)}")
    print(f"By level: { {l: len(v) for l, v in sorted(tasks_by_level.items())} }")

    def run_volume_test(rng, norm_override=None):
        rng_local = random.Random(rng)
        seen = set()
        print(f"\n{'Day':<6} {'Set size':<10} {'By level':<40}")
        for day in range(1, 11):
            if day <= 7:
                target = 5
            else:
                target = 10 if norm_override is None else norm_override
            assigned = []
            per_level = target // n_levels
            extra = target - per_level * n_levels
            level_counts = {}
            for idx, lvl in enumerate(levels_sorted):
                goal = per_level + (1 if idx < extra else 0)
                tlist = tasks_by_level[lvl]
                available = [t for t in tlist if t['id'] not in seen
                             and t['id'] not in {a['id'] for a in assigned}]
                rng_local.shuffle(available)
                taken = available[:goal]
                for t in taken:
                    seen.add(t['id'])
                    assigned.append(t)
                level_counts[lvl] = len(taken)
            print(f"{day:<6} {len(assigned):<10} {str(level_counts):<40}")
        return len(seen)

    print(f"\n--- Norm=10 (days 1-7=5, days 8-10=10) ---")
    u1 = run_volume_test(777)
    print(f"\n--- Norm=15 (days 1-7=5, days 8-10=15) ---")
    u2 = run_volume_test(888, norm_override=15)
    print(f"\nUnique tasks (norm=10): {u1}")
    print(f"Unique tasks (norm=15): {u2}")

if __name__ == '__main__':
    task1()
    task2()
    task3()
    print("\nDone.")
