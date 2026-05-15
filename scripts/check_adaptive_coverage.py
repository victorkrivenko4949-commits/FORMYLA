"""Check coverage of (grade, topic) combinations against the live SQLite DB,
using exactly the same keyword logic as app.adaptive_test_start_simple()."""
import os, sqlite3, sys
sys.path.insert(0, os.getcwd())
from services.adaptive_topic_mapping import TOPIC_KEYWORDS_BY_GRADE  # noqa

# fallback dictionary (mirrors app.py:3851)
FALLBACK = {
    'algebra': ['алгебра','выражения','одночлен','многочлен','формул'],
    'geometry': ['геометрия','треугольник','четырехугольник','окружность','вектор',
                 'площад','стереометр','многогранник','тела вращения','объем'],
    'combinatorics': ['комбинатор','вероятност','перестановк','размещен','сочетан'],
    'number_theory': ['натуральн','делимост','положительн','отрицательн','рациональн',
                      'числ','НОД','НОК'],
    'movement': ['движен','текстовые задачи','совместная работа'],
    'knights_liars': ['рыцар','лжец'],
}

UI_TOPICS = ['algebra','geometry','combinatorics','number_theory','movement','knights_liars']
GRADES = [5,6,7,8,9,10,11]
THRESHOLD = 10

def keywords_for(grade, topic):
    kw = TOPIC_KEYWORDS_BY_GRADE.get(grade, {}).get(topic, [])
    return kw if kw else FALLBACK.get(topic, [])

def main():
    db = os.path.join("instance","formyla.db")
    conn = sqlite3.connect(db); cur = conn.cursor()
    rows = cur.execute(
        "SELECT class_level, topic FROM adaptive_tasks WHERE is_flagged=0"
    ).fetchall()
    print(f"Loaded {len(rows)} non-flagged adaptive tasks from DB\n")

    by_class = {}
    for c, t in rows:
        by_class.setdefault(c, []).append(t or "")

    print(f"{'Grade':>6} {'Topic':<16} {'Tasks':>6}  Status")
    print("-"*46)
    bad = []
    for g in GRADES:
        all_t = by_class.get(g, [])
        for ui in UI_TOPICS:
            kws = [k.lower() for k in keywords_for(g, ui)]
            if not kws:
                n = 0
            else:
                n = sum(1 for t in all_t if any(k in t.lower() for k in kws))
            status = "OK" if n >= THRESHOLD else ("EMPTY" if n == 0 else "LOW")
            print(f"{g:>6} {ui:<16} {n:>6}  {status}")
            if n < THRESHOLD:
                bad.append((g, ui, n))
        print()

    print(f"Combinations below threshold {THRESHOLD}: {len(bad)} / {len(GRADES)*len(UI_TOPICS)}")

if __name__ == "__main__":
    main()
