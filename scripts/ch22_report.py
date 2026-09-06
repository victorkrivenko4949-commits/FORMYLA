# -*- coding: utf-8 -*-
"""CH22 STEP 4: отчёт по пилоту."""
import csv
import json
import os
import shutil
import statistics
import sys
from collections import Counter, defaultdict

sys.stdout = sys.stdout

OUT = "output/ch22"


def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "0%"


def med(xs):
    return round(statistics.median(xs), 1) if xs else 0


def p95(xs):
    if not xs:
        return 0
    s = sorted(xs)
    return round(s[int(0.95 * (len(s) - 1))], 1)


def main():
    rows = list(csv.DictReader(open(os.path.join(OUT, "results.csv"), encoding="utf-8")))
    done = [r for r in rows if r["status"] == "done"]
    failed = [r for r in rows if r["status"] != "done"]

    by_style = defaultdict(lambda: Counter())
    for r in rows:
        by_style[r["solution_style"]][r["status"]] += 1

    aux_status = Counter(r.get("aux_status") or "" for r in rows)
    aux_fail = Counter()
    for r in rows:
        for c in (r.get("aux_fail_codes") or "").split(","):
            c = c.strip()
            if c:
                aux_fail[c] += 1

    err_codes = Counter(r.get("error_code") or "OTHER" for r in failed)
    lat = [float(r["total_latency_ms"]) for r in rows if r.get("total_latency_ms")]
    cost_all = sum(float(r["cost_usd"]) for r in rows)
    cost_done = [float(r["cost_usd"]) for r in done if r.get("cost_usd")]
    avg_cost = (sum(cost_done) / len(cost_done)) if cost_done else 0.0

    soft_warn = sum(1 for r in rows if (r.get("soft_warnings") or "").strip())

    # aux_status по style
    constructive_aux = Counter()
    analytic_aux = Counter()
    for r in rows:
        st = r["solution_style"]
        a = r.get("aux_status") or ""
        if st == "constructive":
            constructive_aux[a] += 1
        elif st in ("coordinate", "complex", "trig"):
            analytic_aux[a] += 1

    L = []
    A = L.append
    A("# CH22 — Отчёт пилота\n")
    A(f"- Обработано задач: **{len(rows)}** (done={len(done)}, failed={len(failed)}).")
    A(f"- Общая стоимость: **${cost_all:.4f}**.\n")

    A("## 1. done / failed по solution_style\n")
    A("| style | done | failed |")
    A("|---|---|---|")
    for s in sorted(by_style):
        A(f"| {s} | {by_style[s].get('done', 0)} | {by_style[s].get('failed', 0)} |")

    A("\n## 2. Распределение aux_status (все задачи)\n")
    A("| aux_status | count |")
    A("|---|---|")
    for k, v in aux_status.most_common():
        A(f"| {k or '(пусто)'} | {v} |")

    A("\n## 3. aux_status для constructive\n")
    A("| status | count | доля |")
    A("|---|---|---|")
    total_c = sum(constructive_aux.values())
    for k in ("AUX_BUILT", "AUX_ROLLED_BACK", "AUX_NOT_NEEDED", "AUX_PLAN_REJECTED", "AUX_BUILD_FAILED"):
        A(f"| {k} | {constructive_aux.get(k, 0)} | {pct(constructive_aux.get(k, 0), total_c)} |")

    A("\n## 4. aux_status для coordinate/complex/trig\n")
    A("| status | count | доля |")
    A("|---|---|---|")
    total_a = sum(analytic_aux.values())
    for k in ("AUX_NOT_NEEDED", "AUX_BUILT", "AUX_ROLLED_BACK", "AUX_PLAN_REJECTED", "AUX_BUILD_FAILED"):
        A(f"| {k} | {analytic_aux.get(k, 0)} | {pct(analytic_aux.get(k, 0), total_a)} |")

    A("\n## 5. Топ error_code и aux_fail_codes\n")
    A("| error_code | count |")
    A("|---|---|")
    for k, v in err_codes.most_common(15):
        A(f"| {k} | {v} |")
    A("\n| aux_fail_codes | count |")
    A("|---|---|")
    for k, v in aux_fail.most_common(15):
        A(f"| {k} | {v} |")

    A("\n## 6. Latency (ms)\n")
    A(f"- p50={med(lat)}, p95={p95(lat)}, max={max(lat) if lat else 0}")

    A("\n## 7. Стоимость\n")
    A(f"- Общая: ${cost_all:.4f}; средняя успешного: ${avg_cost:.4f}")

    A("\n## 8. Задачи с soft_warnings\n")
    A(f"- {soft_warn}")

    A("\n## 9. Прогноз на 354 задачи\n")
    avg_per = cost_all / len(rows) if rows else 0
    A(f"- Средняя стоимость задачи: ${avg_per:.4f}; прогноз 354: ${avg_per * 354:.2f}")
    avg_lat = sum(lat) / len(lat) if lat else 0
    A(f"- Средняя latency: {avg_lat:.0f} ms; прогноз времени (2 workers): {avg_lat / 1000 * 354 / 2 / 60:.0f} мин")

    A("\n## 10. Ручная выборка 15 задач с самым интересным aux\n")
    A("| task_uid | aux_status | aux_ops | aux_reason |")
    A("|---|---|---|---|")
    interesting = [r for r in rows if r.get("has_aux") == "1" or r.get("aux_status") in ("AUX_BUILT", "AUX_ROLLED_BACK")]
    interesting.sort(key=lambda r: int(r.get("aux_ops_count") or 0), reverse=True)
    os.makedirs(os.path.join(OUT, "manual_review"), exist_ok=True)
    shown = 0
    for r in interesting[:15]:
        A(f"| {r['task_uid'][:20]} | {r.get('aux_status')} | {r.get('aux_ops_count')} | {(r.get('aux_reason') or '')[:40]} |")
        shown += 1
        # копируем SVG
        for suffix in ("_base.svg", "_aux.svg"):
            src = os.path.join(OUT, "svg", f"{r['task_uid']}{suffix}")
            if os.path.exists(src):
                shutil.copy(src, os.path.join(OUT, "manual_review", f"{r['task_uid']}{suffix}"))
    A(f"\n(скопировано {shown} задач с aux в manual_review/)")

    with open(os.path.join(OUT, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("wrote", os.path.join(OUT, "report.md"))


if __name__ == "__main__":
    main()
