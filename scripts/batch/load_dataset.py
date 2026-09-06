# -*- coding: utf-8 -*-
"""scripts/batch/load_dataset.py — разбор датасета geometry 7-11 + выборка.

БЛОК 0: определить формат, нормализовать схему, посчитать статистику.
БЛОК 1: детерминированная стратифицированная выборка 100 задач (20 на класс).

Нормализованная схема записи:
    {task_id, grade, condition, solution, answer, level, needs_figure}

Запуск:
    python scripts/batch/load_dataset.py [--sample] [--input PATH]

`--sample` дополнительно создаёт scripts/batch/out/sample_100.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Any, Dict, List, Optional

# Windows-консоль: принудительный UTF-8 для печати кириллицы и ∠.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Путь к файлу датасета по умолчанию (Загрузки пользователя).
DEFAULT_INPUT = os.path.join(
    os.path.expanduser("~"), "Downloads", "formyla_geometry_7_11_drawing_required.jsonl"
)

# Нормализованная схема (ключи, которые обязаны присутствовать в каждой записи).
NORMALIZED_FIELDS = ["task_id", "grade", "condition", "solution", "answer", "level", "needs_figure"]

# Детерминированный random_state для воспроизводимой выборки.
RANDOM_STATE = 42


def _read_jsonl(path: str) -> List[dict]:
    """Прочитать JSONL-файл (или JSON-массив) в список dict."""
    records: List[dict] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        first = f.read(1)
        f.seek(0)
        if first == "[":
            data = json.load(f)
            if isinstance(data, list):
                records = [r for r in data if isinstance(r, dict)]
        else:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    return records


def _first(d: dict, *keys: str) -> Any:
    """Вернуть первое не-None значение среди синонимичных ключей."""
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def normalize_record(raw: dict) -> dict:
    """Привести запись к единой схеме. Отсутствующие поля -> None."""
    return {
        "task_id": _first(raw, "task_uid", "task_id", "id", "uid"),
        "grade": _first(raw, "grade", "class", "class_level", "уровень"),
        "condition": _first(raw, "statement", "condition", "text", "problem", "условие"),
        "solution": _first(raw, "solution", "решение", "solution_text"),
        "answer": _first(raw, "answer", "ответ"),
        "level": _first(raw, "level", "difficulty", "сложность", "level_name"),
        # Файл называется drawing_required => для всего набора флаг True;
        # отдельного поля "нужен чертёж" в исходнике нет.
        "needs_figure": _first(raw, "needs_figure", "drawing_required", "нужен_чертеж", "requires_drawing"),
    }


def load_dataset(path: str) -> List[dict]:
    """Прочитать и нормализовать датасет в единую схему."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Датасет не найден: {path}")
    raw = _read_jsonl(path)
    normalized = [normalize_record(r) for r in raw]
    return normalized


def dataset_stats(rows: List[dict]) -> dict:
    """Статистика датасета (блок 0.4)."""
    from collections import Counter

    total = len(rows)
    by_grade = Counter(r.get("grade") for r in rows)
    with_solution = sum(1 for r in rows if r.get("solution"))
    with_answer = sum(1 for r in rows if r.get("answer") not in (None, ""))
    needs_figure_true = sum(1 for r in rows if r.get("needs_figure") in (True, 1, "true", "1", "yes"))
    # needs_figure может быть None (поле отсутствует) — тогда по имени файла считаем True.
    if needs_figure_true == 0 and total > 0:
        needs_figure_true = total

    return {
        "total": total,
        "by_grade": dict(sorted(by_grade.items())),
        "with_solution": with_solution,
        "with_answer": with_answer,
        "needs_figure_true": needs_figure_true,
    }


def build_sample(
    rows: List[dict],
    per_grade: int = 20,
    group_a_per_grade: int = 10,
    seed: int = RANDOM_STATE,
) -> List[dict]:
    """Стратифицированная детерминированная выборка.

    По per_grade задач на каждый класс 7-11.  Внутри класса задачи с решением
    имеют приоритет (все в GROUP_A).  Остаток класса идёт в GROUP_B.

    Так как в данном датасете решение есть у 100% задач, GROUP_B (без решения)
    формируется искусственно: задачи класса, которым решение НЕ передаётся в
    конвейер (mode=solver_aux).  Фактические размеры групп фиксируются в поле
    group.
    """
    by_grade: Dict[Any, List[dict]] = {}
    for r in rows:
        g = r.get("grade")
        if g is None:
            continue
        by_grade.setdefault(g, []).append(r)

    rng = random.Random(seed)
    sample: List[dict] = []
    for g in sorted(by_grade):
        pool = list(by_grade[g])
        # Приоритет задачам с решением.
        with_sol = [r for r in pool if r.get("solution")]
        without_sol = [r for r in pool if not r.get("solution")]
        rng.shuffle(with_sol)
        rng.shuffle(without_sol)
        ordered = with_sol + without_sol
        picked = ordered[:per_grade]
        if len(picked) < per_grade:
            # Не хватило задач — берём сколько есть.
            pass
        for idx, r in enumerate(picked):
            rec = dict(r)
            rec["group"] = "A" if idx < group_a_per_grade else "B"
            sample.append(rec)

    return sample


def _fmt_stat(rows: List[dict], title: str = "Датасет") -> str:
    s = dataset_stats(rows)
    lines = [
        f"== {title} ==",
        f"Всего задач: {s['total']}",
        "По классам: " + ", ".join(f"{k}={v}" for k, v in s["by_grade"].items()),
        f"С решением: {s['with_solution']}",
        f"С ответом: {s['with_answer']}",
        f"needs_figure=true: {s['needs_figure_true']}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Разбор датасета и выборка 100 задач")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Путь к JSONL-файлу датасета")
    parser.add_argument("--sample", action="store_true", help="Создать out/sample_100.jsonl")
    parser.add_argument("--per-grade", type=int, default=20)
    parser.add_argument("--group-a-per-grade", type=int, default=10)
    parser.add_argument("--seed", type=int, default=RANDOM_STATE)
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[load_dataset] Файл не найден: {args.input}", file=sys.stderr)
        # Попытка найти похожий файл в Загрузках.
        d = os.path.dirname(args.input)
        candidates = [f for f in os.listdir(d) if "formyla_geometry_7_11_drawing_required" in f.lower()]
        if candidates:
            print("[load_dataset] Найдены похожие файлы:", file=sys.stderr)
            for c in candidates:
                print("   ", os.path.join(d, c), file=sys.stderr)
        return 1

    rows = load_dataset(args.input)
    print(_fmt_stat(rows, "Датасет"))

    # Три примера записей (нормализованные, без полного текста решения).
    print("\n== 3 примера записей (нормализовано) ==")
    for r in rows[:3]:
        preview = {k: r.get(k) for k in NORMALIZED_FIELDS}
        preview["condition"] = (preview["condition"] or "")[:120]
        preview["solution"] = ((preview["solution"] or "")[:80] + "...") if preview["solution"] else None
        print(json.dumps(preview, ensure_ascii=False))

    # Фактические поля исходного файла.
    raw = _read_jsonl(args.input)
    all_keys: List[str] = []
    for r in raw:
        for k in r.keys():
            if k not in all_keys:
                all_keys.append(k)
    print("\n== Фактические поля исходного файла ==")
    print(", ".join(all_keys))

    if args.sample:
        sample = build_sample(
            rows,
            per_grade=args.per_grade,
            group_a_per_grade=args.group_a_per_grade,
            seed=args.seed,
        )
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "sample_100.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for r in sample:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        from collections import Counter
        gc = Counter((r["grade"], r["group"]) for r in sample)
        print(f"\n== Выборка ==")
        print(f"Всего отобрано: {len(sample)}")
        print("Распределение (grade, group):", dict(sorted(gc.items())))
        print(f"GROUP_A (с решением, condition_solution): {sum(1 for r in sample if r['group']=='A')}")
        print(f"GROUP_B (решение withheld, solver_aux): {sum(1 for r in sample if r['group']=='B')}")
        print(f"Сохранено: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
