#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create generation plan for any grade. Usage: python scripts/gen_plan_any_grade.py <grade>"""
import json, os, sys, psycopg2

DB_URL = (os.environ.get('DATABASE_URL') or
          os.environ.get('EXTERNAL_DATABASE_URL') or
          'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
          '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
          '/formyla?sslmode=require')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/gen_plan_any_grade.py <grade>")
        sys.exit(1)

    grade = int(sys.argv[1])
    audit_dir = os.path.join(BASE_DIR, 'data', 'audit')
    os.makedirs(audit_dir, exist_ok=True)

    # Query current distribution
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        'SELECT topic, difficulty_level, COUNT(*) FROM adaptive_tasks '
        'WHERE class_level=%s GROUP BY topic, difficulty_level '
        'ORDER BY topic, difficulty_level', (grade,))
    rows = cur.fetchall()

    # Save audit
    audit = [{'topic': r[0], 'level': r[1], 'count': r[2]} for r in rows]
    audit_file = os.path.join(audit_dir, f'grade{grade}_audit.json')
    json.dump(audit, open(audit_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    # Get unique topics
    topics = sorted(set(r[0] for r in rows))
    total_existing = sum(r[2] for r in rows)
    print(f'Grade {grade}: {len(topics)} topics, {total_existing} existing tasks')

    for t in topics:
        counts = {r[1]: r[2] for r in rows if r[0] == t}
        total = sum(counts.values())
        print(f'  {t}: {total} (L1:{counts.get(1,0)} L2:{counts.get(2,0)} L3:{counts.get(3,0)} L4:{counts.get(4,0)} L5:{counts.get(5,0)})')

    # Target: ~1050 tasks total
    # Strategy: 14 tasks per level per topic (L1-L5 = 70 per topic)
    TARGET_PER_LEVEL = 14
    plan = []
    for t in topics:
        counts = {r[1]: r[2] for r in rows if r[0] == t}
        for lvl in range(1, 6):
            have = counts.get(lvl, 0)
            gen = max(0, TARGET_PER_LEVEL - have)
            if gen > 0:
                plan.append({'topic': t, 'difficulty': lvl, 'count': gen, 'priority': 1})

    total_plan = sum(p['count'] for p in plan)
    plan_file = os.path.join(audit_dir, f'grade{grade}_gen_plan.json')
    json.dump(plan, open(plan_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'\nPlan: {len(plan)} items, {total_plan} tasks to generate')
    print(f'After generation: {total_existing + total_plan} total tasks')
    print(f'Saved to {plan_file}')

    conn.close()

if __name__ == '__main__':
    main()
