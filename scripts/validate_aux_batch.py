# -*- coding: utf-8 -*-
"""CH28: валидация партии aux_construction (40 задач) без LLM.

Для каждой задачи:
  1. Компилирует aux_construction.steps через services.aux_compiler
     (БЕЗ обращения к LLM).
  2. Проверяет, что каждый action есть в реестре (_ACTION_OP).
  3. Проверяет, что все creates_point разрешаются (нет UNRESOLVED_POINT).
  4. Проверяет ссылки по id (obj1/obj2/line1/line2).
  5. Проверяет формат имён точек.

Выводит сводку: сколько компилируется без issues, список задач с issues и
кодом каждого issue, частоты action, распределение has_aux.

Запуск: python scripts/validate_aux_batch.py
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BATCH = os.path.join(_ROOT, "data", "figures", "aux_batch_1_40.jsonl")


def _load_batch():
    recs = []
    with open(_BATCH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs


def _name_format_ok(name):
    """Проверка формата имён точек: латиница A-Z, опц. цифра/индекс."""
    if not name:
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", str(name)))


def main():
    from services.aux_compiler import compile_steps_to_aux, _ACTION_OP

    recs = _load_batch()
    print(f"Всего задач в партии: {len(recs)}\n")

    clean = 0
    issues_by_task = {}
    action_counter = Counter()
    has_aux_true = 0
    has_aux_false = 0
    name_issues = []

    for r in recs:
        uid = r.get("task_uid", "?")
        aux = r.get("aux_construction") or {}
        steps = aux.get("steps", [])
        unsupported = aux.get("unsupported", [])
        has_aux = bool(aux.get("has_aux", False))

        if has_aux:
            has_aux_true += 1
        else:
            has_aux_false += 1

        # Частоты action.
        for s in steps:
            if isinstance(s, dict):
                action_counter[s.get("action", "?")] += 1

        # Формат имён creates_point.
        for s in steps:
            if not isinstance(s, dict):
                continue
            cp = s.get("creates_point")
            if cp and not _name_format_ok(cp):
                name_issues.append((uid, cp))

        # Компиляция (детерминированная, без LLM).
        # base_plan пустой — компилятор сам проверит ссылки по registry.
        base_plan = {"constructions": []}
        aux_plan, issues = compile_steps_to_aux(steps, base_plan)

        # Неизвестные action.
        unknown_actions = []
        for s in steps:
            if isinstance(s, dict) and s.get("action") not in _ACTION_OP:
                unknown_actions.append(f"UNKNOWN_ACTION:{s.get('action')}")

        # Проверка ссылок по id: шаги с id и ссылки на них.
        step_ids = {s.get("id") for s in steps if isinstance(s, dict) and s.get("id")}
        id_ref_issues = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            args = s.get("args") or {}
            for k in ("obj1", "obj2"):
                v = args.get(k)
                if isinstance(v, str) and v and v not in step_ids:
                    id_ref_issues.append(f"UNKNOWN_STEP_ID:{v}")

        all_issues = list(issues) + unknown_actions + id_ref_issues
        if all_issues:
            issues_by_task[uid] = all_issues
        else:
            clean += 1

    # ── Сводка ──
    print("=" * 70)
    print("СВОДКА")
    print("=" * 70)
    print(f"Компилируется без issues: {clean} / {len(recs)}")
    print(f"has_aux=true: {has_aux_true}")
    print(f"has_aux=false: {has_aux_false}")
    print()

    print("Частоты action:")
    for action, cnt in action_counter.most_common():
        print(f"  {action}: {cnt}")
    print()

    if name_issues:
        print(f"Проблемы формата имён creates_point ({len(name_issues)}):")
        for uid, name in name_issues[:20]:
            print(f"  {uid}: creates_point={name!r}")
        print()

    if issues_by_task:
        print(f"Задачи с issues ({len(issues_by_task)}):")
        for uid, iss in issues_by_task.items():
            codes = Counter(i.split(":")[0] for i in iss)
            code_str = ", ".join(f"{c}×{n}" for c, n in codes.items())
            print(f"  {uid[:36]}: {code_str}")
            for i in iss[:6]:
                print(f"      - {i}")
    else:
        print("Нет задач с issues.")

    # ── Отчёт в файл ──
    out = {
        "total": len(recs),
        "clean": clean,
        "has_aux_true": has_aux_true,
        "has_aux_false": has_aux_false,
        "actions": dict(action_counter),
        "issues_by_task": issues_by_task,
        "name_issues": name_issues,
    }
    out_path = os.path.join(_ROOT, "output", "ch28_validate.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[ch28] отчёт: {out_path}")


if __name__ == "__main__":
    main()
