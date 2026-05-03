#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reclassify movement tasks in the adaptive_tasks table on Render PostgreSQL.
Finds tasks with movement keywords in task_text and updates their topic to "Задачи на движение".
"""
import sys
import re
import psycopg2

sys.stdout.reconfigure(encoding='utf-8')

DB_URL = "postgresql://formyla_user:HwFVHpWWNFZzLvB1m6aXAKfeijKLqtGe@dpg-d7n8uo0g4nts73b1n9k0-a.ohio-postgres.render.com/formyla?sslmode=require"

# Movement keywords regex — must match at least 2 to avoid false positives
MOVEMENT_RE = re.compile(
    r'скорост|км/ч|м/с|навстречу|вдогонку|'
    r'из\s+пункта|из\s+города|выехал|отправил|'
    r'расстояни\w+\s+между|весь\s+путь|половин\w+\s+пути|'
    r'по\s+течени|против\s+течени|собственн\w+\s+скорост|'
    r'велосипедист|пешеход|мотоциклист|катер\w*\s+плыв|лодк|'
    r'поезд\w*\s+\w*\s*выех|автобус\w*\s+\w*\s*выех|'
    r'движ\w+\s+навстречу|движ\w+\s+в\s+одном\s+направлен|'
    r'встретил\w+\s+через|время\s+в\s+пути|'
    r'догнал|обгон',
    re.IGNORECASE
)

NEW_TOPIC = "Задачи на движение"


def main():
    print("Connecting to Render PostgreSQL...")
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # Step 1: Get current stats
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"Total tasks in DB: {total}")

    cur.execute("SELECT topic, COUNT(*) FROM adaptive_tasks WHERE topic = %s GROUP BY topic", (NEW_TOPIC,))
    existing = cur.fetchone()
    print(f"Already tagged as '{NEW_TOPIC}': {existing[1] if existing else 0}")

    # Step 2: Fetch all tasks and find movement ones
    cur.execute("SELECT id, class_level, topic, task_text FROM adaptive_tasks WHERE topic != %s", (NEW_TOPIC,))
    rows = cur.fetchall()
    print(f"Tasks to scan: {len(rows)}")

    to_update = []
    for row in rows:
        task_id, grade, topic, text = row
        if not text:
            continue
        matches = MOVEMENT_RE.findall(text)
        if len(matches) >= 2:  # At least 2 movement keywords
            to_update.append((task_id, grade, topic))

    print(f"\nFound {len(to_update)} movement tasks to reclassify")

    # Stats by grade
    by_grade = {}
    for _, grade, _ in to_update:
        by_grade[grade] = by_grade.get(grade, 0) + 1
    print("\nBy grade:")
    for g in sorted(by_grade.keys()):
        print(f"  Grade {g}: {by_grade[g]}")

    # Stats by old topic
    by_topic = {}
    for _, _, topic in to_update:
        by_topic[topic] = by_topic.get(topic, 0) + 1
    print("\nBy old topic:")
    for tp, c in sorted(by_topic.items(), key=lambda x: -x[1]):
        print(f"  {tp}: {c}")

    if not to_update:
        print("\nNothing to update!")
        conn.close()
        return

    # Step 3: Update
    print(f"\nUpdating {len(to_update)} tasks...")
    ids = [t[0] for t in to_update]

    # Batch update
    cur.execute(
        "UPDATE adaptive_tasks SET topic = %s WHERE id = ANY(%s)",
        (NEW_TOPIC, ids)
    )
    updated = cur.rowcount
    conn.commit()
    print(f"Updated: {updated} rows")

    # Step 4: Verify
    cur.execute(
        "SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE topic = %s GROUP BY class_level ORDER BY class_level",
        (NEW_TOPIC,)
    )
    print(f"\nVerification — '{NEW_TOPIC}' by grade:")
    for row in cur.fetchall():
        print(f"  Grade {row[0]}: {row[1]}")

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE topic = %s", (NEW_TOPIC,))
    final = cur.fetchone()[0]
    print(f"\nTotal '{NEW_TOPIC}': {final}")

    conn.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
