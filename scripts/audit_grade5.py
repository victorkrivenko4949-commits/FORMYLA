#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Аудит задач 5 класса в adaptive_tasks (Render Postgres)."""
import os, json, psycopg2
from collections import defaultdict

DB_URL = os.environ.get(
    'DATABASE_URL',
    os.environ.get('EXTERNAL_DATABASE_URL',
        'postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe'
        '@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com'
        '/formyla?sslmode=require'
    )
)

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

cur.execute("""
    SELECT topic, difficulty_level, COUNT(*)
    FROM adaptive_tasks
    WHERE class_level = 5
      AND (is_flagged IS NULL OR is_flagged = false)
    GROUP BY topic, difficulty_level
    ORDER BY topic, difficulty_level
""")

data = defaultdict(lambda: defaultdict(int))
for topic, diff, cnt in cur.fetchall():
    data[topic][diff] = cnt

TARGET = 175

print("=" * 100)
print("АУДИТ 5 КЛАССА — adaptive_tasks (Render Postgres)")
print("=" * 100)

header = f"{'Тема':<55} | {'L1':>3} | {'L2':>3} | {'L3':>3} | {'L4':>3} | {'L5':>3} | {'L6':>3} | {'L7':>3} | {'Всего':>5} | {'Дефицит':>7}"
print(header)
print("-" * len(header))

report = []
grand_total = 0
grand_deficit = 0

for topic in sorted(data.keys()):
    levels = data[topic]
    total = sum(levels.values())
    deficit = max(0, TARGET - total)
    grand_total += total
    grand_deficit += deficit
    row = {
        "topic": topic,
        "levels": {str(k): v for k, v in levels.items()},
        "total": total,
        "deficit": deficit,
    }
    report.append(row)
    vals = [levels.get(i, 0) for i in range(1, 8)]
    print(f"{topic:<55} | {vals[0]:>3} | {vals[1]:>3} | {vals[2]:>3} | {vals[3]:>3} | {vals[4]:>3} | {vals[5]:>3} | {vals[6]:>3} | {total:>5} | {deficit:>7}")

print("-" * len(header))
print(f"{'ИТОГО':<55} | {'':>3} | {'':>3} | {'':>3} | {'':>3} | {'':>3} | {'':>3} | {'':>3} | {grand_total:>5} | {grand_deficit:>7}")
print()
print(f"Всего задач 5 класса: {grand_total}")
print(f"Тем: {len(data)}")
print(f"Суммарный дефицит до {TARGET}/тему: {grand_deficit}")

# Сохраняем JSON
os.makedirs("data/audit", exist_ok=True)
out = {
    "grade": 5,
    "target_per_topic": TARGET,
    "total_tasks": grand_total,
    "total_topics": len(data),
    "total_deficit": grand_deficit,
    "topics": report,
}
with open("data/audit/grade5_distribution.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\nJSON сохранён: data/audit/grade5_distribution.json")

conn.close()
