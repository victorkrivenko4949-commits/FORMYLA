# -*- coding: utf-8 -*-
"""
services/level_engine.py — Единый держатель канонического уровня FORMYLA.

Шкала: 1..5 (каноническая). Всё остальное — производное.

Источники задач и их шкалы определены по результатам ШАГА 1 аудита
(см. docs/LEVEL_ENGINE_PLAN.md):
  - formyla_L1_L5_TOP5  -> пятибалльная шкала (difficulty_level 1..5)

Восьмибалльные источники (curator diagnostic, profile-based движок)
будут добавлены в EIGHT_POINT_SOURCES при их появлении в пуле.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from models import db
from models_curator import CuratorState

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Константы — источники задач и их шкалы (определены ШАГОМ 1)
# ══════════════════════════════════════════════════════════════════════

# Источники с пятибалльной шкалой (difficulty_level in {1, 2, 3, 4, 5})
FIVE_POINT_SOURCES: set = {
    'formyla_L1_L5_TOP5',
}

# ══════════════════════════════════════════════════════════════════════
# Маппинг канонического уровня (1..5) -> список difficulty_level
#
# P3 BAND FIX (2026-07-31):
#   Каждый уровень отдаёт основной + соседние уровни выше и ниже,
#   с предпочтением основного (он первый в списке).
#   Полоса не зависит от того, сколько задач осталось.
#   Диапазон зажат в 1..5.
# ══════════════════════════════════════════════════════════════════════

FIVE_POINT_MAP: Dict[int, List[int]] = {
    1: [1, 2],
    2: [2, 1, 3],
    3: [3, 2, 4],
    4: [4, 3, 5],
    5: [5, 4],
}

# ══════════════════════════════════════════════════════════════════════
# Внутренние константы
# ══════════════════════════════════════════════════════════════════════

# Коэффициенты обновления mu/sigma
CORRECT_DELTA_FACTOR = 0.22
WRONG_DELTA_FACTOR = 0.28
SIGMA_OFFSET = 0.3
SIGMA_DECAY = 0.94
MIN_SIGMA = 0.35
MIN_MU = 1.0
MAX_MU = 5.0

# ══════════════════════════════════════════════════════════════════════
# Маппинг русских названий разделов из JSONL -> латинские slug'и
# (канонические ключи level_by_section, на них же завязан радар)
# ══════════════════════════════════════════════════════════════════════

SECTION_RU_TO_SLUG: Dict[str, str] = {
    'Алгебра':            'algebra',
    'Алгебра и анализ':   'algebra',
    'Арифметика':         'algebra',
    'Геометрия':          'geometry',
    'Комбинаторика':      'combinatorics',
    'Логика и методы':    'logic',
    'Текстовые задачи':   'algebra',
    'Теория чисел':       'number_theory',
}

CANONICAL_SECTIONS: tuple = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')

def _normalize_section(raw: str) -> str:
    """Преобразовать русское название раздела (из JSONL) в латинский slug.
    Если строка уже латинский slug — вернуть как есть."""
    s = raw.strip()
    if s in CANONICAL_SECTIONS:
        return s
    return SECTION_RU_TO_SLUG.get(s, s)

# Значения по умолчанию (если записи CuratorState нет)
DEFAULT_MU = 3.0
DEFAULT_SIGMA = 1.5


# ══════════════════════════════════════════════════════════════════════
# Публичный API
# ══════════════════════════════════════════════════════════════════════

def get_state(user_id: int) -> Dict[str, Any]:
    """Получить текущее состояние уровня ученика.

    Возвращает:
        {
            "mu": float,           # оценка уровня (1.0..5.0)
            "sigma": float,        # неопределённость (≥ 0.35)
            "level": int,          # округлённый уровень (1..5)
            "by_section": dict,    # {section: {mu, sigma, n}, ...}
            "updated_at": str|None # ISO-строка последнего обновления
        }
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs or cs.level_mu is None:
        return {
            "mu": DEFAULT_MU,
            "sigma": DEFAULT_SIGMA,
            "level": int(round(DEFAULT_MU)),
            "by_section": {},
            "updated_at": None,
        }

    by_section = {}
    if cs.level_by_section:
        try:
            by_section = json.loads(cs.level_by_section)
        except (json.JSONDecodeError, TypeError):
            by_section = {}

    mu = float(cs.level_mu)
    level = max(1, min(5, int(round(mu))))

    return {
        "mu": mu,
        "sigma": float(cs.level_sigma),
        "level": level,
        "by_section": by_section,
        "updated_at": cs.level_updated_at,
    }


def set_prior(user_id: int, mu: float, sigma: float,
              source: str = "") -> Dict[str, Any]:
    """Задать начальное значение уровня (вызывается анкетой или вручную).

    Параметры:
        user_id: ID пользователя
        mu:      начальная оценка уровня (будет зажата в [1.0, 5.0])
        sigma:   начальная неопределённость (будет зажата ≥ 0.35)
        source:  строка-источник (для логов, не сохраняется)

    Возвращает:
        Результат get_state() после установки.
    """
    mu = max(MIN_MU, min(MAX_MU, float(mu)))
    sigma = max(MIN_SIGMA, float(sigma))

    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None:
        cs = CuratorState(user_id=user_id)
        db.session.add(cs)

    cs.level_mu = mu
    cs.level_sigma = sigma
    cs.level_by_section = "{}"
    cs.level_updated_at = datetime.utcnow().isoformat()

    if not cs.onboarding_done:
        cs.onboarding_done = True

    db.session.commit()
    logger.info(f"level_engine set_prior: user={user_id} mu={mu:.3f} "
                f"sigma={sigma:.3f} source={source!r}")

    return get_state(user_id)


def record_result(user_id: int, section: Optional[str], level_shown: int,
                  correct: bool) -> Dict[str, Any]:
    """Записать результат решения одной задачи.

    Обновляет mu/sigma глобально и по разделу по формулам:
      верно   -> mu += 0.22 * (sigma + 0.3)
      неверно -> mu -= 0.28 * (sigma + 0.3)
      sigma   -> max(0.35, sigma * 0.94)
      mu      -> clamp(1.0, 5.0)
      level   -> int(round(mu)), clamp(1, 5)

    Параметры:
        user_id:     ID пользователя
        section:     имя раздела (например, 'algebra', 'geometry').
                     Если None — обновляется только глобальный mu,
                     by_section не трогается.
        level_shown: уровень задачи, которую показывали (1..5)
        correct:     True если решена верно

    Возвращает:
        Результат get_state() после обновления.
    """
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if cs is None or cs.level_mu is None:
        # Авто-инициализация дефолтными значениями
        set_prior(user_id, DEFAULT_MU, DEFAULT_SIGMA, "auto")
        cs = CuratorState.query.filter_by(user_id=user_id).first()

    mu = float(cs.level_mu)
    sigma_old = float(cs.level_sigma)

    # ── Обновление глобального mu/sigma ──
    delta = (sigma_old + SIGMA_OFFSET)
    if correct:
        mu += CORRECT_DELTA_FACTOR * delta
    else:
        mu -= WRONG_DELTA_FACTOR * delta

    sigma_new = max(MIN_SIGMA, sigma_old * SIGMA_DECAY)
    mu = max(MIN_MU, min(MAX_MU, mu))

    cs.level_mu = mu
    cs.level_sigma = sigma_new
    cs.level_updated_at = datetime.utcnow().isoformat()

    # ── Обновление by_section (только если section передан) ──
    if section is not None:
        by_section = {}
        if cs.level_by_section:
            try:
                by_section = json.loads(cs.level_by_section)
            except (json.JSONDecodeError, TypeError):
                by_section = {}

        section = _normalize_section(str(section))
        sec = by_section.get(section, {"mu": DEFAULT_MU, "sigma": DEFAULT_SIGMA, "n": 0})

        sec["n"] = int(sec.get("n", 0)) + 1
        sec_mu = float(sec.get("mu", mu))
        sec_sigma = float(sec.get("sigma", sigma_new))

        sec_delta = (sec_sigma + SIGMA_OFFSET)
        if correct:
            sec_mu += CORRECT_DELTA_FACTOR * sec_delta
        else:
            sec_mu -= WRONG_DELTA_FACTOR * sec_delta

        sec_sigma = max(MIN_SIGMA, sec_sigma * SIGMA_DECAY)
        sec_mu = max(MIN_MU, min(MAX_MU, sec_mu))

        sec["mu"] = sec_mu
        sec["sigma"] = sec_sigma
        by_section[section] = sec
        cs.level_by_section = json.dumps(by_section, ensure_ascii=False)

    db.session.commit()

    return get_state(user_id)


def allowed_difficulty(level_5: int, source: str) -> List[int]:
    """Перевести канонический уровень (1..5) в список допустимых
    difficulty_level для заданного источника задач.

    Маппинг — явный словарь, без интерполяции:
      - Пятибалльные источники: 1->[1] 2->[2] 3->[3] 4->[4] 5->[5]

    Параметры:
        level_5: канонический уровень (1..5, будет зажат)
        source:  строка-источник из adaptive_tasks.source

    Возвращает:
        Список допустимых значений difficulty_level (list[int]).
    """
    level_5 = max(1, min(5, int(level_5)))

    if source not in FIVE_POINT_SOURCES and source:
        logger.warning(
            "level_engine.allowed_difficulty: unknown source %r, "
            "treating as 5-point", source
        )

    return list(FIVE_POINT_MAP.get(level_5, [level_5]))


def get_level_by_theme(user_id: int) -> Dict[str, Any]:
    """Return level_by_theme dict from CuratorState, or {}."""
    import json as _json
    cs = CuratorState.query.filter_by(user_id=user_id).first()
    if not cs or not cs.level_by_theme:
        return {}
    try:
        return _json.loads(cs.level_by_theme) if isinstance(cs.level_by_theme, str) else cs.level_by_theme
    except (_json.JSONDecodeError, TypeError):
        return {}


def _theme_prior_mu(user_id: int, theme_id: str) -> float:
    """Resolve prior mu for a theme.

    Priority: level_by_theme -> level_by_section -> global mu -> default 3.0
    """
    from services.theme_registry import section_of_theme as _sec

    lbt = get_level_by_theme(user_id)
    if theme_id in lbt:
        mu_val = lbt[theme_id].get('mu')
        if mu_val is not None:
            return float(mu_val)

    # Try section
    section = _sec(theme_id)
    if section:
        state = get_state(user_id)
        by_section = state.get('by_section', {})
        sec_data = by_section.get(section, {})
        sec_mu = sec_data.get('mu')
        if sec_mu is not None:
            return float(sec_mu)

    # Global
    state = get_state(user_id)
    return float(state.get('mu', DEFAULT_MU))


def weakest_themes(user_id: int, grade: int, k: int) -> List[str]:
    """Return k theme_ids with the lowest mu for the given grade.

    Unmeasured themes receive their prior mu (section -> global -> 3.0).
    """
    from services.theme_registry import themes_of_grade as _tog

    all_themes = _tog(grade)
    if not all_themes:
        return []

    scored = [(tid, _theme_prior_mu(user_id, tid)) for tid in all_themes]
    scored.sort(key=lambda x: x[1])

    return [tid for tid, _ in scored[:k]]
