# -*- coding: utf-8 -*-
import sqlite3
db = sqlite3.connect('instance/formyla.db')

sets = db.execute("""
    SELECT dts.id, dts.status, dts.triggered_by, dts.generated_at
    FROM daily_task_sets dts
    WHERE dts.status = 'ready'
    ORDER BY dts.id DESC LIMIT 5
""").fetchall()

for s in sets:
    set_id = s[0]
    items = db.execute("""
        SELECT position, task_text, correct_answer, difficulty_level,
               status, topic, subtopic
        FROM daily_task_items
        WHERE daily_set_id = ?
        ORDER BY position
    """, (set_id,)).fetchall()
    
    print(f"=== Set #{set_id} status={s[1]} time={s[3]} === ({len(items)} tasks)")
    for pos, txt, ans, lvl, st, topic, sub in items:
        topic_str = (topic or '?')[:25]
        sub_str = (sub or '?')[:25]
        txt_str = (txt or 'N/A').replace('\n', ' ')[:130]
        ans_str = (ans or '?')[:50]
        print(f"  [{pos}] L{lvl} {st} | {topic_str} / {sub_str}")
        print(f"       {txt_str}")
        print(f"       => {ans_str}")
        print()
    print()

db.close()
