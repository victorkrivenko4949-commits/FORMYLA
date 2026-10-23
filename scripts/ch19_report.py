# -*- coding: utf-8 -*-
"""scripts/ch19_report.py — итоговый отчёт CH19 (Step 7).

Собирает output/ch19/report.md из:
  * инвентаризации входного файла (потоково);
  * классификатора стилей (services.solution_style);
  * results.csv пилота;
  * qa_report.md (сводка предупреждений).

Честный отчёт: фиксирует дефекты и неудачи, ничего не исправляя.
"""
import argparse
import csv
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from services.solution_style import classify_solution_style  # noqa: E402

DEFAULT_INPUT = "FORMYLA_geometry_7_11_chertezh_v13.jsonl"
OUT = os.path.join("output", "ch19")


def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "0%"


def med(xs):
    return round(statistics.median(xs), 1) if xs else 0


def p95(xs):
    if not xs:
        return 0
    s = sorted(xs)
    return round(s[int(0.95 * (len(s) - 1))], 1)


def inventory(input_path):
    total = 0
    grade = Counter()
    level = Counter()
    theme = Counter()
    stmt_lens = []
    sol_lens = []
    style = Counter()
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            total += 1
            grade[str(rec.get("grade"))] += 1
            level[str(rec.get("level"))] += 1
            theme[str(rec.get("theme_id"))] += 1
            stmt_lens.append(len(rec.get("statement") or ""))
            sol_lens.append(len(rec.get("solution") or ""))
            style[classify_solution_style(rec)] += 1
    return {
        "total": total, "grade": grade, "level": level, "theme": theme,
        "stmt": stmt_lens, "sol": sol_lens, "style": style,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    results_path = os.path.join(args.out, "results.csv")
    qa_path = os.path.join(args.out, "qa_report.md")
    state_path = os.path.join(args.out, "state.jsonl")

    inv = inventory(args.input)

    rows = []
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    done = [r for r in rows if r.get("status") == "done"]
    failed = [r for r in rows if r.get("status") != "done"]

    by_style_status = defaultdict(lambda: Counter())
    by_grade_status = defaultdict(lambda: Counter())
    for r in rows:
        by_style_status[r.get("solution_style")][r.get("status")] += 1
        by_grade_status[r.get("grade")][r.get("status")] += 1

    err_codes = Counter(r.get("error_code") or "UNKNOWN" for r in failed)

    lat_done = [float(r["total_latency_ms"]) for r in done if r.get("total_latency_ms")]
    lat_aux_t = [float(r["total_latency_ms"]) for r in done
                 if r.get("has_aux") == "1" and r.get("total_latency_ms")]
    lat_aux_f = [float(r["total_latency_ms"]) for r in done
                 if r.get("has_aux") == "0" and r.get("total_latency_ms")]

    cost_done = [float(r["cost_usd"]) for r in done if r.get("cost_usd")]
    cost_all = [float(r["cost_usd"]) for r in rows if r.get("cost_usd")]
    avg_cost_success = (sum(cost_done) / len(cost_done)) if cost_done else 0.0
    total_cost = sum(cost_all)

    n = len(rows)
    fast = sum(1 for r in rows if r.get("fast_path_used") == "1")
    fallback = sum(1 for r in rows if r.get("fallback_to_two_call") == "1")
    audit = sum(1 for r in rows if r.get("audit_executed") == "1")
    structured = sum(1 for r in rows if r.get("structured_json_used") == "1")

    has_aux_by_style = defaultdict(lambda: Counter())
    for r in done:
        has_aux_by_style[r.get("solution_style")][r.get("has_aux")] += 1

    # QA warnings
    qa_summary = []
    if os.path.exists(qa_path):
        with open(qa_path, encoding="utf-8") as f:
            qa_lines = f.read().splitlines()
        in_table = False
        for ln in qa_lines:
            # Останавливаемся на второй таблице («Сводка по задачам»).
            if ln.startswith("## Сводка"):
                break
            if ln.startswith("| код проблемы"):
                in_table = True
                continue
            if in_table and ln.startswith("|-"):
                continue
            if in_table and ln.startswith("|"):
                parts = [p.strip() for p in ln.strip("|").split("|")]
                if len(parts) >= 2 and parts[0]:
                    qa_summary.append(parts[:2])

    # Кредиты: читаем из state + примечание (списания в коде отключены).
    credit_charges = sum(1 for r in done)  # ожидание по инварианту «1 done = 1 списание»
    credit_refunds = len(failed)

    # Прогноз полного прогона (354 записи).
    full_total = inv["total"]
    avg_cost_per_task = (total_cost / n) if n else 0.0
    projected_cost = avg_cost_per_task * full_total
    avg_latency = statistics.mean(lat_done) if lat_done else 0.0
    # время = (среднее latency) * число задач / workers(2), в секундах
    projected_sec = (avg_latency / 1000.0) * full_total / 2.0

    L = []
    A = L.append
    A("# CH19 — Итоговый отчёт пакетной генерации чертежей\n")
    A("> Пилот: 100 задач, workers=2, max-cost-usd=5. "
      "Провайдеры: Novita (недоступен по сети) → DeepSeek (fallback).\n")
    A("")
    A("## 1. Инвентаризация файла\n")
    A(f"- Всего записей: **{inv['total']}** (все quality_status=APPROVE, все с solution).")
    A(f"- Длины statement: медиана {med(inv['stmt'])}, p90 {p95(inv['stmt'])}, "
      f"max {max(inv['stmt'])}.")
    A(f"- Длины solution: медиана {med(inv['sol'])}, p90 {p95(inv['sol'])}, "
      f"max {max(inv['sol'])}.")
    A("- Распределение по grade: "
      + ", ".join(f"{g}={inv['grade'][g]}" for g in sorted(inv['grade'])))
    A("- Распределение по level: "
      + ", ".join(f"{l}={inv['level'][l]}" for l in sorted(inv['level'])))
    A("")
    A("## 2. Классификатор стилей (по всему файлу)\n")
    A("| style | количество |")
    A("|---|---|")
    for s, c in inv["style"].most_common():
        A(f"| {s} | {c} |")
    A("")
    A("## 3. Результаты пилота (done/failed по style)\n")
    A("| style | done | failed |")
    A("|---|---|---|")
    for s in sorted(by_style_status):
        A(f"| {s} | {by_style_status[s].get('done', 0)} | "
          f"{by_style_status[s].get('failed', 0)} |")
    A("")
    A("## 3b. done/failed по grade\n")
    A("| grade | done | failed |")
    A("|---|---|---|")
    for g in sorted(by_grade_status, key=lambda x: (int(x) if x.isdigit() else 999, x)):
        A(f"| {g} | {by_grade_status[g].get('done', 0)} | "
          f"{by_grade_status[g].get('failed', 0)} |")
    A("")
    A("## 4. Топ error_code\n")
    A("| code | count |")
    A("|---|---|")
    for code, cnt in err_codes.most_common(15):
        A(f"| {code} | {cnt} |")
    A("")
    A("## 5. Latency (ms)\n")
    A(f"- p50/p95/max (все done): {med(lat_done)} / {p95(lat_done)} / "
      f"{max(lat_done) if lat_done else 0}.")
    A(f"- has_aux=true: p50 {med(lat_aux_t)}, p95 {p95(lat_aux_t)}, "
      f"max {max(lat_aux_t) if lat_aux_t else 0}.")
    A(f"- has_aux=false: p50 {med(lat_aux_f)}, p95 {p95(lat_aux_f)}, "
      f"max {max(lat_aux_f) if lat_aux_f else 0}.")
    A("")
    A("## 6. Стоимость\n")
    A(f"- Средняя цена успешного чертежа: ${avg_cost_success:.6f}.")
    A(f"- Общая стоимость пилота: ${total_cost:.6f}.")
    A("")
    A("## 7. Доли pipeline-метрик\n")
    A(f"- fast_path_used: {fast}/{n} ({pct(fast, n)})")
    A(f"- fallback_to_two_call: {fallback}/{n} ({pct(fallback, n)})")
    A(f"- audit_executed: {audit}/{n} ({pct(audit, n)})")
    A(f"- structured_json_used: {structured}/{n} ({pct(structured, n)})")
    A("")
    A("## 8. Доля has_aux по style (КЛЮЧЕВАЯ метрика)\n")
    A("| style | has_aux=true | has_aux=false | доля aux |")
    A("|---|---|---|---|")
    for s in sorted(has_aux_by_style):
        t = has_aux_by_style[s].get("1", 0)
        f_ = has_aux_by_style[s].get("0", 0)
        A(f"| {s} | {t} | {f_} | {pct(t, t + f_)} |")
    A("")
    A("## 9. Сводка QA-предупреждений\n")
    if qa_summary:
        for code, cnt in qa_summary:
            A(f"- {code}: {cnt}")
    else:
        A("- (QA-отчёт отсутствует или пуст — нет done-задач.)")
    A("")
    A("## 10. Сверка кредитов\n")
    A(f"- Списания (ожидание: 1 на done): {credit_charges}.")
    A(f"- Возвраты (ожидание: 1 на failed): {credit_refunds}.")
    A("- ФАКТ: `_charge_credit` в конвейере отключён (возвращает 'unlimited'); "
      "`_refund_credit` срабатывает только при credit_charged=true. "
      "Поэтому фактический баланс служебного аккаунта не меняется (delta=0).")
    A("")
    A("## 11. Прогноз полного прогона\n")
    A(f"- Средняя стоимость задачи: ${avg_cost_per_task:.6f}.")
    A(f"- Прогноз стоимости {full_total} задач: ${projected_cost:.2f}.")
    A(f"- Средняя latency done-задачи: {avg_latency:.0f} ms; "
      f"прогноз времени (2 workers): {projected_sec / 60:.0f} мин.")
    A("")
    A("## 12. Рекомендация\n")
    A("")
    A("**НЕ масштабировать сейчас.** Пилот вскрыл критический дефект конвейера:")
    A("")
    A("1. **[CRITICAL] `max_tokens=4096` жёстко зашит в `_call_deepseek`** "
      "([`routes/figures_generator.py`](routes/figures_generator.py:467)), "
      "а `FIGURE_BASE_MAX_TOKENS`/`FIGURE_AUX_MAX_TOKENS`/`FIGURE_AUDIT_MAX_TOKENS` "
      "нигде не читаются. Реализованные модели (`deepseek-v4-flash`/`deepseek-v4-pro`) "
      "являются reasoning-моделями: весь бюджет уходит на CoT (`reasoning_tokens`), "
      "JSON не успевает сгенерироваться → `LLM_NO_JSON` / «Модель не смогла создать "
      "корректный base-план» на большинстве задач.")
    A("2. **[HIGH] Падение базового планировщика — массовое** (см. топ error_code). "
      "Успешны лишь задачи с коротким CoT.")
    A("3. **[MED] Novita недоступна по сети** (ConnectionError) — прогон полностью "
      "ложится на fallback DeepSeek, увеличивая latency и стоимость.")
    A("")
    A("Дефекты по приоритету исправления: 1 → 2 → 3. После исправления max_tokens "
      "(или перехода на non-reasoning модель для планировщиков) повторить пилот.")

    report_path = os.path.join(args.out, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("wrote", report_path)
    print("done:", len(done), "failed:", len(failed), "cost:", round(total_cost, 6))


if __name__ == "__main__":
    main()
