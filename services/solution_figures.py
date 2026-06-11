"""Загрузка и поиск рисунков-решений по олимпиадным задачам.

Источник данных: `data/solution_figures_index.json`, который строится скриптом
[`scripts/build_solution_figures_index.py`](scripts/build_solution_figures_index.py:1)
на основе `static/solution_figures/MANIFEST.json`.

Ключ индекса — `"<olympiad>|<year>|<grade>|<num>"`. Это позволяет ОДНОЗНАЧНО
прикрепить картинку к задаче внутри пробника:
  - `olympiad` — slug олимпиады (как в OLYMPIADS_DB),
  - `year` — год пробника,
  - `grade` — класс,
  - `num` — номер задачи внутри пробника.

ВАЖНО: рисунки относятся к РЕШЕНИЮ. В шаблоне условий задач они НЕ
показываются. Это решается на уровне шаблона — здесь мы только отдаём
данные. См. [`templates/olympiad_solutions.html`](templates/olympiad_solutions.html:1).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INDEX_PATH = os.path.join(_HERE, "data", "solution_figures_index.json")

# Фичефлаг: показывать ли «возможные» картинки (assignment=pdf_pool_uncertain).
# По умолчанию выключен — на проде показываем только точные привязки.
# Включить можно env `SHOW_UNCERTAIN_FIGURES=1`.
SHOW_UNCERTAIN_FIGURES = (
    os.environ.get("SHOW_UNCERTAIN_FIGURES", "").strip().lower()
    in ("1", "true", "yes", "on")
)


@lru_cache(maxsize=1)
def _load_index() -> dict[str, list[dict]]:
    """Читает индекс с диска один раз и кэширует.

    Возвращает словарь `key -> [figure, ...]`, где `key` —
    "<olympiad>|<year>|<grade>|<num>" а `figure` —
    `{file, source_url, assignment?}`.

    Если файла нет (скрипт не запущен) — возвращает пустой dict.
    Это безопасный фолбэк: страницы решений просто не покажут картинки.
    """
    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except FileNotFoundError:
        return {}
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"[solution_figures] Cannot read index {_INDEX_PATH}: {e}"
        )
        return {}


def get_figures_for(
    *,
    olympiad: str,
    year: Any,
    grade: Any,
    num: Any,
    round_key: str | None = None,
) -> list[dict]:
    """Возвращает список картинок-решений для конкретной задачи.

    Каждая картинка — dict с полями:
        - file: путь относительно `static/` (например, `solution_figures/x.png`)
        - source_url: ссылка на источник
        - assignment: 'exact_search' | 'pdf_exact' | 'pdf_pool_uncertain'

    Картинки с `assignment == 'pdf_pool_uncertain'` скрываются, если
    переменная окружения `SHOW_UNCERTAIN_FIGURES` не выставлена.

    Ключ индекса: `<oly>|<year>|<grade>|<round>|<num>`. Если в индексе
    запись помечена `round='*'` — это «pdf_pool_uncertain», т.е. картинка
    точно не знает round (одна на весь год). Возвращаем её, если round
    запроса не известен либо если в (oly,year,grade) только один round-вариант.
    """
    if not (olympiad and year and grade and num):
        return []
    try:
        year_i = int(year)
        grade_i = int(grade)
        num_i = int(num)
    except (TypeError, ValueError):
        return []
    idx = _load_index()
    out: list[dict] = []
    seen_files: set[str] = set()

    # 1. Точный матч по round (если round_key передан)
    keys_to_try: list[str] = []
    if round_key:
        keys_to_try.append(
            f"{olympiad}|{year_i}|{grade_i}|{round_key}|{num_i}"
        )
    # 2. Wildcard round (`*`) — для pdf_pool_uncertain
    keys_to_try.append(f"{olympiad}|{year_i}|{grade_i}|*|{num_i}")

    # 3. Если round_key не указан — ищем ВСЕ round-варианты,
    # которые есть в индексе для этой задачи.
    if not round_key:
        for k in idx.keys():
            parts = k.split("|")
            if len(parts) == 5:
                k_oly, k_year, k_grade, k_round, k_num = parts
                if (k_oly == olympiad and k_year == str(year_i)
                        and k_grade == str(grade_i) and k_num == str(num_i)):
                    if k not in keys_to_try:
                        keys_to_try.append(k)

    for key in keys_to_try:
        for f in idx.get(key) or []:
            a = (f.get("assignment") or "").strip().lower()
            if a == "pdf_pool_uncertain" and not SHOW_UNCERTAIN_FIGURES:
                continue
            file_path = f.get("file", "")
            if file_path in seen_files:
                continue
            seen_files.add(file_path)
            out.append({
                "file": file_path,
                "source_url": f.get("source_url", ""),
                "assignment": a,
            })
    return out


def attach_to_problems(
    *,
    combo: dict,
    problems: list,
) -> int:
    """Дополняет каждую задачу в списке полем `solution_figures`.

    Возвращает количество ПРИКРЕПЛЁННЫХ картинок (для логирования).
    Не модифицирует текст задачи/решения. Идемпотентно: если у задачи
    уже есть `solution_figures`, новые картинки добавляются без дублей.

    Использует `round_key` из combo для точного матчинга — это
    предотвращает ложные привязки картинок из качественного этапа к
    задачам финала и наоборот.

    Использовать прямо перед `render_template` для страниц решений.
    """
    if not (isinstance(combo, dict) and isinstance(problems, list)):
        return 0
    olympiad = (combo.get("olympiad") or "").lower()
    year = combo.get("year")
    grade = combo.get("grade")
    round_key = (combo.get("round") or "").strip() or None
    if not (olympiad and year and grade):
        return 0
    total = 0
    for p in problems:
        if not isinstance(p, dict):
            continue
        num = p.get("num")
        figs = get_figures_for(
            olympiad=olympiad, year=year, grade=grade,
            num=num, round_key=round_key,
        )
        if not figs:
            continue
        existing = list(p.get("solution_figures") or [])
        existing_files = {x.get("file") for x in existing if isinstance(x, dict)}
        for f in figs:
            if f["file"] in existing_files:
                continue
            existing.append(f)
            total += 1
        p["solution_figures"] = existing
    return total
