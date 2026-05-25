# -*- coding: utf-8 -*-
"""Subject classification for FORMYLA adaptive tasks.

Single source of truth that maps a task (from new JSON dataset
``formyla_adaptive_full_with_full_level8_by_topics.json`` or from
``adaptive_tasks`` rows) to a canonical *subject* key:

    algebra, geometry, combinatorics, number_theory, logic, set_theory

These keys mirror the per-grade domain registry in
:mod:`models_grade` (``GRADE_DOMAINS``) for grades 9–11, and are the
keys exposed in the UI for selecting an adaptive-test theme.

The classifier is deterministic and *never* mixes subjects on fallback:
if classification fails it returns ``None`` (the caller must surface a
"no tasks for this filter" error to the user, NOT widen the search to a
different subject).

Rules
-----
1.  If the input dict has an explicit ``subject`` (or ``subject_key``)
    that is one of the canonical keys (or maps cleanly via
    :data:`SUBJECT_ALIASES`), use it.
2.  Otherwise, look at the task ``id`` prefix (``algebra_…``,
    ``geometry_…``, ``set_theory_…``, …).
3.  Otherwise, look at ``domain`` (the per-grade school-curriculum key
    used in :mod:`models_grade`).
4.  Otherwise, scan ``topic`` text against curated keyword lists.

Step 4 only ever produces algebra / geometry / number_theory /
combinatorics / logic / set_theory.  If nothing matches, the function
returns ``None``.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

# ─── Canonical subject keys ───────────────────────────────────────────────
ALGEBRA = "algebra"
GEOMETRY = "geometry"
COMBINATORICS = "combinatorics"
NUMBER_THEORY = "number_theory"
LOGIC = "logic"
SET_THEORY = "set_theory"

ALL_SUBJECTS = (ALGEBRA, GEOMETRY, COMBINATORICS, NUMBER_THEORY, LOGIC, SET_THEORY)

# Subjects that share a UI label.  e.g. older datasets used "math" for
# everything in grades 5–6; we treat it as "unknown" and rely on rules.
SUBJECT_ALIASES = {
    "algebra": ALGEBRA,
    "алгебра": ALGEBRA,
    "geometry": GEOMETRY,
    "геометрия": GEOMETRY,
    "combinatorics": COMBINATORICS,
    "комбинаторика": COMBINATORICS,
    "number_theory": NUMBER_THEORY,
    "теория чисел": NUMBER_THEORY,
    "logic": LOGIC,
    "логика": LOGIC,
    "set_theory": SET_THEORY,
    "теория множеств": SET_THEORY,
}

# Per-grade school domain → subject (for grades 5–8 where the JSON file
# uses subject="math" for everything).
DOMAIN_TO_SUBJECT = {
    # 5 класс
    "natural_numbers":              ALGEBRA,
    "fractions_decimals_percent":   ALGEBRA,
    "geometry_measurement":         GEOMETRY,
    "combinatorics_school":         COMBINATORICS,
    "logic_olympiad_intro":         LOGIC,
    # 6 класс
    "divisibility":                 NUMBER_THEORY,
    "fractions_ratio_percent":      ALGEBRA,
    "integers_coordinates":         ALGEBRA,
    "geometry_6":                   GEOMETRY,
    "olympiad_logic_combinatorics": LOGIC,
    # 7 класс
    "algebra_expressions_equations":  ALGEBRA,
    "linear_functions_intro":         ALGEBRA,
    "geometry_7_lines_triangles":     GEOMETRY,
    "number_theory_combinatorics_7":  NUMBER_THEORY,
    "olympiad_logic_7":               LOGIC,
    "olympiad_logic_number_theory":   LOGIC,
    "functions_inequalities":         ALGEBRA,
    # 8 класс
    "algebra_roots_quadratics_intro":       ALGEBRA,
    "algebra_roots_quadratics":             ALGEBRA,
    "geometry_8_quadrilaterals_pythagoras": GEOMETRY,
    "geometry_8_planimetry":                GEOMETRY,
    "functions_inequalities_8":             ALGEBRA,
    "counting_probability_8":               COMBINATORICS,
    "combinatorics_probability":            COMBINATORICS,
    "olympiad_logic_8":                     LOGIC,
    # 9–11 классы — однозначные
    "algebra":         ALGEBRA,
    "geometry":        GEOMETRY,
    "combinatorics":   COMBINATORICS,
    "number_theory":   NUMBER_THEORY,
    "logic":           LOGIC,
    "set_theory":      SET_THEORY,
    # синонимы, встречающиеся в файле
    "stereometry":              GEOMETRY,
    "circles_measurement":      GEOMETRY,
    "polynomials":              ALGEBRA,
    "exponential_logarithmic":  ALGEBRA,
    "trigonometry":             ALGEBRA,
    "calculus":                 ALGEBRA,
    "inequalities":             ALGEBRA,
    "binomial_coefficients":    COMBINATORICS,
    "extremal_combinatorics":   COMBINATORICS,
    "pigeonhole":               COMBINATORICS,
    "graph_theory":             COMBINATORICS,
    "modular_arithmetic":       NUMBER_THEORY,
    "invariants":               LOGIC,
}

# ─── Keyword-based fallback (last resort).
# ВАЖНО: эти списки только сужают выбор, никогда не приводят к
# смешиванию субъектов — если ни один не сработал, классификатор
# возвращает None.
GEOMETRY_KW = (
    "геометр", "треугольник", "окружност", "параллел", "перпендикуляр",
    "угол ", "углы", "площад", "объ", "конус", "куб", "пирамид",
    "призм", "сфер", "шар", "цилиндр", "стереометр", "планиметр",
    "медиан", "биссектрис", "высот", "тетраэдр", "многогранник",
    "четырехугольник", "ромб", "трапец", "вписанн", "описанн",
    "вектор", "координат",
)

ALGEBRA_KW = (
    "алгебр", "уравнен", "неравенств", "функц", "производн", "интеграл",
    "многочлен", "парабол", "логарифм", "показательн", "квадратич",
    "корн", "виет", "трехчлен", "степен", "прогресс", "тригонометр",
    "выражени", "одночлен", "формул", "процент", "пропорц", "график",
    "оптимизац", "параметр", "движен",  # текстовые/движение → алгебра
)

NUMBER_THEORY_KW = (
    "теория чисел", "делимост", "остатк", "нод", "нок", "диофант",
    "сравнен", "ферма", "эйлер", "простые", "составные", "признаки делимости",
    "цепные дроби", "алгоритм евклида",
)

COMBINATORICS_KW = (
    "комбинатор", "вероятност", "перестановк", "размещен", "сочетан",
    "правило суммы", "правило произведен", "правило умножения",
    "принцип дирихле", "дирихле", "граф", "рамсе", "хроматическ",
    "счет", "подсчёт", "подсчет",
)

LOGIC_KW = (
    "логик", "рыцар", "лжец", "инвариант", "взвешивани", "переливани",
    "стратеги", "игр", "тактик",
)

SET_THEORY_KW = (
    "множеств", "пересечен", "объединен", "включен", "формула включ",
    "венна", "характеристическ",
)

# Порядок проверки: геометрию проверяем ПЕРВОЙ, чтобы геометрические
# слова не съели топик вроде "координатная геометрия" (там "координат"
# тянется и к алгебре).
KEYWORD_RULES = (
    (GEOMETRY,      GEOMETRY_KW),
    (SET_THEORY,    SET_THEORY_KW),
    (LOGIC,         LOGIC_KW),
    (COMBINATORICS, COMBINATORICS_KW),
    (NUMBER_THEORY, NUMBER_THEORY_KW),
    (ALGEBRA,       ALGEBRA_KW),
)


# ─── ID prefix lookup ─────────────────────────────────────────────────────
ID_PREFIXES = {
    "algebra":       ALGEBRA,
    "geometry":      GEOMETRY,
    "combinatorics": COMBINATORICS,
    "number":        NUMBER_THEORY,        # "number_theory_..."
    "logic":         LOGIC,
    "set":           SET_THEORY,           # "set_theory_..."
}


def _id_prefix(task_id: Any) -> str:
    s = str(task_id or "")
    if not s:
        return ""
    return s.split("_", 1)[0]


def _normalize_alias(value: Any) -> Optional[str]:
    if not value:
        return None
    key = str(value).strip().lower()
    return SUBJECT_ALIASES.get(key)


def classify_subject(task: Mapping[str, Any]) -> Optional[str]:
    """Classify ``task`` into one of :data:`ALL_SUBJECTS` or return None.

    Accepts both:
      * raw dicts from the new JSON dataset
        (keys: ``subject``, ``domain``, ``topic``, ``id`` …);
      * dicts produced from ``adaptive_tasks`` rows
        (keys: ``subject``, ``topic``, ``task_text``, ``subtopic`` …).

    Returns one of:
        "algebra", "geometry", "combinatorics", "number_theory",
        "logic", "set_theory", or None when unsure.
    """
    # 1. Explicit canonical subject
    explicit = _normalize_alias(task.get("subject")) or _normalize_alias(task.get("subject_key"))
    if explicit in ALL_SUBJECTS:
        return explicit

    # 2. ID prefix
    prefix = _id_prefix(task.get("id"))
    if prefix in ID_PREFIXES:
        return ID_PREFIXES[prefix]

    # 3. Domain
    domain = str(task.get("domain") or "").strip().lower()
    if domain in DOMAIN_TO_SUBJECT:
        return DOMAIN_TO_SUBJECT[domain]

    # 4. Topic / subtopic / тэги
    haystack_parts = []
    for k in ("topic", "subtopic", "tags", "domain"):
        v = task.get(k)
        if isinstance(v, str):
            haystack_parts.append(v.lower())
        elif isinstance(v, (list, tuple)):
            haystack_parts.extend(str(x).lower() for x in v)
    haystack = " ".join(haystack_parts)
    if haystack:
        for subject, keywords in KEYWORD_RULES:
            for kw in keywords:
                if kw in haystack:
                    return subject

    return None


# ─── Russian display labels ──────────────────────────────────────────────
SUBJECT_LABEL_RU = {
    ALGEBRA:       "Алгебра",
    GEOMETRY:      "Геометрия",
    COMBINATORICS: "Комбинаторика",
    NUMBER_THEORY: "Теория чисел",
    LOGIC:         "Логика",
    SET_THEORY:    "Теория множеств",
}


def subject_label_ru(subject: Optional[str]) -> str:
    if not subject:
        return ""
    return SUBJECT_LABEL_RU.get(subject, subject)


# ─── URL/UI key → canonical subject ──────────────────────────────────────
# Часть страниц использует ключи 'kl_movement', 'knights_liars', 'movement'
# и т.п.  Для адаптивного теста по предметной области они НЕ подходят
# (это под-темы, а не предмет), и фильтрация по `subject` для них
# возвращает None — UI обязан в этом случае показать «нет задач по
# выбранному фильтру», а не подмешивать произвольную алгебру/геометрию.
URL_TOPIC_TO_SUBJECT = {
    "algebra":        ALGEBRA,
    "geometry":       GEOMETRY,
    "combinatorics":  COMBINATORICS,
    "number_theory":  NUMBER_THEORY,
    "logic":          LOGIC,
    "set_theory":     SET_THEORY,
}


def url_topic_to_subject(topic: Optional[str]) -> Optional[str]:
    """Возвращает каноническое имя предмета по URL-ключу темы.

    Для не-предметных тем (`movement`, `knights_liars`, …) возвращает
    None — это сигнал вызывающему коду, что фильтра по предмету нет
    и нужно использовать keyword-фильтр по topic, но без расширения
    на другие предметы.
    """
    if not topic:
        return None
    return URL_TOPIC_TO_SUBJECT.get(str(topic).strip().lower())


__all__ = [
    "ALL_SUBJECTS",
    "ALGEBRA", "GEOMETRY", "COMBINATORICS",
    "NUMBER_THEORY", "LOGIC", "SET_THEORY",
    "SUBJECT_ALIASES", "DOMAIN_TO_SUBJECT",
    "SUBJECT_LABEL_RU", "subject_label_ru",
    "URL_TOPIC_TO_SUBJECT", "url_topic_to_subject",
    "classify_subject",
]
