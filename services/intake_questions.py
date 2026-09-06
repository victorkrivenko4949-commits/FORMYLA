# -*- coding: utf-8 -*-
"""
services/intake_questions.py — Новая анкета входа (P9 Intake).
5 вопросов, затем 5 якорей (без изменений механизма).

Вопросы (ровно в этом порядке):
  1) класс ученика: 5, 6, 7, 8, 9, 10, 11
  2) цель
  3) опыт олимпиад
  4) сколько времени в день готов уделять
  5) слабые разделы (можно выбрать несколько)

Правила обработки:
  - цель "не знаю" -> авто-назначение по классу + опыту (таблица)
  - время -> дневная норма задач: 15мин->5, 30мин->10, час->15, >часа->20
  - слабые разделы -> приоритет при подборе, не ломая разнообразие
  - "не знаю" в слабых разделах -> приоритет не применяется
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════
# ВОПРОС 1: КЛАСС / РОЛЬ
# ══════════════════════════════════════════════════════════════════════

Q1_CLASS = {
    "id": "class",
    "text": "Кто ты?",
    "options": [
        {"key": "teacher", "label": "Я учитель",     "value": "teacher", "role": "teacher"},
        {"key": "parent",  "label": "Я родитель",     "value": "parent",  "role": "parent"},
        {"key": "5",       "label": "5 класс",        "value": 5         },
        {"key": "6",       "label": "6 класс",        "value": 6         },
        {"key": "7",       "label": "7 класс",        "value": 7         },
        {"key": "8",       "label": "8 класс",        "value": 8         },
        {"key": "9",       "label": "9 класс",        "value": 9         },
        {"key": "10",      "label": "10 класс",       "value": 10        },
        {"key": "11",      "label": "11 класс",       "value": 11        },
    ],
}

# ══════════════════════════════════════════════════════════════════════
# ВОПРОС 2: ЦЕЛЬ
# ══════════════════════════════════════════════════════════════════════

Q2_GOAL = {
    "id": "goal",
    "text": "Какая у тебя цель?",
    "options": [
        {"key": "school_muni",   "label": "Победить в школьном или муниципальном этапе"},
        {"key": "region",        "label": "Выйти на региональный этап"},
        {"key": "region_prize",  "label": "Взять призёра регионального"},
        {"key": "perechnevye",   "label": "Готовиться к перечневым олимпиадам"},
        {"key": "just_grow",     "label": "Просто регулярно решать и расти"},
        {"key": "dont_know",     "label": "Не знаю"},
    ],
}

# ══════════════════════════════════════════════════════════════════════
# ВОПРОС 3: ОПЫТ ОЛИМПИАД
# ══════════════════════════════════════════════════════════════════════

Q3_EXPERIENCE = {
    "id": "experience",
    "text": "Какой у тебя опыт участия в олимпиадах?",
    "options": [
        {"key": "none",          "label": "Не участвовал"},
        {"key": "participated",  "label": "Участвовал, без результатов"},
        {"key": "school_prize",  "label": "Есть призовые места в школьном или муниципальном"},
        {"key": "region_plus",   "label": "Есть результаты на региональном и выше"},
    ],
}

# ══════════════════════════════════════════════════════════════════════
# ВОПРОС 4: ВРЕМЯ В ДЕНЬ
# ══════════════════════════════════════════════════════════════════════

Q4_TIME = {
    "id": "time",
    "text": "Сколько времени в день готов уделять занятиям?",
    "options": [
        {"key": "m30",   "label": "30 минут",    "tasks_per_day": 5},
        {"key": "m60",   "label": "Час",          "tasks_per_day": 8},
        {"key": "m90",   "label": "Больше часа",  "tasks_per_day": 10},
    ],
}

# ══════════════════════════════════════════════════════════════════════
# ВОПРОС 5: СЛАБЫЕ РАЗДЕЛЫ (можно выбрать несколько)
# ══════════════════════════════════════════════════════════════════════

Q5_WEAK_SECTIONS = {
    "id": "weak_sections",
    "text": "Какие разделы даются сложнее всего? Можно выбрать несколько.",
    "multi": True,
    "options": [
        {"key": "algebra",        "label": "Алгебра"},
        {"key": "number_theory",  "label": "Теория чисел"},
        {"key": "geometry",       "label": "Геометрия"},
        {"key": "combinatorics",  "label": "Комбинаторика"},
        {"key": "logic",          "label": "Логика"},
        {"key": "dont_know",      "label": "Не знаю"},
    ],
}

# ══════════════════════════════════════════════════════════════════════
# ТАБЛИЦА АВТО-НАЗНАЧЕНИЯ ЦЕЛИ (когда цель = "не знаю")
# ══════════════════════════════════════════════════════════════════════

# Формат: (min_class, max_class, experience) -> goal_key
# Логика:
#   - Младшие классы (5-6) без опыта -> "just_grow"
#   - Средние классы (7-8) без опыта -> "school_muni"
#   - Старшие (9-11) без опыта -> "region"
#   - С опытом любого уровня -> на ступень выше базы
AUTO_GOAL_TABLE: List[Tuple[int, int, str, str]] = [
    # (min_class, max_class, experience_key, assigned_goal)
    # 5-6 класс
    (5, 6, "none",           "just_grow"),
    (5, 6, "participated",   "school_muni"),
    (5, 6, "school_prize",   "region"),
    (5, 6, "region_plus",    "region_prize"),
    # 7-8 класс
    (7, 8, "none",           "school_muni"),
    (7, 8, "participated",   "region"),
    (7, 8, "school_prize",   "region_prize"),
    (7, 8, "region_plus",    "perechnevye"),
    # 9 класс
    (9, 9, "none",           "region"),
    (9, 9, "participated",   "region_prize"),
    (9, 9, "school_prize",   "perechnevye"),
    (9, 9, "region_plus",    "perechnevye"),
    # 10-11 класс
    (10, 11, "none",           "region"),
    (10, 11, "participated",   "region_prize"),
    (10, 11, "school_prize",   "perechnevye"),
    (10, 11, "region_plus",    "perechnevye"),
]


def assign_goal(class_level: int, experience: str) -> Tuple[str, bool]:
    """Авто-назначить цель по классу и опыту.
    
    Returns:
        (goal_key, auto_assigned: True)
    """
    for min_c, max_c, exp_key, goal_key in AUTO_GOAL_TABLE:
        if min_c <= class_level <= max_c and exp_key == experience:
            return goal_key, True
    # Fallback (не должно случаться)
    return "just_grow", True


# ══════════════════════════════════════════════════════════════════════
# ЯКОРНЫЙ ПЛАН (без изменений из P4)
# ══════════════════════════════════════════════════════════════════════

ANCHOR_PLAN = {
    "mu_shift_correct": +0.55,
    "mu_shift_wrong":   -0.65,
    "sigma_gain":        0.30,
}

ANCHOR_SECTION_ORDER = ('algebra', 'number_theory', 'geometry', 'combinatorics', 'logic')

CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

SECTION_RU = {
    'algebra': 'алгебра',
    'geometry': 'геометрия',
    'combinatorics': 'комбинаторика',
    'logic': 'логика',
    'number_theory': 'теория чисел',
}

# ══════════════════════════════════════════════════════════════════════
# РЕЗУЛЬТАТ АНКЕТЫ
# ══════════════════════════════════════════════════════════════════════


@dataclass
class IntakeResult:
    """Результат новой анкеты входа."""
    class_level: int                    # 5..11
    goal: str                           # ключ цели (school_muni/region/...)
    goal_auto: bool                     # True если цель назначена автоматически
    experience: str                     # ключ опыта
    daily_tasks: int                    # дневная норма (5/10/15/20)
    weak_sections: List[str]            # список слабых разделов (может быть пустым)
    weak_priority: bool                 # True если приоритет слабых применяется
    prior_mu: float                     # ожидаемый уровень (из якорей)
    prior_sigma: float                  # неопределённость
    anchors: List[dict] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_json(self):
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════
# ВЫЧИСЛЕНИЕ PRIOR (как в onboarding_tree.py, без изменений механики)
# ══════════════════════════════════════════════════════════════════════

# mu из опыта — соответствует старым Q3_OLYMP_REACH значениям
EXPERIENCE_PRIOR = {
    "none":          {"mu": 1.6, "w": 0.9},
    "participated":  {"mu": 2.1, "w": 0.9},
    "school_prize":  {"mu": 2.9, "w": 1.0},
    "region_plus":   {"mu": 3.9, "w": 1.1},
}


def compute_prior(answers: Dict[str, Any], anchors: List[Dict]) -> IntakeResult:
    """Вычислить итоговый результат анкеты.
    
    answers — словарь ответов:
        {"class": "9", "goal": "region", "experience": "school_prize",
         "time": "m60", "weak_sections": ["geometry", "logic"]}
    
    anchors — список результатов якорей:
        [{"correct": True, "section": "algebra", "level": 3, "task_id": 1234}, ...]
    """
    # ── Класс ─────────────────────────────────────────────────────
    class_level = int(answers.get("class", 9))

    # ── Цель ──────────────────────────────────────────────────────
    goal = answers.get("goal", "dont_know")
    goal_auto = False
    if goal == "dont_know":
        exp_for_goal = answers.get("experience", "none")
        goal, goal_auto = assign_goal(class_level, exp_for_goal)

    # ── Опыт -> prior mu/sigma ─────────────────────────────────────
    exp_key = answers.get("experience", "none")
    exp_opt = EXPERIENCE_PRIOR.get(exp_key, EXPERIENCE_PRIOR["none"])
    mu = exp_opt["mu"]
    sigma = 1.35 if exp_opt["w"] >= 0.8 else 1.9

    declared = mu
    for a in anchors:
        ok = a.get("correct", False)
        mu += ANCHOR_PLAN["mu_shift_correct"] if ok else ANCHOR_PLAN["mu_shift_wrong"]
        sigma = max(0.45, sigma - ANCHOR_PLAN["sigma_gain"])

    mu = min(4.0, max(1.0, mu))

    # ── Время -> дневная норма ─────────────────────────────────────
    time_key = answers.get("time", "m30")
    for opt in Q4_TIME["options"]:
        if opt["key"] == time_key:
            daily_tasks = opt["tasks_per_day"]
            break
    else:
        daily_tasks = 10  # default m30

    # ── Слабые разделы ────────────────────────────────────────────
    weak_raw = answers.get("weak_sections", [])
    if isinstance(weak_raw, str):
        weak_raw = [w.strip() for w in weak_raw.split(',') if w.strip()]
    elif isinstance(weak_raw, list):
        # Flatten any nested comma-joined strings within list elements
        flat = []
        for item in weak_raw:
            if isinstance(item, str) and ',' in item:
                flat.extend([w.strip() for w in item.split(',') if w.strip()])
            else:
                flat.append(str(item).strip())
        weak_raw = flat
    weak_sections = [w for w in weak_raw if w != "dont_know"]
    weak_priority = len(weak_sections) > 0 and "dont_know" not in weak_raw

    return IntakeResult(
        class_level=class_level,
        goal=goal,
        goal_auto=goal_auto,
        experience=exp_key,
        daily_tasks=daily_tasks,
        weak_sections=weak_sections,
        weak_priority=weak_priority,
        prior_mu=round(mu, 2),
        prior_sigma=round(sigma, 2),
        anchors=anchors,
        raw={"answers": answers, "anchors": anchors},
    )
