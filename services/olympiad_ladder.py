# -*- coding: utf-8 -*-
"""
services/olympiad_ladder.py — OLYMPIAD_LADDER_V1 (06.11.2026): лестница
пробников под класс ученика.

Владелец (06.11.2026): «под каждый класс выбор олимпиады: начать со
школьного этапа ВсОШ, потом в зависимости от результата — муниципальный
либо снова школьный, потом перечневые, которые предложит куратор».

Ступени
-------
* 9–11 классы (ВсОШ есть в каталоге):
    1. ВсОШ, школьный этап. Результат ≥ PASS_SHARE → ступень 2,
       иначе — следующий школьный вариант (свежий год → старый);
    2. ВсОШ, муниципальный этап. Результат ≥ PASS_SHARE → ступень 3,
       иначе — следующий муниципальный вариант (назад на школьный
       не откатываемся: школьный уже сдан);
    3. перечневые олимпиады, которые предлагает куратор (см. ниже).
* 5–8 классы: вариантов ВсОШ в каталоге НЕТ (только 9–11), подмен
  классов не бывает — стартовая ступень своя для класса
  (ENTRY_BY_GRADE), дальше по тому же правилу — перечневые.

Результат пробника — доля задач варианта, отмеченных ИИ-проверкой как
верные (bank_issues.is_correct по строкам банка 'probnik:<код>').
Учитываются только ПОЛНОСТЬЮ сданные варианты: ответы есть на все
задачи. Недосданный вариант результата не даёт — ступень не меняется,
следующий пробник берётся с той же ступени (выданные не повторяются).

Если на ступени кончились невыданные варианты, ученик переходит на
следующую — архив конечен, по кругу на одной ступени не гоняем.

Перечневые: «куратор предлагает» 2–3 олимпиады (PERECHEN_PICK):
  1) олимпиада, которую ученик сам выбрал в плане подготовки (если она
     перечневая и в каталоге есть варианты его класса);
  2) олимпиады из советника куратора (services.olympiads_knowledge) по
     слабым темам — те, что есть в каталоге;
  3) базовый порядок для класса (DEFAULT_PERECHEN): от доступных к
     сложным.
Выдача чередует предложенные олимпиады по кругу.

Модуль ничего не коммитит: выбор → services.real_probnik
(ensure_real_probnik делает только flush в транзакции вызывающего кода).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Порог перехода на следующую ступень: доля верно решённых задач варианта.
PASS_SHARE = 0.5

# Сколько перечневых олимпиад предлагает куратор одновременно.
PERECHEN_PICK = 3

# 5–8 классы: стартовая олимпиада вместо ВсОШ (в каталоге ВсОШ — только 9–11).
ENTRY_BY_GRADE: Dict[int, str] = {
    5: 'formula-unity',
    6: 'matprazdnik',
    7: 'matprazdnik',
    8: 'euler',
}

# Базовый порядок перечневых для класса — от доступных к сложным.
# Только олимпиады, у которых в каталоге есть варианты этого класса
# (лишние фильтруются автоматически по наличию вариантов).
DEFAULT_PERECHEN: Dict[int, List[str]] = {
    5: ['pvg', 'formula-unity'],
    6: ['kurchatov', 'pvg', 'formula-unity', 'spbgu'],
    7: ['vysshaya-proba', 'kurchatov', 'pvg', 'formula-unity', 'spbgu'],
    8: ['vysshaya-proba', 'kurchatov', 'turgor', 'mmo', 'pvg', 'spbgu',
        'formula-unity'],
    9: ['vysshaya-proba', 'kurchatov', 'turgor', 'mmo', 'phystech', 'pvg',
        'spbgu', 'formula-unity'],
    10: ['vysshaya-proba', 'kurchatov', 'turgor', 'mmo', 'phystech', 'pvg',
         'spbgu', 'formula-unity'],
    11: ['vysshaya-proba', 'kurchatov', 'turgor', 'mmo', 'phystech', 'pvg',
         'spbgu', 'formula-unity'],
}

# Slug'и prep-плана / советника куратора → slug каталога.
_SLUG_TO_CATALOG = {
    'turnir-gorodov': 'turgor',
    'pokori-vorobievy-gory': 'pvg',
    'fiztekh': 'phystech',
}

_STAGE_LABELS = {
    'school': 'школьный этап ВсОШ',
    'municipal': 'муниципальный этап ВсОШ',
}


def _catalog_slug(slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    return _SLUG_TO_CATALOG.get(slug, slug)


def rungs_for_grade(grade: Optional[int]) -> List[Dict[str, Any]]:
    """Стартовые ступни класса (без перечневой): [{'slug','stage','label'}]."""
    if grade is None:
        return []
    from services.real_probnik import stage_codes
    if 9 <= grade <= 11 and stage_codes('vsosh', grade, 'school'):
        return [
            {'slug': 'vsosh', 'stage': 'school', 'label': _STAGE_LABELS['school']},
            {'slug': 'vsosh', 'stage': 'municipal',
             'label': _STAGE_LABELS['municipal']},
        ]
    entry = ENTRY_BY_GRADE.get(grade)
    if entry and stage_codes(entry, grade):
        return [{'slug': entry, 'stage': None, 'label': entry}]
    return []


# ─── Результаты сданных пробников ────────────────────────────────────────

def probnik_result(user_id: int, code: str) -> Optional[Tuple[int, int]]:
    """(верно, всего) по варианту или None, если сдан не полностью."""
    try:
        from models import BankIssue, DailyTaskBank
        from services.probnik_daily import PROBNIK_BANK_PREFIX
        rows = DailyTaskBank.query.filter_by(
            subtopic=f'{PROBNIK_BANK_PREFIX}{code}').all()
        if not rows:
            return None
        ids = [r.id for r in rows]
        issues = BankIssue.query.filter(
            BankIssue.user_id == user_id,
            BankIssue.task_id.in_(ids),
            BankIssue.user_answer.isnot(None),
        ).all()
        answered: Dict[int, bool] = {}
        for it in issues:
            answered[it.task_id] = answered.get(it.task_id, False) or bool(it.is_correct)
        if len(answered) < len(ids):
            return None  # не все задачи сданы — результата нет
        return sum(1 for ok in answered.values() if ok), len(ids)
    except Exception as e:  # noqa: BLE001
        logger.warning('[ladder] result %s failed: %r', code, e)
        return None


def _passed(res: Optional[Tuple[int, int]]) -> bool:
    return bool(res) and res[1] > 0 and res[0] / res[1] >= PASS_SHARE


def _history(user_id: int) -> List[Dict[str, Any]]:
    """Пробники ученика по порядку выдачи (curator_lessons)."""
    try:
        from curator.session_plan import _lessons
        return [l for l in _lessons(user_id)
                if l.get('lesson_type') == 'probnik' and l.get('probnik_code')]
    except Exception as e:  # noqa: BLE001
        logger.warning('[ladder] history failed user=%s: %r', user_id, e)
        return []


# ─── Перечневые: предложение куратора ────────────────────────────────────

def _advisor_slugs(user_id: int, grade: int) -> List[str]:
    """Олимпиады советника куратора по слабым темам (без ИИ-вызова)."""
    try:
        from curator.olympiad_advisor import TOPIC_TO_SUBTOPIC_KEYS
        from curator.topic_analyzer import analyze_topics
        from services.olympiads_knowledge import recommend_olympiads_for
        summary = (analyze_topics(user_id) or {}).get('summary', {}) or {}
        keys: List[str] = []
        for t in (summary.get('weak_topics') or []) + (summary.get('medium_topics') or []):
            keys.extend(TOPIC_TO_SUBTOPIC_KEYS.get(t, []))
        return [_catalog_slug(s) for s in recommend_olympiads_for(grade, keys, limit=5)]
    except Exception as e:  # noqa: BLE001
        logger.info('[ladder] advisor unavailable user=%s: %r', user_id, e)
        return []


def perechen_offer(user_id: int, grade: int,
                   preferred_slug: Optional[str] = None) -> List[str]:
    """Перечневые олимпиады, которые куратор предлагает ученику (2–3 шт.)."""
    from services.real_probnik import stage_codes
    base = DEFAULT_PERECHEN.get(grade, [])
    allowed = set(base)
    cands: List[str] = []
    pref = _catalog_slug(preferred_slug)
    if pref and pref in allowed:
        cands.append(pref)
    cands += [s for s in _advisor_slugs(user_id, grade) if s in allowed]
    cands += base
    out: List[str] = []
    for s in cands:
        if s in out or not stage_codes(s, grade):
            continue
        out.append(s)
        if len(out) >= PERECHEN_PICK:
            break
    return out


# ─── Состояние лестницы и выбор следующего пробника ───────────────────────

def ladder_state(user_id: int, grade: Optional[int], used_codes: set,
                 preferred_slug: Optional[str] = None) -> Dict[str, Any]:
    """Текущая ступень ученика.

    {'rung': i, 'rungs': [...], 'slug', 'stage', 'label', 'perechen': [...],
     'history': [{'code','slug','stage','result'}]}. rung == len(rungs) —
    перечневая ступень.
    """
    from services.real_probnik import has_unused, parse_code
    rungs = rungs_for_grade(grade)
    hist_out: List[Dict[str, Any]] = []
    i = 0
    for l in _history(user_id):
        code = l['probnik_code']
        info = parse_code(code) or {}
        res = probnik_result(user_id, code)
        hist_out.append({'code': code, 'slug': info.get('slug'),
                         'stage': info.get('stage'),
                         'result': list(res) if res else None})
        if i < len(rungs):
            r = rungs[i]
            if info.get('slug') == r['slug'] and (
                    r['stage'] is None or info.get('stage') == r['stage']):
                if _passed(res):
                    i += 1
    # ступень исчерпана (все варианты выданы) — идём дальше
    while i < len(rungs) and not has_unused(
            rungs[i]['slug'], grade, used_codes, rungs[i]['stage']):
        i += 1
    state: Dict[str, Any] = {'rung': i, 'rungs': rungs, 'history': hist_out,
                             'perechen': [], 'slug': None, 'stage': None,
                             'label': None, 'pass_share': PASS_SHARE}
    if i < len(rungs):
        state.update(slug=rungs[i]['slug'], stage=rungs[i]['stage'],
                     label=rungs[i]['label'])
        return state
    if grade is None:
        return state
    offer = perechen_offer(user_id, grade, preferred_slug)
    state['perechen'] = offer
    if not offer:
        return state
    # чередуем предложенные олимпиады по кругу: следующая — по числу
    # уже выданных перечневых пробников; исчерпанные пропускаем
    issued = sum(1 for h in hist_out if h['slug'] in offer)
    order = offer[issued % len(offer):] + offer[:issued % len(offer)]
    pick = next((s for s in order if has_unused(s, grade, used_codes)), order[0])
    state.update(slug=pick, stage=None, label=f'перечневая: {pick}')
    return state


def pick_next(user_id: int, grade: Optional[int], used_codes: set,
              preferred_slug: Optional[str] = None,
              create: bool = True) -> Optional[Dict[str, str]]:
    """Следующий пробник по лестнице: {'code','title','slug','ladder'} или None.

    create=False — только посмотреть (контекст куратора, без записи в БД).
    """
    if grade is None:
        return None
    st = ladder_state(user_id, grade, used_codes, preferred_slug)
    slug = st.get('slug')
    if not slug:
        return None
    from services.real_probnik import next_real_probnik, peek_next_probnik
    fn = next_real_probnik if create else peek_next_probnik
    p = fn(slug, grade, used_codes, stage=st.get('stage'))
    if not p:
        return None
    out = dict(p)
    out['slug'] = slug
    out['ladder'] = st.get('label') or slug
    return out
