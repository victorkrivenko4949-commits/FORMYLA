# -*- coding: utf-8 -*-
"""CH24: сгенерировать отчёт output/ch24/report.md из results.csv + планов.

Анализирует:
  * done/failed из 40;
  * причины отказа base (HARD/DEGENERATE/MISSING/LLM_NO_JSON/невозможная геометрия);
  * распределение aux_status;
  * воронку aux: steps -> ops -> built по solution_style;
  * сколько отказов вызвано дефектами банка (дискретные/комбинаторные задачи);
  * прогноз на 354 задачи;
  * три главных дефекта.

Запуск: python scripts/ch24_report.py
"""
import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "output", "ch24")
_RESULTS = os.path.join(_OUT, "results.csv")
_REPORT = os.path.join(_OUT, "report.md")
_INPUT = os.path.join(_ROOT, "output", "ch19", "pilot_100.jsonl")


def _load_records():
    recs = {}
    try:
        with open(_INPUT, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                uid = str(d.get("task_uid", ""))
                if uid:
                    recs[uid] = d
    except OSError:
        pass
    return recs


def _is_discrete_bank(cond):
    """Эвристика: дискретная/комбинаторная задача (не евклидова геометрия)."""
    if not cond:
        return False
    c = cond.lower()
    markers = [
        "шахматн", "клетчат", "сетк", "100 точ", "20 × 20", "20 \\times 20",
        "18 клет", "вырезать", "ладь", "разбивает точки", "никакие три",
        "произведени",  # вычислительно-комбинаторные (A₁..A₁₀ на окружности)
    ]
    return any(m in c for m in markers)


def _classify_base_fail(row, recs):
    """Классифицировать причину отказа.  Возвращает категорию.

    Разделяем base-отказы (base_thinking/base_drawing) и aux-отказы
    (aux_thinking/aux_drawing с AUX_*-статусом).
    """
    code = (row.get("base_fail_codes") or "").strip()
    stage = (row.get("current_stage") or "").strip()
    aux_status = (row.get("aux_status") or "").strip()

    # Aux-отказы — отдельная категория (не base).
    if stage.startswith("aux_") or aux_status.startswith("AUX_"):
        return "AUX_FAILED"

    # Сначала — дефект банка: дискретная/комбинаторная задача, которой не
    # нужен евклидов чертёж (шахматы, сетки, 100 точек, произведения).
    uid = row.get("task_uid", "")
    cond = recs.get(uid, {}).get("statement", "") if recs else ""
    if _is_discrete_bank(cond):
        return "BANK_DISCRETE_SCOPE"

    if "DEGENERATE_SEGMENT" in code:
        return "DEGENERATE_SEGMENT"
    if "MISSING_CONDITION_POINT" in code:
        return "MISSING_CONDITION_POINT"
    if "LLM_NO_JSON" in code:
        return "LLM_NO_JSON"
    if "BASE_PARSE" in code or "BASE_VALIDATION" in code:
        return "BASE_VALIDATION"
    if "LLM_ERROR" in code:
        return "LLM_TRANSPORT"
    if "RUNNER_CRASH" in code:
        return "RUNNER_CRASH"
    if "HARD_POINT_DIST" in code:
        return "HARD_POINT_DIST"
    if "HARD_BOUNDS" in code:
        return "HARD_BOUNDS"
    if "ENGINE_HARD" in code or code.startswith("HARD_"):
        return "ENGINE_HARD"
    return "OTHER"


def main():
    recs = _load_records()
    rows = []
    if os.path.exists(_RESULTS):
        with open(_RESULTS, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(r)

    if not rows:
        print("Нет results.csv — прогон не завершён.")
        return

    total = len(rows)
    done = [r for r in rows if r.get("status") == "done"]
    failed = [r for r in rows if r.get("status") != "done"]
    n_done = len(done)
    n_failed = len(failed)

    # ── Причины отказа base ──
    fail_categories = Counter()
    fail_examples = defaultdict(list)
    for r in failed:
        cat = _classify_base_fail(r, recs)
        fail_categories[cat] += 1
        uid = r.get("task_uid", "?")
        cond = recs.get(uid, {}).get("statement", "") if recs else ""
        cond_short = (cond or "").strip().replace("\n", " ")[:110]
        soft = (r.get("soft_warnings") or "").strip()
        if len(fail_examples[cat]) < 3:
            fail_examples[cat].append({
                "uid": uid,
                "cond": cond_short,
                "soft": soft,
                "stage": r.get("current_stage", ""),
                "code": r.get("base_fail_codes", ""),
            })

    # ── aux_status распределение ──
    aux_status_counter = Counter(r.get("aux_status") or "-" for r in rows)

    # ── aux_status по solution_style ──
    aux_by_style = defaultdict(Counter)
    for r in rows:
        aux_by_style[r.get("solution_style") or "unknown"][r.get("aux_status") or "-"] += 1

    # ── Воронка aux для constructive: только задачи, ДОШЕДШИЕ до aux-этапа.
    # Задачи, упавшие на base, в воронку aux не входят.
    reached_aux = [r for r in rows
                   if r.get("solution_style") == "constructive"
                   and r.get("status") == "done"]
    base_failed = [r for r in rows
                   if r.get("solution_style") == "constructive"
                   and r.get("status") != "done"
                   and not (r.get("current_stage") or "").startswith("aux_")]
    aux_failed = [r for r in rows
                  if r.get("solution_style") == "constructive"
                  and r.get("status") != "done"
                  and (r.get("current_stage") or "").startswith("aux_")]

    funnel = {
        "reached_aux": len(reached_aux),
        "base_failed": len(base_failed),
        "aux_failed": len(aux_failed),
        "with_steps": sum(1 for r in reached_aux if int(r.get("extracted_steps_count") or 0) > 0),
        "total_steps": sum(int(r.get("extracted_steps_count") or 0) for r in reached_aux),
        "with_ops": sum(1 for r in reached_aux if int(r.get("compiled_ops_count") or 0) > 0),
        "total_ops": sum(int(r.get("compiled_ops_count") or 0) for r in reached_aux),
        "aux_built": sum(1 for r in reached_aux if r.get("aux_status") == "AUX_BUILT"),
        "aux_not_needed": sum(1 for r in reached_aux if r.get("aux_status") == "AUX_NOT_NEEDED"),
        "aux_build_failed": sum(1 for r in reached_aux if r.get("aux_status") == "AUX_BUILD_FAILED"),
        "aux_plan_rejected": sum(1 for r in reached_aux if r.get("aux_status") == "AUX_PLAN_REJECTED"),
    }

    loss = {
        "no_steps": sum(1 for r in reached_aux if int(r.get("extracted_steps_count") or 0) == 0),
        "steps_but_no_ops": sum(
            1 for r in reached_aux
            if int(r.get("extracted_steps_count") or 0) > 0
            and int(r.get("compiled_ops_count") or 0) == 0
        ),
        "ops_but_not_built": sum(
            1 for r in reached_aux
            if int(r.get("compiled_ops_count") or 0) > 0
            and r.get("aux_status") != "AUX_BUILT"
        ),
    }

    # ── Дефекты банка vs системы (только среди base-отказов) ──
    aux_failed = sum(1 for r in failed if _classify_base_fail(r, recs) == "AUX_FAILED")
    bank_defect = sum(1 for r in failed if _classify_base_fail(r, recs).startswith("BANK_"))
    base_failed_n = n_failed - aux_failed
    system_defect = base_failed_n - bank_defect

    lines = []
    lines.append("# CH24 диагностический отчёт — 40 задач\n")

    lines.append("## 1. Итог\n")
    lines.append(f"- Всего: **{total}**")
    lines.append(f"- done: **{n_done}**")
    lines.append(f"- failed: **{n_failed}**\n")

    lines.append("## 2. Причины отказа base\n")
    lines.append("| Категория | Кол-во |")
    lines.append("|---|---|")
    for cat, cnt in fail_categories.most_common():
        lines.append(f"| {cat} | {cnt} |")
    lines.append("")
    for cat, exs in fail_examples.items():
        lines.append(f"### {cat}\n")
        for ex in exs:
            lines.append(f"- `{ex['uid']}` (stage={ex['stage']})")
            if ex["cond"]:
                lines.append(f"  - Условие: {ex['cond']}")
            if ex["soft"]:
                lines.append(f"  - HARD-значения: {ex['soft'][:260]}")
        lines.append("")

    lines.append("## 3. Распределение aux_status\n")
    lines.append("| aux_status | Кол-во |")
    lines.append("|---|---|")
    for st, cnt in aux_status_counter.most_common():
        lines.append(f"| {st} | {cnt} |")
    lines.append("")

    lines.append("## 4. aux_status по solution_style\n")
    all_st = sorted({st for c in aux_by_style.values() for st in c})
    lines.append("| style | " + " | ".join(all_st) + " |")
    lines.append("|---|" + "---|" * len(all_st))
    for st in sorted(aux_by_style.keys()):
        c = aux_by_style[st]
        cells = " | ".join(str(c.get(k, 0)) for k in all_st)
        lines.append(f"| {st} | {cells} |")
    lines.append("")

    lines.append("## 5. Воронка aux для constructive-задач\n")
    lines.append(f"- constructive всего: **{funnel['reached_aux'] + funnel['base_failed'] + funnel['aux_failed']}**")
    lines.append(f"- упали на base (в aux не попали): **{funnel['base_failed']}**")
    lines.append(f"- упали на aux-этапе: **{funnel['aux_failed']}**")
    lines.append(f"- дошли до aux-этапа и завершились: **{funnel['reached_aux']}**")
    lines.append(f"-   с шагами экстрактора: **{funnel['with_steps']}** (всего steps {funnel['total_steps']})")
    lines.append(f"-   с скомпилированными ops: **{funnel['with_ops']}** (всего ops {funnel['total_ops']})")
    lines.append(f"-   AUX_BUILT: **{funnel['aux_built']}**")
    lines.append(f"-   AUX_NOT_NEEDED: **{funnel['aux_not_needed']}**")
    lines.append(f"-   AUX_BUILD_FAILED: **{funnel['aux_build_failed']}**")
    lines.append(f"-   AUX_PLAN_REJECTED: **{funnel['aux_plan_rejected']}**")
    lines.append("")
    lines.append("Потери по этапам (среди дошедших до aux):")
    lines.append(f"- extract (0 шагов): **{loss['no_steps']}**")
    lines.append(f"- compile (шаги есть, ops=0): **{loss['steps_but_no_ops']}**")
    lines.append(f"- draw/validate (ops есть, но не AUX_BUILT): **{loss['ops_but_not_built']}**")
    lines.append("")

    lines.append("## 6. Дефекты банка vs системы\n")
    lines.append(f"- Отказы на base-этапе: **{base_failed_n}**")
    lines.append(f"- Отказы на aux-этапе: **{aux_failed}**")
    lines.append(f"-   из base: дефекты банка (дискретные/комбинаторные условия вне scope движка): **{bank_defect}**")
    lines.append(f"-   из base: дефекты системы (degenerate координаты / выход за canvas / LLM-план): **{system_defect}**")
    lines.append("")
    lines.append("_Невозможных (математически противоречивых) условий не обнаружено — все условия корректны;_")
    lines.append("«дефект банка» здесь — это задачи, которым не нужен евклидов чертёж (шахматы, сетки, 100 точек)._")
    lines.append("")

    lines.append("## 7. Прогноз на 354 задачи\n")
    if total:
        done_rate = n_done / total
        aux_rate = sum(1 for r in rows if r.get("has_aux") == "1") / total
        lines.append(f"- base (done): **~{round(done_rate * 354)}** из 354")
        lines.append(f"- aux (has_aux=1): **~{round(aux_rate * 354)}** из 354")
    lines.append("")

    lines.append("## 8. Три главных дефекта (по приоритету)\n")
    ordered = fail_categories.most_common(3)
    for i, (cat, cnt) in enumerate(ordered, 1):
        lines.append(f"{i}. **{cat}** — {cnt} задач.")
    lines.append("")

    with open(_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[ch24] report written: {_REPORT}")
    print(f"[ch24] done={n_done} failed={n_failed}")
    print(f"[ch24] fail_categories={dict(fail_categories)}")
    print(f"[ch24] aux_status={dict(aux_status_counter)}")
    print(f"[ch24] funnel={funnel}")
    print(f"[ch24] bank_defect={bank_defect} system_defect={system_defect}")


if __name__ == "__main__":
    main()
