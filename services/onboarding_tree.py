# -*- coding: utf-8 -*-
"""
FORMYLA — линейная анкета онбординга (5 вопросов, 5 якорей).

Дерево из 5 вопросов БЕЗ ветвления:
  Q1: grade      — класс (5-11), автозаполнение из профиля
  Q2: target     — целевой уровень (1-5)
  Q3: olymp_reach — олимпиадный опыт (mu/w из Q2_BY_GOAL["olympiad"])
  Q4: load       — нагрузка (без изменений)
  Q5: deadline   — дата олимпиады или "нет даты"

Затем 5 якорных задач из 5 РАЗНЫХ разделов (все разделы, фиксированный порядок).
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any

# ══════════════════════════════════════════════════════════════════════════════
# ЧАСТЬ 1. Дерево вопросов — ровно 5, без ветвления.
# ══════════════════════════════════════════════════════════════════════════════

Q1_GRADE = {
    "id": "grade",
    "text": "Кто ты?",
    "options": [
        {"key": "teacher", "label": "Я учитель",     "value": "teacher", "role": "teacher"},
        {"key": "parent",  "label": "Я родитель",     "value": "parent",  "role": "parent"},
        {"key": "5",       "label": "5 класс",        "value": 5},
        {"key": "6",       "label": "6 класс",        "value": 6},
        {"key": "7",       "label": "7 класс",        "value": 7},
        {"key": "8",       "label": "8 класс",        "value": 8},
        {"key": "9",       "label": "9 класс",        "value": 9},
        {"key": "10",      "label": "10 класс",       "value": 10},
        {"key": "11",      "label": "11 класс",       "value": 11},
    ],
}

Q2_TARGET = {
    "id": "target",
    "text": "До какого уровня хочешь дойти? Это цель — пройдём её как можно быстрее.",
    "options": [
        {"key": "lvl1", "label": "Вводный уровень, первые олимпиадные задачи", "target_level": 1},
        {"key": "lvl2", "label": "Школьный этап ВОШ",                          "target_level": 2},
        {"key": "lvl3", "label": "Муниципальный этап",                         "target_level": 3},
        {"key": "lvl4", "label": "Региональный этап",                          "target_level": 4},
        {"key": "lvl5", "label": "Заключительный этап, сильные финалы",        "target_level": 5},
    ],
}

# ── Q3: olymp_reach — существующий вопрос из ветки "olympiad" в Q2_BY_GOAL.
#     Перенесён как есть, mu и w НЕ менять. ──
Q3_OLYMP_REACH = {
    "id": "olymp_reach",
    "text": "Как далеко доходил на олимпиадах по математике?",
    "options": [
        {"key": "none",   "label": "Не участвовал",              "mu": 1.6, "w": 0.9},
        {"key": "school", "label": "Школьный этап",              "mu": 2.1, "w": 0.9},
        {"key": "muni",   "label": "Муниципальный этап",         "mu": 2.9, "w": 1.0},
        {"key": "region", "label": "Региональный этап и выше",   "mu": 3.9, "w": 1.1},
    ],
}

# ── Q4: load — существующий Q3_LOAD без изменений ──
Q4_LOAD = {
    "id": "load",
    "text": "Сколько минут в день реально готов тратить? Отвечай честно — от этого зависит объём, а не сложность.",
    "options": [
        {"key": "m15", "label": "15 минут",     "tasks": 3},
        {"key": "m30", "label": "30 минут",     "tasks": 5},
        {"key": "m60", "label": "Около часа",   "tasks": 8},
        {"key": "m90", "label": "Больше часа",  "tasks": 10},
    ],
}

# ── Q5: deadline — вариант "нет даты" + поле ввода конкретной даты ──
Q5_DEADLINE = {
    "id": "deadline",
    "text": "Есть дата олимпиады, к которой готовишься?",
    "options": [
        {"key": "none", "label": "Нет даты"},
    ],
    "has_date_input": True,
}

# ══════════════════════════════════════════════════════════════════════════════
# ЧАСТЬ 2. ROUTE_CEILING = min(5, target_level + 1)
# ══════════════════════════════════════════════════════════════════════════════


def compute_route_ceiling(target_level: int) -> int:
    """Вычислить потолок маршрута: min(5, target_level + 1)."""
    return min(5, max(1, int(target_level) + 1))


# ══════════════════════════════════════════════════════════════════════════════
# ЧАСТЬ 4. ЯКОРНЫЕ ЗАДАЧИ — 5 штук из 5 РАЗНЫХ разделов.

# ══════════════════════════════════════════════════════════════════════════════

ANCHOR_PLAN = {
    "mu_shift_correct": +0.55,
    "mu_shift_wrong":   -0.65,
    "sigma_gain":        0.30,
}


DEADLINE_RU = {
    "none": "без дедлайна",
    "soon": "близкий (меньше 2 месяцев)",
    "mid": "средний (2–6 месяцев)",
    "far": "далёкий (больше 6 месяцев)",
}


def compute_deadline_bucket(days_left: int | None) -> str:
    """Автоматическая классификация по days_left (а не вопрос):
    <60 дней soon, 60..180 mid, >180 far."""
    if days_left is None:
        return "none"
    if days_left < 60:
        return "soon"
    if days_left <= 180:
        return "mid"
    return "far"


# ══════════════════════════════════════════════════════════════════════════════
# РЕЗУЛЬТАТ АНКЕТЫ
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OnboardingResult:
    grade: int                        # класс из Q1
    target_level: int                 # цель 1..5 из Q2
    olymp_reach: str                  # ключ ответа Q3
    daily_tasks: int                  # задач в день из Q4
    deadline_date: str | None         # YYYY-MM-DD или None
    days_left: int | None             # дней до дедлайна или None
    deadline_bucket: str              # soon | mid | far | none
    prior_mu: float                   # ожидаемый уровень 1..5
    prior_sigma: float                # неопределённость
    start_level: int                  # стартовый уровень теста
    route_ceiling: int                # потолок маршрута
    test_length: int                  # сколько задач в диагностике
    conflict: bool                    # самооценка разошлась с якорями
    anchors: list = field(default_factory=list)   # [{task_id, section, level, correct}, ...]
    raw: dict[str, Any] = field(default_factory=dict)

    def to_json(self):
        return asdict(self)


def compute_prior(answers: dict[str, Any], anchors: list[dict]) -> OnboardingResult:
    """
    Вычислить итоговый результат анкеты.

    answers — словарь ответов на все вопросы:
        {"grade": "9", "target": "lvl3", "olymp_reach": "muni",
         "load": "m30", "deadline": "2026-12-01"}

    anchors — список результатов якорей:
        [{"correct": True, "section": "algebra", "level": 3, "task_id": 1234}, ...]

    Все поля answers опциональны — при отсутствии используются значения по умолчанию.
    """
    # ── grade (по умолчанию 9) ──────────────────────────────────────
    grade = int(answers.get("grade", 9))

    # ── target_level (по умолчанию lvl3) ────────────────────────────
    target_key = answers.get("target", "lvl3")
    try:
        target_opt = next(o for o in Q2_TARGET["options"] if o["key"] == target_key)
    except StopIteration:
        target_opt = Q2_TARGET["options"][2]  # lvl3 — средний
    target_level = target_opt["target_level"]
    ceiling = compute_route_ceiling(target_level)

    # ── olymp_reach — prior mu/sigma (по умолчанию "none") ──────────
    olymp_key = answers.get("olymp_reach", "none")
    try:
        olymp_opt = next(o for o in Q3_OLYMP_REACH["options"]
                         if o["key"] == olymp_key)
    except StopIteration:
        olymp_opt = Q3_OLYMP_REACH["options"][0]  # none
    mu = olymp_opt["mu"]
    sigma = 1.35 if olymp_opt["w"] >= 0.8 else 1.9

    declared = mu
    for a in anchors:
        ok = a.get("correct", False)
        mu += ANCHOR_PLAN["mu_shift_correct"] if ok else ANCHOR_PLAN["mu_shift_wrong"]
        sigma = max(0.45, sigma - ANCHOR_PLAN["sigma_gain"])

    mu = min(5.0, max(1.0, mu))
    conflict = (declared - mu) >= 1.25 or (mu - declared) >= 1.6
    if conflict:
        sigma = min(1.6, sigma + 0.35)

    # ── load (по умолчанию "m30") ───────────────────────────────────
    load_key = answers.get("load", "m30")
    try:
        load_opt = next(o for o in Q4_LOAD["options"] if o["key"] == load_key)
    except StopIteration:
        load_opt = Q4_LOAD["options"][1]  # m30 — средняя нагрузка

    # ── deadline ────────────────────────────────────────────────────
    deadline_str = answers.get("deadline", "none")
    deadline_date = None
    days_left = None
    if deadline_str and deadline_str != "none":
        try:
            dt = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            days_left = (dt - date.today()).days
            deadline_date = deadline_str
        except (ValueError, TypeError):
            deadline_date = None
            days_left = None
    deadline_bucket = compute_deadline_bucket(days_left)

    start_level = int(min(ceiling, max(1, round(mu - 0.35))))
    test_length = 8 if sigma <= 0.7 else (12 if sigma <= 1.2 else 15)

    return OnboardingResult(
        grade=grade,
        target_level=target_level,
        olymp_reach=olymp_key,
        daily_tasks=load_opt["tasks"],
        deadline_date=deadline_date,
        days_left=days_left,
        deadline_bucket=deadline_bucket,
        prior_mu=round(mu, 2),
        prior_sigma=round(sigma, 2),
        start_level=start_level,
        route_ceiling=ceiling,
        test_length=test_length,
        conflict=conflict,
        anchors=anchors,
        raw={"answers": answers, "anchors": anchors},
    )


# ══════════════════════════════════════════════════════════════════════════════
# ОЧЕРЕДЬ ТЕСТОВ — куратор решает, что ученик проходит.
# ══════════════════════════════════════════════════════════════════════════════

PRIORITY = {
    "diagnostic":   100,
    "section_gap":   80,
    "stale":         55,
    "promote":       40,
    "checkpoint":    30,
}


@dataclass
class TestTask:
    kind: str
    scope: str
    length: int
    level_hint: int
    reason: str
    created: str

    @property
    def priority(self):
        return PRIORITY[self.kind]


def next_test(queue: list[TestTask]) -> TestTask | None:
    if not queue:
        return None
    return sorted(queue, key=lambda t: (-t.priority, t.created))[0]


def build_initial_queue(res: OnboardingResult, today: date) -> list[TestTask]:
    return [TestTask(
        kind="diagnostic",
        scope="all_sections",
        length=res.test_length,
        level_hint=res.start_level,
        reason=f"Первый замер: {res.test_length} задач по всем разделам, "
               f"старт с уровня {res.start_level}. Дальше сложность подстроится сама.",
        created=today.isoformat(),
    )]


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    cases = [
        ({"grade": "9", "target": "lvl3", "olymp_reach": "region",
          "load": "m60", "deadline": "2027-01-15"},
         [{"correct": True, "section": "algebra", "level": 3, "task_id": 1001},
          {"correct": True, "section": "geometry", "level": 4, "task_id": 1002},
          {"correct": False, "section": "combinatorics", "level": 5, "task_id": 1003}]),
        ({"grade": "7", "target": "lvl2", "olymp_reach": "none",
          "load": "m30", "deadline": "none"},
         [{"correct": False, "section": "algebra", "level": 2, "task_id": 2001},
          {"correct": False, "section": "number_theory", "level": 1, "task_id": 2002},
          {"correct": True, "section": "geometry", "level": 2, "task_id": 2003}]),
    ]
    print(f"{'target':>7} {'reach':<8} {'daily':>6} {'deadline':>12} "
          f"{'mu':>5} {'sigma':>6} {'start':>6} {'test':>5} {'ceiling':>8} "
          f"{'conflict':>9}")
    print("-" * 85)
    for a, anc in cases:
        r = compute_prior(a, anc)
        print(f"{r.target_level:>7} {r.olymp_reach:<8} {r.daily_tasks:>6} "
              f"{r.deadline_bucket:>12} {r.prior_mu:>5} {r.prior_sigma:>6} "
              f"{r.start_level:>6} {r.test_length:>5} {r.route_ceiling:>8} "
              f"{str(r.conflict):>9}")
