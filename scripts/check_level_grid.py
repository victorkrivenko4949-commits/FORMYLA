"""Show how the DB is filled across the full grid (grade × ui_topic × level).

Target: every cell should have at least --target tasks (default 25).
For each (grade, topic) prints a row with counts per level 1..7 and the deficit.
"""
import argparse, os, sqlite3, sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from services.adaptive_topic_mapping import get_keywords_for_grade_topic  # noqa: E402

UI_TOPICS = ["algebra", "geometry", "combinatorics",
             "number_theory", "movement", "knights_liars"]
GRADES = [5, 6, 7, 8, 9, 10, 11]
LEVELS = [1, 2, 3, 4, 5, 6, 7]

FALLBACK = {
    "algebra": ["алгебра", "выражения", "одночлен", "многочлен", "формул"],
    "geometry": ["геометрия", "треугольник", "четырехугольник", "окружность",
                 "вектор", "площад", "стереометр", "многогранник",
                 "тела вращения", "объем"],
    "combinatorics": ["комбинатор", "вероятност", "перестановк", "размещен", "сочетан"],
    "number_theory": ["натуральн", "делимост", "положительн", "отрицательн",
                      "рациональн", "числ", "НОД", "НОК"],
    "movement": ["движен", "текстовые задачи", "совместная работа"],
    "knights_liars": ["рыцар", "лжец"],
}


def kws(g, t):
    k = get_keywords_for_grade_topic(g, t)
    return [x.lower() for x in (k or FALLBACK.get(t, []))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=25)
    ap.add_argument("--db", default=os.path.join("instance", "formyla.db"))
    args = ap.parse_args()

    conn = sqlite3.connect(args.db); cur = conn.cursor()
    rows = cur.execute(
        "SELECT class_level, difficulty_level, topic FROM adaptive_tasks WHERE is_flagged=0"
    ).fetchall()
    print(f"DB tasks: {len(rows)}; target per cell = {args.target}\n")

    # Index: by class -> list of (level, topic_str)
    by_class: dict[int, list] = {}
    for c, d, t in rows:
        by_class.setdefault(int(c or 0), []).append((int(d or 0), (t or "").lower()))

    print(f"{'Cls':>3} {'Topic':<14}  L1   L2   L3   L4   L5   L6   L7  | total  deficit")
    print("-" * 75)
    grand_have = 0
    grand_need = 0
    cells_done = 0
    cells_total = len(GRADES) * len(UI_TOPICS) * len(LEVELS)
    for g in GRADES:
        all_t = by_class.get(g, [])
        for ui in UI_TOPICS:
            kw = kws(g, ui)
            counts = [0] * 8  # index 1..7
            for lvl, tstr in all_t:
                if lvl < 1 or lvl > 7:
                    continue
                if any(k in tstr for k in kw):
                    counts[lvl] += 1
            cell_total = sum(counts[1:])
            grand_have += cell_total
            cell_need = sum(max(0, args.target - counts[l]) for l in LEVELS)
            grand_need += cell_need
            cells_done += sum(1 for l in LEVELS if counts[l] >= args.target)
            cells_str = "  ".join(f"{counts[l]:>3}" for l in LEVELS)
            print(f"{g:>3} {ui:<14} {cells_str} | {cell_total:>5}  {cell_need:>5}")
        print()

    target_total = cells_total * args.target
    print(f"Grand total (have / target): {grand_have} / {target_total}")
    print(f"Cells fully filled: {cells_done} / {cells_total}")
    print(f"Tasks needed to reach target: {grand_need}")


if __name__ == "__main__":
    main()
