# -*- coding: utf-8 -*-
"""Дыры в нумерации задач каталога олимпиад + нормализация поля day.

Вариант = (год, этап, класс). Дни объединяются: у ВсОШ нумерация сквозная
(день 1 — №1–4, день 2 — №5–8), поэтому считать день отдельным вариантом нельзя —
получаются ложные «нет №1–4». Внутри варианта смотрим, какие номера от 1 до
максимального присутствующего отсутствуют.

Важно: максимальный номер в файле — лишь нижняя оценка длины варианта. Если в файле
есть только №3 и №5, отчёт покажет пропуски 1, 2, 4; про №6 и дальше данных нет.

День: у ряда олимпиад (Физтех и др.) в данных вперемешку day=0 и day=1, хотя дней
у олимпиады нет. День считаем настоящим только если внутри одного (год, этап)
встречается больше одного непустого значения day (этим пользуется отображение каталога).
"""
from __future__ import annotations

import re
from collections import OrderedDict

_NUM_RE = re.compile(r"\d+")


def norm_day(d) -> str:
    d = str(d if d is not None else "").strip()
    return "" if d in ("", "0", "None", "none") else d


def multi_day_keys(tasks) -> set:
    """Множество (year, round), внутри которых реально больше одного дня."""
    days: dict = {}
    for t in tasks:
        days.setdefault((t.get("year"), str(t.get("round", ""))), set()).add(norm_day(t.get("day")))
    return {k for k, v in days.items() if len(v - {""}) > 1}


def task_num(t):
    m = _NUM_RE.search(str(t.get("num", "")))
    return int(m.group()) if m else None


def _grade_key(g):
    try:
        return int(g)
    except Exception:  # noqa: BLE001
        return 99


def variant_gaps(tasks):
    """Все варианты олимпиады: [{year, round, grade, days, have, missing, count, max}].

    days — список дней, в которых встречаются задачи варианта (пустой, если дней нет);
    нумерация считается по объединению дней.
    """
    multi = multi_day_keys(tasks)
    groups: "OrderedDict[tuple, dict]" = OrderedDict()
    for t in tasks:
        n = task_num(t)
        if n is None:
            continue
        year, rnd = t.get("year"), str(t.get("round", ""))
        g = groups.setdefault((year, rnd, str(t.get("grade", ""))), {"nums": set(), "days": set()})
        g["nums"].add(n)
        if (year, rnd) in multi:
            d = norm_day(t.get("day"))
            if d:
                g["days"].add(d)
    out = []
    for (year, rnd, grade), g in groups.items():
        nums = g["nums"]
        mx = max(nums)
        out.append({"year": year, "round": rnd, "grade": grade,
                    "days": sorted(g["days"], key=lambda x: (len(x), x)),
                    "have": sorted(nums), "missing": sorted(set(range(1, mx + 1)) - nums),
                    "count": len(nums), "max": mx})
    return out


def summarize(slug, name, tasks):
    variants = variant_gaps(tasks)
    gaps = [v for v in variants if v["missing"]]
    gaps.sort(key=lambda v: (-int(v["year"] or 0), v["round"], _grade_key(v["grade"])))
    return {"slug": slug, "name": name, "tasks": len(tasks), "variants": len(variants),
            "variants_with_gaps": len(gaps),
            "missing_total": sum(len(v["missing"]) for v in gaps), "gaps": gaps}


def report_md(summaries) -> str:
    lines = ["# Дыры в нумерации задач каталога", "",
             "Вариант = год + этап + класс (дни объединены: у ВсОШ нумерация сквозная по дням). "
             "Пропуск = номер меньше максимального в варианте, которого нет в файле. "
             "Номера больше максимального не учитываются (данных о длине варианта нет).", "",
             "| Олимпиада | Задач | Вариантов | С пропусками | Пропущено номеров |",
             "|---|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append("| %s | %d | %d | %d | %d |" % (s["name"], s["tasks"], s["variants"],
                                                   s["variants_with_gaps"], s["missing_total"]))
    for s in summaries:
        if not s["gaps"]:
            continue
        lines += ["", "## %s (%s)" % (s["name"], s["slug"]), ""]
        for v in s["gaps"]:
            days = (" (дни: %s)" % ", ".join(v["days"])) if v["days"] else ""
            lines.append("- %s, %s, %s класс%s: есть №%s; нет №%s" % (
                v["year"], v["round"], v["grade"], days,
                ", ".join(map(str, v["have"])), ", ".join(map(str, v["missing"]))))
    return "\n".join(lines) + "\n"
