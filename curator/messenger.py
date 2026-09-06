# -*- coding: utf-8 -*-
"""
curator/messenger.py — Факты, сообщения и проверка куратора (P10).

Функции:
  get_student_facts(user_id)     -> dict фактов на сегодня (только данные, без текста)
  build_curator_message(facts)   -> str | None (короткое обращение из фактов)
  validate_message(message, facts) -> (bool, str) — проверка перед показом
  get_curator_card(user_id)      -> dict | None (готовые данные для HTML-карточки)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from models import db
from models_curator import CuratorState
from daily_tasks.models import DailyTaskSet, DailyTaskItem

logger = logging.getLogger(__name__)

# ─── TZ ───────────────────────────────────────────────────────────────────────
MSK = timezone(timedelta(hours=3))


def _today() -> date:
    return datetime.now(MSK).date()


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 2. ФАКТЫ — get_student_facts(user_id)
# ═══════════════════════════════════════════════════════════════════════════════


def get_student_facts(user_id: int) -> Dict[str, Any]:
    """Собрать набор фактов по ученику на сегодня.

    Возвращает только данные, без текста. Ключи:
      - cycle_day, slice_done, slice_total
      - today_total, today_solved, today_correct, today_pending
      - debt_size, debt_days_count, debt_burns_tomorrow
      - streak_days, missed_days_last_week
      - level_now, level_week_ago, level_delta
      - weakest_sections: [{section, accuracy_pct, total_attempts}, ...]
      - tomorrow_subtopic, tomorrow_section
      - method_code, method_name, method_source_line
      - grade
    """
    facts: Dict[str, Any] = {
        # ── Цикл ──────────────────────────────────────────────────────────
        "cycle_day": None,
        "slice_done": False,
        "slice_total": 0,

        # ── Сегодняшний набор ─────────────────────────────────────────────
        "today_total": 0,
        "today_solved": 0,
        "today_correct": 0,
        "today_pending": 0,

        # ── Долг ──────────────────────────────────────────────────────────
        "debt_size": 0,
        "debt_days_count": 0,
        "debt_burns_tomorrow": 0,

        # ── Посещаемость ──────────────────────────────────────────────────
        "streak_days": 0,
        "missed_days_last_week": 0,

        # ── Уровень ───────────────────────────────────────────────────────
        "level_now": None,
        "level_week_ago": None,
        "level_delta": None,

        # ── Слабые разделы ────────────────────────────────────────────────
        "weakest_sections": [],

        # ── Завтрашняя тема + метод ───────────────────────────────────────
        "tomorrow_subtopic": None,
        "tomorrow_section": None,
        "method_code": None,
        "method_name": None,
        "method_source_line": None,

        # ── Класс ─────────────────────────────────────────────────────────
        "grade": None,
    }

    today = _today()

    # ── 1. Класс ученика ───────────────────────────────────────────────────
    grade = _get_grade(user_id)
    facts["grade"] = grade

    # ── 2. Цикл (monthly_cycle) ────────────────────────────────────────────
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle = get_cycle_info(user_id)
        if cycle.get("active"):
            facts["cycle_day"] = cycle.get("day_index")
            facts["slice_total"] = len(cycle.get("themes", []))
            facts["slice_done"] = (
                cycle.get("current_theme") in cycle.get("done_themes", [])
                if cycle.get("current_theme")
                else False
            )
    except Exception as e:
        logger.warning("messenger: cycle_info failed: %s", e)

    # ── 3. Сегодняшний набор задач ─────────────────────────────────────────
    daily_set = DailyTaskSet.query.filter_by(
        user_id=user_id, target_date=today,
    ).first()
    if daily_set:
        items = DailyTaskItem.query.filter_by(daily_set_id=daily_set.id).all()
        facts["today_total"] = len(items)
        answered = [i for i in items if i.is_correct is not None]
        correct = [i for i in answered if i.is_correct is True]
        facts["today_solved"] = len(answered)
        facts["today_correct"] = len(correct)
        facts["today_pending"] = len(items) - len(answered)

    # ── 4. Долг ────────────────────────────────────────────────────────────
    debt_items = _get_active_debt(user_id)
    facts["debt_size"] = len(debt_items)
    if debt_items:
        debt_days = set()
        tomorrow = today + timedelta(days=1)
        burns = 0
        for item in debt_items:
            parent = DailyTaskSet.query.get(item.daily_set_id)
            if parent:
                debt_days.add(parent.target_date)
            if item.debt_until and item.debt_until <= tomorrow:
                burns += 1
        facts["debt_days_count"] = len(debt_days)
        facts["debt_burns_tomorrow"] = burns

    # ── 5. Серия (streak) ──────────────────────────────────────────────────
    facts["streak_days"] = _calc_streak(user_id)

    # ── 6. Пропуски за последнюю неделю ────────────────────────────────────
    facts["missed_days_last_week"] = _calc_missed_days(user_id, 7)

    # ── 7. Уровень ─────────────────────────────────────────────────────────
    try:
        from services.level_engine import get_state
        state = get_state(user_id)
        facts["level_now"] = state.get("level")
        # Ищем уровень недельной давности в ProgressLog
        week_ago_level = _get_level_week_ago(user_id)
        facts["level_week_ago"] = week_ago_level
        if facts["level_now"] is not None and week_ago_level is not None:
            facts["level_delta"] = facts["level_now"] - week_ago_level
    except Exception as e:
        logger.warning("messenger: level_engine failed: %s", e)

    # ── 8. Слабые разделы (по answer_log level_by_section) ─────────────────
    try:
        facts["weakest_sections"] = _get_weakest_sections(user_id)
    except Exception as e:
        logger.warning("messenger: weakest_sections failed: %s", e)

    # ── 9. Завтрашняя тема ─────────────────────────────────────────────────
    try:
        tomorrow_info = _get_tomorrow_info(user_id, grade)
        facts["tomorrow_subtopic"] = tomorrow_info.get("subtopic")
        facts["tomorrow_section"] = tomorrow_info.get("section")
    except Exception as e:
        logger.warning("messenger: tomorrow_info failed: %s", e)

    # ── 10. Метод из methods_catalog_105.json ──────────────────────────────
    if facts["tomorrow_section"] and grade:
        method = _pick_method(facts["tomorrow_section"], grade)
        if method:
            facts["method_code"] = method["code"]
            facts["method_name"] = method["name"]
            facts["method_source_line"] = method["source"]

    return facts


# ─── Вспомогательные функции для фактов ─────────────────────────────────────


def _get_grade(user_id: int) -> Optional[int]:
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs and cs.grade:
        return cs.grade
    try:
        from models import User
        u = db.session.get(User, user_id)
        if u and hasattr(u, "preferred_grade") and u.preferred_grade:
            return u.preferred_grade
    except Exception:
        pass
    return None


def _get_active_debt(user_id: int) -> List[DailyTaskItem]:
    debt_set_ids = (
        db.session.query(DailyTaskSet.id)
        .filter(DailyTaskSet.user_id == user_id)
        .subquery()
    )
    return (
        DailyTaskItem.query
        .filter(
            DailyTaskItem.daily_set_id.in_(db.session.query(debt_set_ids.c.id)),
            DailyTaskItem.debt_status == "active",
        )
        .all()
    )


def _calc_streak(user_id: int) -> int:
    """Дни подряд с активностью (от сегодня назад)."""
    today = _today()
    try:
        from curator.models import ProgressLog
        logs = (
            ProgressLog.query
            .filter_by(user_id=user_id)
            .filter(ProgressLog.log_date <= today)
            .order_by(ProgressLog.log_date.desc())
            .all()
        )
        if not logs:
            return 0
        streak = 0
        expected = today
        for log in logs:
            if log.log_date == expected:
                if log.tasks_total and log.tasks_total > 0:
                    streak += 1
                expected -= timedelta(days=1)
            elif log.log_date < expected:
                break
        return streak
    except Exception:
        pass

    # Fallback: считаем по DailyTaskItem
    sets = (
        DailyTaskSet.query
        .filter_by(user_id=user_id)
        .filter(DailyTaskSet.target_date <= today)
        .order_by(DailyTaskSet.target_date.desc())
        .all()
    )
    if not sets:
        return 0
    streak = 0
    expected = today
    for ds in sets:
        if ds.target_date == expected:
            items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).all()
            if items and any(i.is_correct is not None for i in items):
                streak += 1
            expected -= timedelta(days=1)
        elif ds.target_date < expected:
            break
    return streak


def _calc_missed_days(user_id: int, window: int = 7) -> int:
    """Сколько дней из последних N дней без активности."""
    today = _today()
    active_dates = set()
    try:
        from curator.models import ProgressLog
        since = today - timedelta(days=window - 1)
        logs = (
            ProgressLog.query
            .filter_by(user_id=user_id)
            .filter(ProgressLog.log_date >= since)
            .filter(ProgressLog.tasks_total > 0)
            .all()
        )
        for log in logs:
            active_dates.add(log.log_date)
    except Exception:
        pass

    # Дополняем из DailyTaskSet
    since = today - timedelta(days=window - 1)
    sets = (
        DailyTaskSet.query
        .filter_by(user_id=user_id)
        .filter(DailyTaskSet.target_date >= since)
        .all()
    )
    for ds in sets:
        items = DailyTaskItem.query.filter_by(daily_set_id=ds.id).all()
        if items and any(i.is_correct is not None for i in items):
            active_dates.add(ds.target_date)

    missed = 0
    for i in range(window):
        d = today - timedelta(days=i)
        if d not in active_dates:
            missed += 1
    return missed


def _get_level_week_ago(user_id: int) -> Optional[int]:
    """Уровень ученика ~7 дней назад (из ProgressLog.profile_snapshot)."""
    try:
        from curator.models import ProgressLog
        week_ago = _today() - timedelta(days=7)
        log = (
            ProgressLog.query
            .filter_by(user_id=user_id)
            .filter(ProgressLog.log_date <= week_ago)
            .order_by(ProgressLog.log_date.desc())
            .first()
        )
        if log and log.profile_snapshot:
            snapshot = log.profile_snapshot_dict
            # Пробуем вытащить уровень из snapshot
            levels = [
                v.get("level", v.get("pct", None))
                for v in snapshot.values()
                if isinstance(v, dict)
            ]
            if levels:
                return int(round(sum(levels) / len(levels)))
    except Exception:
        pass
    return None


def _get_weakest_sections(user_id: int) -> List[Dict[str, Any]]:
    """Разделы с самой низкой долей верных ответов (≤ 3 худших).

    Важное правило: раздел, у которого mu на максимуме (≈ 100% верных),
    НЕ может считаться «слабым» — иначе при единственном измеренном
    разделе с mu=4.0 карточка показывала бы абсурд «Слабый раздел:
    Алгебра — 100%». Такие разделы отбрасываются.
    """
    try:
        from services.level_engine import get_state
        state = get_state(user_id)
        by_section = state.get("by_section", {})
        if not by_section:
            return []

        # by_section: {section: {mu, sigma, n}, ...}
        entries = []
        for sec, data in by_section.items():
            if not isinstance(data, dict):
                continue
            mu = data.get("mu")
            n = data.get("n", 0)
            if mu is None or n == 0:
                continue
            try:
                mu_f = float(mu)
            except (TypeError, ValueError):
                continue
            # Раздел с mu на максимуме (>= 3.99) = ~100% верных — не слабый.
            if mu_f >= 3.99:
                continue
            # mu (1..4) -> переводим в проценты: (mu-1)/3 * 100
            accuracy_pct = round((mu_f - 1) / 3 * 100, 1)
            entries.append({
                "section": sec,
                "accuracy_pct": accuracy_pct,
                "total_attempts": n,
                "mu": mu_f,
            })

        entries.sort(key=lambda x: x["accuracy_pct"])
        return entries[:3]  # до 3 худших
    except Exception:
        return []


def _get_tomorrow_info(user_id: int, grade: Optional[int]) -> Dict[str, Any]:
    """Определить завтрашнюю подтему и раздел."""
    from services.theme_registry import section_of_theme, theme_title as _theme_title

    # Пробуем через monthly_cycle
    try:
        from curator.monthly_cycle import get_cycle_info
        cycle = get_cycle_info(user_id)
        if cycle.get("active") and cycle.get("themes"):
            day_idx = cycle.get("day_index", 1)
            themes = cycle.get("themes", [])
            done = cycle.get("done_themes", [])
            # Завтрашняя: day_idx (или day_idx+1 если сегодня done)
            next_idx = day_idx if cycle.get("current_theme") not in done else day_idx
            if next_idx <= len(themes):
                tid = themes[next_idx - 1]
                return {
                    "subtopic": tid,
                    "section": section_of_theme(tid),
                }
    except Exception:
        pass

    # Fallback: ближайший theme_id по grade
    if grade:
        try:
            from services.theme_registry import themes_of_grade
            all_t = themes_of_grade(grade)
            if all_t:
                # Берём следующий непройденный
                tid = all_t[0]  # fallback
                return {
                    "subtopic": tid,
                    "section": section_of_theme(tid),
                }
        except Exception:
            pass

    return {}


def _pick_method(section: str, grade: int) -> Optional[Dict[str, Any]]:
    """Подобрать метод из methods_catalog_105.json по разделу и классу.

    Возвращает dict с code, name, source или None.
    Ничего не выдумывается — строго из каталога.
    """
    catalog_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "olympiads", "methods_catalog_105.json",
    )
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            methods = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("messenger: cannot load methods_catalog_105.json: %s", e)
        return None

    # Маппинг section slug -> буква раздела в каталоге
    section_map = {
        "algebra": "A",
        "geometry": "G",
        "combinatorics": "C",
        "logic": "L",
        "number_theory": "N",
    }
    target_letter = section_map.get(section)

    candidates = []
    for m in methods:
        m_section = m.get("section", "")
        m_grades = m.get("grades", [])
        # Совпадение по разделу (первая буква кода или поле section)
        if target_letter and m_section == target_letter:
            if grade in m_grades:
                candidates.append(m)
        elif not target_letter:
            # Без маппинга — берём все подходящие по классу
            if grade in m_grades:
                candidates.append(m)

    if not candidates:
        return None

    # Сортируем по difficulty_level (простые первыми)
    candidates.sort(key=lambda m: m.get("difficulty_level", 4))
    best = candidates[0]

    return {
        "code": best.get("method_code", ""),
        "name": best.get("method_name", ""),
        "source": f"methods_catalog_105.json: method_code={best.get('method_code', '')}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 3. СООБЩЕНИЯ — build_curator_message(facts)
# ═══════════════════════════════════════════════════════════════════════════════


def build_curator_message(facts: Dict[str, Any]) -> Optional[str]:
    """Построить короткое обращение куратора строго из фактов.

    Правила:
      - Никаких выдуманных чисел, адресов страниц, названий
      - Если факта нет — часть не пишется
      - Не больше трёх предложений
      - Без эмодзи, обращение на «ты», спокойный тон
      - Метод: «D1 Делимость» (код + название)

    Returns:
        str | None — сообщение или None если нет поводов.
    """
    triggers: List[Tuple[int, str]] = []

    # Повод 1: вчера ничего не решено
    yesterday_solved = _yesterday_solved(facts)
    if yesterday_solved == 0 and facts.get("today_total", 0) > 0:
        triggers.append((10, "yesterday_zero"))

    # Повод 2: есть долг и часть сгорит завтра
    if facts.get("debt_size", 0) > 0 and facts.get("debt_burns_tomorrow", 0) > 0:
        triggers.append((20, "debt_burns"))

    # Повод 3: срез не закончен
    if (facts.get("cycle_day") is not None
            and not facts.get("slice_done", False)
            and facts.get("slice_total", 0) > 0):
        triggers.append((30, "slice_pending"))

    # Повод 4: уровень вырос
    if facts.get("level_delta") is not None and facts["level_delta"] > 0:
        triggers.append((40, "level_up"))

    # Повод 5: уровень просел
    if facts.get("level_delta") is not None and facts["level_delta"] < 0:
        triggers.append((50, "level_down"))

    # Повод 6: слабый раздел
    if facts.get("weakest_sections"):
        triggers.append((60, "weak_section"))

    # Повод 7: завтрашняя тема и метод
    if facts.get("tomorrow_subtopic") and facts.get("method_code"):
        triggers.append((70, "tomorrow_method"))

    # Повод 8: есть долг вообще
    if facts.get("debt_size", 0) > 0 and not any(t[1] == "debt_burns" for t in triggers):
        triggers.append((15, "debt_exists"))

    # Повод 9: сегодня ничего не решено
    if facts.get("today_total", 0) > 0 and facts.get("today_solved", 0) == 0:
        triggers.append((5, "today_zero"))

    if not triggers:
        return None

    # Сортируем по приоритету (меньше = важнее) и берём не более 2
    triggers.sort(key=lambda x: x[0])
    triggers = triggers[:2]

    sentences = []
    for _, reason in triggers:
        sentence = _render_trigger(reason, facts)
        if sentence:
            sentences.append(sentence)

    if not sentences:
        return None

    message = " ".join(sentences)
    # Обрезаем до трёх предложений (по точкам)
    parts = message.split(".")
    parts = [p.strip() for p in parts if p.strip()]
    message = ". ".join(parts[:3]) + "."

    return message


def _yesterday_solved(facts: Dict[str, Any]) -> Optional[int]:
    """Не вычисляется из facts — возвращаем -1 как «нет данных»."""
    return -1  # маркер: считается отдельно


def _render_trigger(reason: str, facts: Dict[str, Any]) -> Optional[str]:
    """Отрендерить одно предложение по коду повода."""
    if reason == "yesterday_zero":
        return "Вчера ты не решил ни одной задачи."

    if reason == "today_zero":
        total = facts.get("today_total", 0)
        return f"Сегодня ты ещё не решил ни одной задачи из {total}."

    if reason == "debt_exists":
        size = facts.get("debt_size", 0)
        days = facts.get("debt_days_count", 0)
        return f"У тебя {size} задач долга за {days} дней."

    if reason == "debt_burns":
        size = facts.get("debt_size", 0)
        burns = facts.get("debt_burns_tomorrow", 0)
        return f"У тебя {size} задач долга, {burns} из них сгорят завтра."

    if reason == "slice_pending":
        day = facts.get("cycle_day")
        total = facts.get("slice_total", 0)
        if day is not None:
            return f"Идёт день {day} месячного цикла из {total}, срез ещё не пройден."

    if reason == "level_up":
        now = facts.get("level_now")
        delta = facts.get("level_delta")
        if now is not None and delta is not None:
            return f"Твой уровень вырос до {now} (плюс {delta} за неделю)."

    if reason == "level_down":
        now = facts.get("level_now")
        delta = facts.get("level_delta")
        if now is not None and delta is not None:
            return f"Твой уровень снизился до {now} (минус {abs(delta)} за неделю)."

    if reason == "weak_section":
        weakest = facts.get("weakest_sections", [])
        if weakest:
            sec = weakest[0]
            section_names = {
                "algebra": "Алгебра",
                "geometry": "Геометрия",
                "combinatorics": "Комбинаторика",
                "logic": "Логика",
                "number_theory": "Теория чисел",
            }
            name = section_names.get(sec.get("section", ""), sec.get("section", ""))
            pct = sec.get("accuracy_pct", 0)
            pct_str = str(int(pct)) if pct == int(pct) else str(pct)
            return f"Самый слабый раздел: {name} — {pct_str}% верных ответов."

    if reason == "tomorrow_method":
        code = facts.get("method_code", "")
        name = facts.get("method_name", "")
        if code and name:
            return f"Завтра тема требует метода {code} «{name}»."

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 4. ПРОВЕРКА ФАКТОВ — validate_message(message, facts)
# ═══════════════════════════════════════════════════════════════════════════════


def validate_message(message: str, facts: Dict[str, Any]) -> Tuple[bool, str]:
    """Проверить, что все числа и названия в сообщении есть в фактах.

    Любое число (цифра) и любое название (слово с большой буквы,
    кроме служебных слов-зачинов) должно встречаться в строковом
    представлении фактов.

    Returns:
        (True, "") если валидно
        (False, reason) если нет — с указанием причины
    """
    # Собираем все факты в одну строку для поиска
    facts_str = _facts_to_searchable_string(facts)

    import re

    # Извлекаем все числа из сообщения
    numbers_in_msg = set(re.findall(r'\d+', message))
    for num in numbers_in_msg:
        if num not in facts_str:
            return (False, f"Число '{num}' не найдено в фактах")

    # Извлекаем слова с большой буквы (названия), исключая служебные зачины
    cap_words = set(re.findall(r'\b[А-ЯA-Z][а-яa-z]+\b', message))

    # Слова, которые могут быть в начале предложения и не являются названиями
    sentence_starters = {
        'Ты', 'Сегодня', 'Вчера', 'Завтра', 'У', 'Идёт', 'Твой', 'Самый',
        'Попробуй', 'Не', 'Так', 'Продолжай', 'Отличная', 'Молодец',
        'Вижу', 'Рады', 'Каждый', 'Олимпиадная', 'Начни', 'Важно',
        'Это', 'Он', 'Она', 'Они', 'Мы', 'Вы', 'Я', 'Но', 'А', 'И',
    }
    cap_words -= sentence_starters

    for word in cap_words:
        if word.lower() not in facts_str.lower():
            return (False, f"Название '{word}' не найдено в фактах")

    return (True, "")


def _facts_to_searchable_string(facts: Dict[str, Any]) -> str:
    """Превратить факты в строку для поиска чисел и названий."""
    parts = []

    def _flatten(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(v, f"{prefix}{k} ")
        elif isinstance(obj, list):
            for item in obj:
                _flatten(item, prefix)
        elif obj is not None:
            parts.append(str(obj))

    _flatten(facts)
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАДАЧА 5. КАРТОЧКА — get_curator_card(user_id)
# ═══════════════════════════════════════════════════════════════════════════════


def get_curator_card(user_id: int) -> Optional[Dict[str, Any]]:
    """Получить данные для HTML-карточки куратора на странице задач дня.

    Returns:
        None — если поводов нет (карточка не показывается)
        dict с ключами: message, facts — для рендера
    """
    facts = get_student_facts(user_id)
    message = build_curator_message(facts)

    if message is None:
        return None

    valid, reason = validate_message(message, facts)
    if not valid:
        _log_validation_failure(user_id, message, reason)
        return None

    return {
        "message": message,
        "facts": {
            "cycle_day": facts.get("cycle_day"),
            "slice_done": facts.get("slice_done"),
            "today_total": facts.get("today_total"),
            "today_solved": facts.get("today_solved"),
            "today_correct": facts.get("today_correct"),
            "debt_size": facts.get("debt_size"),
            "debt_days_count": facts.get("debt_days_count"),
            "debt_burns_tomorrow": facts.get("debt_burns_tomorrow"),
            "streak_days": facts.get("streak_days"),
            "level_now": facts.get("level_now"),
            "level_delta": facts.get("level_delta"),
            "method_code": facts.get("method_code"),
            "method_name": facts.get("method_name"),
        },
    }


def _log_validation_failure(user_id: int, message: str, reason: str) -> None:
    """Записать в лог отклонённое сообщение."""
    logger.warning(
        "CURATOR_VALIDATION_FAILED user=%d reason=%s message=%r",
        user_id, reason, message,
    )
    # Пишем также в файл-лог
    try:
        log_path = os.path.join(
            os.path.dirname(__file__), "..", "logs", "curator_validation.log",
        )
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                f"{datetime.now(MSK).isoformat()} "
                f"user={user_id} reason={reason} "
                f"message={message!r}\n"
            )
    except Exception:
        pass
