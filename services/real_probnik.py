# -*- coding: utf-8 -*-
"""
services/real_probnik.py — REAL_PROBNIK_V1 (28.10.2026): реальные пробники
из «Каталога задач олимпиад» (data/olymp_catalog/*.json).

Занятие-пробник в ротации 1-из-6 теперь — реальный вариант выбранной
олимпиады прошлых лет: (год, этап, класс). Порядок выдачи — «свежий год →
старый», внутри года этапы от простого к сложному (владелец, 28.10.2026).

Как устроено
------------
* олимпиада пользователя — slug активного prep-плана; slug → файл
  data/olymp_catalog/<slug>.json (для двух slug есть алиасы);
* варианты группируются по (year, round, grade) из задач каталога;
  класс берётся точный, при отсутствии — ближайший доступный;
* пробник создаётся ЛЕНИВО, в момент назначения занятия-пробника:
  Probnik(type='stage') + OlympiadTask из задач каталога. Повторный
  вызов — no-op (идемпотентно по code). Ничего не удаляет;
* выданные варианты не повторяются (used_codes из curator_lessons);
  когда все годы пройдены — новый круг с самого свежего;
* всё работает через существующие страницы /olympiads/probnik/<code>,
  stage_start/stage_submit и maybe_complete_probnik — без нового UI.

Кодировка кода: real-<slug>-<год>-<этап>-g<класс> (≤50 символов).
Чертежи условий/решений берутся из полей fig_statement/fig_solution
каталога (static/figures/FINAL_FIGURES/...).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'olymp_catalog',
)

# slug prep-плана → имя файла каталога (без .json), где оно отличается.
_SLUG_ALIASES = {
    'turnir-gorodov': 'turgor',
    'pokori-vorobievy-gory': 'pvg',
}

# Ранг «сложности» этапа: меньше — проще (внутри года по возрастанию).
_ROUND_RANK = (
    ('школьн', 1),
    ('муниципальн', 2),
    ('отборочн', 3),
    ('региональн', 4),
    ('заключительн', 5),
    ('финал', 5),
    ('основной', 4),
    ('турунир', 3),
)

# Ранние годы (олимпиады 1935-2010 в архиве ММО и т.п.) тоже годятся.
_MIN_YEAR = 1930
_MIN_VARIANT_TASKS = 3

_DURATION_BY_ROUND = (
    ('школьн', 120),
    ('муниципальн', 120),
    ('региональн', 240),
    ('заключительн', 240),
)


# ─── Каталог: загрузка и группировка вариантов ────────────────────────────

def _file_slug(slug: str) -> str:
    return _SLUG_ALIASES.get(slug, slug)


def _load_catalog(slug: str) -> Optional[List[Dict[str, Any]]]:
    """Задачи олимпиады из data/olymp_catalog/<file>.json (или None)."""
    path = os.path.join(_DATA_DIR, f'{_file_slug(slug)}.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] %s: %r', path, e)
        return None
    return data if isinstance(data, list) else None


def _round_rank(round_name: str) -> int:
    name = str(round_name or '').strip().lower()
    for key, rank in _ROUND_RANK:
        if key in name:
            return rank
    return 3  # нейтральный ранг для неизвестных этапов


def _round_slug(round_name: str) -> str:
    name = str(round_name or '').strip().lower()
    for key, slug in (
        ('школьн', 'school'),
        ('муниципальн', 'municipal'),
        ('отборочн', 'qual'),
        ('региональн', 'regional'),
        ('заключительн', 'final'),
        ('финал', 'final'),
        ('основной', 'main'),
        ('тур', 'tour'),
    ):
        if key in name:
            return slug
    # неизвестный этап — транслит не делаем, устойчивый ключ по рангу
    return f'rd{_round_rank(name)}'


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _grouped_variants(tasks: List[Dict[str, Any]]) -> Dict[Tuple[int, str], Dict[int, list]]:
    """(год, этап) → {класс: [задачи]} — только задачи с условием."""
    groups: Dict[Tuple[int, str], Dict[int, list]] = {}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        text = (t.get('text') or '').strip()
        if not text:
            continue
        year = _as_int(t.get('year'))
        rnd = t.get('round')
        grade = _as_int(t.get('grade'))
        if year is None or year < _MIN_YEAR or not rnd or grade is None:
            continue
        groups.setdefault((year, str(rnd)), {}).setdefault(grade, []).append(t)
    return groups


def ordered_variants(slug: str, grade: Optional[int]) -> List[Dict[str, Any]]:
    """Доступные варианты (год, этап, класс) по порядку выдачи.

    Порядок: год по убыванию (свежий → старый), внутри года — этапы от
    простого к сложному. Класс — точный, при отсутствии ближайший.
    """
    tasks = _load_catalog(slug)
    if not tasks:
        return []
    groups = _grouped_variants(tasks)
    if not groups:
        return []
    grades_avail = sorted({g for per_round in groups.values() for g in per_round})
    if not grades_avail:
        return []
    target = grade if grade in grades_avail else min(
        grades_avail, key=lambda g: abs(g - (grade or 9)))
    out: List[Dict[str, Any]] = []
    for (year, rnd) in sorted(
        groups,
        key=lambda k: (-k[0], _round_rank(k[1]), k[1]),
    ):
        vt = groups[(year, rnd)].get(target)
        if not vt or len(vt) < _MIN_VARIANT_TASKS:
            continue
        out.append({'year': year, 'round': rnd, 'grade': target, 'tasks': vt})
    return out


# ─── Код пробника и метаданные ────────────────────────────────────────────

def _code(slug: str, year: int, round_name: str, grade: int) -> str:
    return f'real-{_file_slug(slug)}-{year}-{_round_slug(round_name)}-g{grade}'[:50]


def _competition_name(slug: str) -> str:
    """Название олимпиады из индекса каталога (для Probnik.competition)."""
    try:
        with open(os.path.join(_DATA_DIR, '_index.json'),
                  encoding='utf-8') as f:
            index = json.load(f)
        for row in index:
            if row.get('slug') == slug:
                return str(row.get('name') or slug)[:50]
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] index read failed: %r', e)
    return _file_slug(slug)[:50]


def _duration_for(round_name: str) -> Optional[int]:
    name = str(round_name or '').lower()
    for key, minutes in _DURATION_BY_ROUND:
        if key in name:
            return minutes
    return 180


def _stage_key(round_name: str) -> Optional[str]:
    name = str(round_name or '').lower()
    for key, slug in (('школьн', 'school'), ('муниципальн', 'municipal'),
                      ('региональн', 'regional'), ('заключительн', 'final')):
        if key in name:
            return slug
    return None


def _num_sort_key(v: Any) -> Tuple[int, int]:
    """Сортировка '1' < '2' < ... < '10' < '2a': (число, суффикс)."""
    s = str(v or '').strip()
    head, tail = '', s
    for i, ch in enumerate(s):
        if ch.isdigit():
            head += ch
        else:
            tail = s[i:]
            break
    return (_as_int(head) or 0, tail)


def _difficulty_at(i: int, n: int) -> str:
    if n <= 1:
        return 'green'
    frac = i / max(n - 1, 1)
    if frac < 0.3:
        return 'green'
    if frac < 0.6:
        return 'yellow'
    if frac < 0.85:
        return 'orange'
    return 'red'


def _task_number(t: Dict[str, Any], used: set) -> str:
    """Номер задачи внутри варианта; при дубле — 'день.номер'."""
    num = str(t.get('num') or '').strip()[:10]
    if num and num not in used:
        return num
    day = str(t.get('day') or 1)
    alt = f'{day}.{num}'[:10]
    if alt and alt not in used:
        return alt
    # крайний случай: нумеруем по порядку
    return str(len(used) + 1)


def _idea_from_solution(solution: str) -> str:
    """Первая фраза решения как «идея» (максимум 300 символов)."""
    s = (solution or '').strip()
    if not s:
        return ''
    for sep in ('. ', '! ', '? '):
        idx = s.find(sep)
        if 0 < idx < 300:
            return s[:idx + 1].strip()
    return s[:300].strip()


# ─── Ленивое создание пробника ────────────────────────────────────────────

def ensure_real_probnik(slug: str, year: int, round_name: str, grade: int,
                        number: int = 1) -> Optional[Dict[str, str]]:
    """Создать Probnik + OlympiadTask из варианта каталога (идемпотентно).

    Возвращает {'code': ..., 'title': ...} или None. Файл каталога —
    источник истины; задачи варианта перезаливаются только при создании
    пробника (существующий пробник не трогаем — прогресс учеников важнее).
    """
    code = _code(slug, year, round_name, grade)
    title = f'{_competition_name(slug)} {year}, {round_name}, {grade} класс'[:200]
    try:
        from models import db
        from models_olympiad import Probnik, OlympiadTask
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] models import failed: %r', e)
        return None

    existing = Probnik.query.filter_by(code=code).first()
    if existing is not None:
        return {'code': existing.code, 'title': existing.title or code}

    # ищем задачи варианта в каталоге
    tasks = _load_catalog(slug) or []
    group = _grouped_variants(tasks).get((year, round_name), {})
    variant = group.get(grade)
    if not variant or len(variant) < _MIN_VARIANT_TASKS:
        logger.info('[real_probnik] variant %s not found/empty — skip', code)
        return None

    max_score = 7 * len(variant)
    try:
        p = Probnik(
            code=code,
            type='stage',
            number=number,
            title=title,
            description=f'Реальный вариант олимпиады ({year}, {round_name}). '
                       f'Источник: каталог задач олимпиад.',
            competition=_competition_name(slug),
            grade=grade,
            season_year=year,
            duration_minutes=_duration_for(round_name),
            max_score=max_score,
            threshold_prize=max(1, round(max_score * 0.3)),
            threshold_winner=max(1, round(max_score * 0.5)),
            sort_order=0,
            is_published=True,
        )
        db.session.add(p)
        db.session.flush()

        used_numbers: set = set()
        for i, t in enumerate(sorted(
                variant,
                key=lambda x: ((x.get('day') or 0), _num_sort_key(x.get('num'))))):
            text = (t.get('text') or '').strip()
            if not text:
                continue
            num = _task_number(t, used_numbers)
            used_numbers.add(num)
            solution = (t.get('solution') or '').strip()
            db.session.add(OlympiadTask(
                probnik_id=p.id,
                number=num,
                sort_order=i + 1,
                difficulty=_difficulty_at(i, len(variant)),
                method_primary='A1',
                method_secondary=None,
                condition_md=text,
                idea_md=_idea_from_solution(solution),
                solution_md=solution,
                answer=str(t.get('answer') or '').strip()[:500] or None,
                source_prototype=str(t.get('source') or '').strip()[:200] or None,
                estimated_minutes=None,
                max_score=7,
                year=year,
                stage=_stage_key(round_name),
            ))
        db.session.commit()
        logger.info('[real_probnik] created %s: %d tasks', code, len(variant))
        return {'code': code, 'title': title}
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] create %s failed: %r', code, e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


# ─── Выбор следующего пробника ────────────────────────────────────────────

def next_real_probnik(slug: str, grade: Optional[int],
                      used_codes: set) -> Optional[Dict[str, str]]:
    """Следующий реальный вариант по порядку (свежий год → старый).

    used_codes — коды уже выданных пробников (не повторяем). Когда все
    годы пройдены — разрешаем новый круг с самого свежего.
    """
    variants = ordered_variants(slug, grade)
    if not variants:
        return None
    for idx, v in enumerate(variants, start=1):
        code = _code(slug, v['year'], v['round'], v['grade'])
        if code in used_codes:
            continue
        made = ensure_real_probnik(slug, v['year'], v['round'], v['grade'],
                                  number=idx)
        if made:
            return made
    # все варианты уже выдавались — начинаем новый круг с самого свежего
    v = variants[0]
    made = ensure_real_probnik(slug, v['year'], v['round'], v['grade'], number=1)
    if made:
        return made
    # создание не удалось, но вариант существует (уже в БД)?
    try:
        from models_olympiad import Probnik
        p = Probnik.query.filter_by(
            code=_code(slug, v['year'], v['round'], v['grade'])).first()
        if p is not None:
            return {'code': p.code, 'title': p.title or p.code}
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] fallback lookup failed: %r', e)
    return None


# ─── Чертежи к задачам реального пробника ─────────────────────────────────

def figures_for_task(probnik_code: str, task_number: str) -> Dict[str, list]:
    """Чертежи условия/решения задачи реального пробника из каталога.

    Разбирает код real-<slug>-<год>-<этап>-g<класс>, находит задачу по
    номеру и возвращает {'condition': [{'file': ...}], 'solution': [...]}
    (формат манифеста чертежей — см. services/figures_manifest.py).
    """
    empty = {'condition': [], 'solution': []}
    if not probnik_code.startswith('real-'):
        return empty
    parts = probnik_code.split('-')
    # real, <slug...>, <year>, <round...>, g<grade> — slug может содержать
    # дефисы, поэтому год и класс ищем с концов.
    if len(parts) < 5 or not parts[-1].startswith('g'):
        return empty
    year = _as_int(parts[-3]) if len(parts) >= 3 else None
    grade = _as_int(parts[-1][1:])
    round_part = parts[-2] if len(parts) >= 2 else ''
    slug = '-'.join(parts[1:-3])
    if year is None or grade is None or not slug:
        return empty

    tasks = _load_catalog(slug)
    if not tasks:
        return empty
    target = str(task_number or '').strip()
    for t in tasks:
        if _as_int(t.get('year')) != year or _as_int(t.get('grade')) != grade:
            continue
        # этап из кода (school/municipal/regional/final/...) должен
        # совпадать с этапом задачи — номер «6» есть в нескольких этапах
        if _round_slug(t.get('round')) != round_part:
            continue
        if str(t.get('num') or '').strip() != target:
            continue
        return {
            'condition': [{'file': f} for f in (t.get('fig_statement') or [])],
            'solution': [{'file': f} for f in (t.get('fig_solution') or [])],
        }
    return empty
