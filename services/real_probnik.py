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
  класс берётся ТОЛЬКО точный: если класса пользователя нет в каталоге —
  пробника нет (без подмен классов); для grade=None (обход каталога) —
  ближайший к 9-му;
* код пробника real-<slug>-<год>-<этап+теги>-g<класс>: этап — слаг
  названия + хеш названия + хеш состава (номеров задач) — код зависит
  только от собственного идентификатора варианта и стабилен при
  пополнении каталога; параллельные комплекты различаются тегом
  состава (проверяется тестом по всем каталогам);
* пробник создаётся ЛЕНИВО, в момент назначения занятия-пробника:
  Probnik(type='stage') + OlympiadTask из задач каталога. Повторный
  вызов — no-op (идемпотентно по code). Ничего не удаляет и НЕ делает
  commit — пробник коммитится транзакцией вызывающего кода;
* выданные варианты не повторяются (used_codes из curator_lessons);
  когда все годы пройдены — снова самый свежий (архив конечен, это
  задокументированное поведение пилота);
* длительность — только по регламенту ВсОШ (школьный/муниципальный
  120, региональный/заключительный 240 минут); для других олимпиад
  длительность не выдумываем: None — сдача без таймера (stage_active
  скрывает таймер). Пороги призёра/победителя НЕ выдумываем: None,
  пока не внесены официальные значения;
* всё работает через существующие страницы /olympiads/probnik/<code>,
  stage_start/stage_submit и maybe_complete_probnik — без нового UI.

Чертежи условий/решений — из полей fig_statement/fig_solution каталога
(static/olymp_figures/FINAL_FIGURES/...), отдаются с URL /static/...
(см. figures_for_task).
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
    'fiztekh': 'phystech',  # одна олимпиада, разные исторические слаги
}

# Олимпиады, чей каталог НЕДОСТОВЕРЕН как источник пробников — выдача
# приостановлена (ревью 28.10.2026). «Ломоносов»: каталог приписывает
# задачи 9 класса к чужим PDF (7-8/10 классов) и теряет задачи — по
# официальным работам 348-sol-math-9-final-23-24.pdf (7 задач, в
# каталоге 3) и 348-sol-math-9-final-24-25.pdf (8 задач, в каталоге 3)
# группы каталога — НЕПОЛНЫЕ фрагменты. До ремонта каталога пробники
# «Ломоносова» не выдаются (подмен и фрагментов не бывает).
_EXCLUDED_SLUGS = {'lomonosov'}

# Проверено по официальным PDF (tasks.olimpiada.ru): полный состав
# комплекта = (год, этап, класс, документ) → число задач. Если группа
# каталога меньше — она НЕПОЛНЫЙ фрагмент и пробником не выдаётся.
_VERIFIED_VARIANT_SIZES: Dict[str, Dict[Tuple[int, str, int, str], int]] = {
    'lomonosov': {
        # Заключительный этап 2023/24, 9 класс: задачи 1-7 (В-1).
        (2023, '2 тур', 9, '348-sol-math-9-final-23-24.pdf'): 7,
        # Заключительный этап 2024/25, 9 класс: задачи 1-8 (В-1).
        (2025, 'Отборочный этап', 9, '348-sol-math-9-final-24-25.pdf'): 8,
    },
}

# Ранг «сложности» этапа: меньше — проще (внутри года по возрастанию).
_ROUND_RANK = (
    ('школьн', 1),
    ('дистанционн', 2),
    ('заочн', 2),
    ('муниципальн', 3),
    ('отборочн', 4),
    ('осенн', 4),
    ('весенн', 5),
    ('базов', 5),
    ('региональн', 6),
    ('основной', 6),
    ('сложн', 7),
    ('заключительн', 8),
    ('финал', 8),
)

# Этап → однословный слаг для кода. Порядок: частные ключи раньше общих
# («базов»/«сложн» раньше «тур», иначе Турнир городов схлопнется в «tour»).
_ROUND_KEYWORDS = (
    ('школьн', 'school'),
    ('дистанционн', 'dist'),
    ('заочн', 'dist'),
    ('муниципальн', 'municipal'),
    ('отборочн', 'qual'),
    ('региональн', 'regional'),
    ('заключительн', 'final'),
    ('финал', 'final'),
    ('основной', 'main'),
    ('базов', 'basic'),
    ('сложн', 'advanced'),
    ('осенн', 'autumn'),
    ('весенн', 'spring'),
    ('тур', 'tour'),
)

# Длительность по регламенту ВсОШ по математике (Москва, vos.olimpiada.ru):
# школьный этап — 120 минут для 9–11 классов (90 для 5–8, 60 для 4);
# муниципальный — 120 минут для всех классов. Региональный и
# заключительный этапы — ДВУХДНЕВНЫЕ (235 и 300 минут за тур):
# единый таймер на весь комплект не задаём (multi_day -> None).
_DURATION_BY_ROUND = (
    ('муниципальн', 120),
)

_MIN_YEAR = 1930
_MIN_VARIANT_TASKS = 3


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
    return 4  # нейтральный ранг для неизвестных этапов


_B36 = '0123456789abcdefghijklmnopqrstuvwxyz'


def _name_tag(round_name: str) -> str:
    """Короткий стабильный тег названия этапа (3 символа, base36).

    Детерминирован ТОЛЬКО от полного названия: добавление в каталог
    нового этапа/года не меняет теги существующих. Используется при
    коллизии слагов внутри одного года (разные названия -> один слаг).
    """
    import hashlib
    h = hashlib.md5(str(round_name).strip().lower().encode('utf-8')).hexdigest()
    n = int(h[:8], 16) % (36 ** 3)
    out = ''
    for _ in range(3):
        out = _B36[n % 36] + out
        n //= 36
    return out


def _round_slug(round_name: str) -> str:
    """Однословный слаг этапа (без дефисов — код пробника должен
    однозначно разбираться обратно на части).

    Цифра из названия сохраняется («1 тур» -> tour1, «2 тур» -> tour2):
    слаг зависит от названия, а не от позиции в архиве."""
    name = str(round_name or '').strip().lower()
    for key, slug in _ROUND_KEYWORDS:
        if key in name:
            base = slug
            break
    else:
        base = 'round'
    import re as _re
    m = _re.search(r'\d+', name)
    if m:
        base += m.group(0)
    return base


def _duration_for(round_name: str, is_vsosh: bool,
                   grade: Optional[int] = None) -> Optional[int]:
    """Длительность этапа по регламенту ВсОШ (минуты) или None.

    Придумывать длительность для других олимпиад не можем: без
    подтверждённого регламента таймера нет — сдача без ограничения
    времени (stage_active скрывает таймер при duration_minutes=None).
    Школьный этап зависит от класса: 120 минут для 9–11, 90 для 5–8,
    60 для 4 (vos.olimpiada.ru, 2026/27).
    """
    if not is_vsosh:
        return None
    name = str(round_name or '').lower()
    if 'школьн' in name:
        if not grade:
            return None
        if grade <= 4:
            return 60
        if grade <= 8:
            return 90
        return 120
    for key, minutes in _DURATION_BY_ROUND:
        if key in name:
            return minutes
    return None  # региональный/заключительный — двухдневные: без таймера


def _stage_key(round_name: str) -> Optional[str]:
    name = str(round_name or '').lower()
    for key, slug in (('школьн', 'school'), ('муниципальн', 'municipal'),
                      ('региональн', 'regional'), ('заключительн', 'final')):
        if key in name:
            return slug
    return None


def _as_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _source_doc(task: Dict[str, Any]) -> str:
    """Имя исходного документа задачи (PDF из source-URL, без якоря).

    Нужно, чтобы НЕ смешивать в один «вариант» задачи из РАЗНЫХ
    официальных документов (параллельные комплекты/классы,
    ошибочно сведённые в один класс каталогом).
    """
    src = str(task.get('source') or '')
    tail = src.split('#')[0].rstrip('/')
    return tail.rsplit('/', 1)[-1]


def _grouped_variants(tasks: List[Dict[str, Any]]) -> Dict[Tuple[int, str, str], Dict[int, list]]:
    """(год, этап, документ) → {класс: [задачи]} — только задачи с условием.

    Если внутри (год, этап, класс) есть задачи с ОДИНАКОВЫМИ номерами —
    это разные официальные комплекты (параллельные варианты или задачи
    из чужого класса, ошибочно попавшие в этот): разбиваем по исходному
    документу, чтобы пробник был ОДНИМ официальным комплектом, а не
    склейкой (ревью 28.10.2026). Задачи без source приписываются к
    документу, если он один; иначе отбрасываются (неатрибуируемы).
    """
    raw: Dict[Tuple[int, str], Dict[int, list]] = {}
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
        raw.setdefault((year, str(rnd)), {}).setdefault(grade, []).append(t)

    groups: Dict[Tuple[int, str, str], Dict[int, list]] = {}
    for (year, rnd), per_grade in raw.items():
        for grade, vt in per_grade.items():
            nums = [str(t.get('num') or '') for t in vt]
            if len(set(nums)) == len(nums):
                # номера уникальны — один комплект, документ не нужен
                groups.setdefault((year, rnd, ''), {}).setdefault(grade, []).extend(vt)
                continue
            # дубликаты номеров: разбиваем по исходному документу
            by_doc: Dict[str, list] = {}
            no_src: list = []
            for t in vt:
                doc = _source_doc(t)
                if doc:
                    by_doc.setdefault(doc, []).append(t)
                else:
                    no_src.append(t)
            if len(by_doc) == 1 and no_src:
                # единственный документ — приписываем безsource-задачи к нему
                only = next(iter(by_doc))
                by_doc[only].extend(no_src)
            for doc, doc_tasks in by_doc.items():
                groups.setdefault((year, rnd, doc), {}).setdefault(grade, []).extend(doc_tasks)
    return groups


def ordered_variants(slug: str, grade: Optional[int]) -> List[Dict[str, Any]]:
    """Доступные варианты (год, этап, класс) по порядку выдачи.

    Порядок: год по убыванию (свежий → старый), внутри года — этапы от
    простого к сложному. Класс — ТОЛЬКО точный: нет класса в каталоге —
    нет пробника (подмен классов не бывает; grade=None — обход каталога,
    берём ближайший к 9-му). Олимпиады из _EXCLUDED_SLUGS не выдаются.
    """
    if _file_slug(slug) in _EXCLUDED_SLUGS:
        return []
    tasks = _load_catalog(slug)
    if not tasks:
        return []
    groups = _grouped_variants(tasks)
    if not groups:
        return []
    grades_avail = sorted({g for per_round in groups.values() for g in per_round})
    if not grades_avail:
        return []
    if grade is None:
        target = min(grades_avail, key=lambda g: abs(g - 9))
    elif grade in grades_avail:
        target = grade
    else:
        return []
    out: List[Dict[str, Any]] = []
    for key in sorted(
        groups,
        key=lambda k: (-k[0], _round_rank(k[1]), k[1], k[2]),
    ):
        vt = groups[key].get(target)
        if not vt or len(vt) < _MIN_VARIANT_TASKS:
            continue
        # после разбивки по документам дубликаты номеров ОСТАЛИСЬ —
        # это не один официальный комплект, а неатрибуируемая склейка:
        # такой «вариант» не выдаём (подмен и склеек не бывает)
        nums = [str(t.get('num') or '') for t in vt]
        if len(set(nums)) != len(nums):
            continue
        year, rnd, doc = key
        # проверенный по официальному PDF состав: группа каталога меньше
        # полного комплекта — НЕПОЛНЫЙ фрагмент, не выдаём
        need = _VERIFIED_VARIANT_SIZES.get(
            _file_slug(slug), {}).get((year, rnd, target, doc))
        if need is not None and len(vt) < need:
            continue
        out.append({'year': year, 'round': rnd, 'grade': target,
                    'tasks': vt, 'doc': doc})
    return out


# ─── Коды пробников (детерминированные, без коллизий) ─────────────────────

def variant_codes(slug: str, grade: Optional[int]) -> List[Tuple[str, Dict[str, Any]]]:
    """[(код, вариант)] по порядку выдачи; коды уникальны и СТАБИЛЬНЫ.

    Тег названия (_name_tag) входит в код КАЖДОГО варианта ВСЕГДА:
    код зависит только от собственного названия этапа, а не от того,
    сколько ещё этапов даёт такой же слог. Второй тег — ХЕШ СОСТАВА
    (_set_tag: короткий хеш отсортированных uid задач) — тоже ВСЕГДА:
    код зависит от собственного стабильного идентификатора комплекта
    (uid — а не номера: параллельные комплекты могут иметь одинаковую
    нумерацию), а не от условного тега исходного PDF (ревью 28.10.2026:
    doc-тег появлялся/исчезал при изменениях каталога и менял код).
    Добавление в каталог новых лет/этапов НЕ меняет существующие коды —
    сохранённые коди в curator_lessons остаются валидными."""
    variants = ordered_variants(slug, grade)
    out: List[Tuple[str, Dict[str, Any]]] = []
    for v in variants:
        part = f'{_round_slug(v["round"])}{_name_tag(v["round"])}{_set_tag(v["tasks"])}'
        code = f'real-{_file_slug(slug)}-{v["year"]}-{part}-g{v["grade"]}'[:50]
        out.append((code, v))
    return out


def _set_tag(vt: List[Dict[str, Any]]) -> str:
    """Стабильный идентификатор СОСТАВА комплекта: хеш uid задач.

    Зависит только от набора задач самого варианта (uid, а не номера:
    параллельные комплекты могут иметь одинаковую нумерацию — как
    «Ломоносов»-2023). Добавление в каталог новых документов/этапов
    код не меняет; разные комплекты получают разные теги.
    """
    uids = sorted(str(t.get('uid') or t.get('num') or '') for t in vt)
    return _name_tag(','.join(uids))


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


def _variant_title(slug: str, v: Dict[str, Any]) -> str:
    return (f'{_competition_name(slug)} {v["year"]}, '
            f'{v["round"]}, {v["grade"]} класс')[:200]


def _num_sort_key(v: Any) -> Tuple[int, str]:
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


def _variant_task_numbers(vt: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """Единая нумерация задач варианта: [(номер, задача)] по порядку.

    Используется и при создании OlympiadTask, и при поиске чертежей
    (figures_for_task) — гарантия, что номер в БД соответствует задаче
    каталога, включая случаи дублей номеров (день.номер).
    """
    used: set = set()
    out: List[Tuple[str, Dict[str, Any]]] = []
    for t in sorted(vt, key=lambda x: ((x.get('day') or 0),
                                      _num_sort_key(x.get('num')))):
        num = _task_number(t, used)
        used.add(num)
        out.append((num, t))
    return out


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
    return str(len(used) + 1)  # крайний случай: нумеруем по порядку


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

def ensure_real_probnik(code: str, variant: Dict[str, Any], slug: str,
                        number: int = 1) -> Optional[Dict[str, str]]:
    """Создать Probnik + OlympiadTask из варианта каталога (идемпотентно).

    НЕ делает commit — только flush: пробник попадает в БД транзакцией
    вызывающего кода (атомарность _insert_lesson/_advance_stale).
    Создание обёрнуто в SAVEPOINT (begin_nested): при ошибке откатывается
    только создание пробника, а не вся транзакция вызывающего кода.
    Возвращает {'code': ..., 'title': ...} или None.
    """
    try:
        from models import db
        from models_olympiad import Probnik, OlympiadTask
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] models import failed: %r', e)
        return None

    try:
        existing = Probnik.query.filter_by(code=code).first()
        if existing is not None:
            return {'code': existing.code, 'title': existing.title or code}

        year, rnd, grade = variant['year'], variant['round'], variant['grade']
        vt = variant['tasks']
        is_vsosh = _file_slug(slug) == 'vsosh'
        # вариант в несколько дней (двухдневный региональный и т.п.) —
        # НЕ одна сессия: выдумывать единый таймер нельзя, длительность
        # не задаём (без таймера), границы дней отмечаем в описании
        days = sorted({(t.get('day') or 0) for t in vt} - {0})
        multi_day = len(days) > 1
        duration = (None if multi_day
                    else _duration_for(rnd, is_vsosh, grade))
        max_score = 7 * len(vt)
        # Номер слота: если занят (смена класса ученика и т.п.) — следующий.
        slot_number = number
        taken = {r[0] for r in db.session.execute(
            db.text('SELECT number FROM olympiad_probniks '
                    'WHERE competition = :c AND grade = :g '
                    'AND season_year = :y AND type = :t'),
            {'c': _competition_name(slug), 'g': grade, 'y': year,
             't': 'stage'}).fetchall()}
        while slot_number in taken:
            slot_number += 1

        # SAVEPOINT: при сбое создания откатывается только пробник,
        # а не вся транзакция вызывающего кода (долги и т.п.)
        with db.session.begin_nested():
            p = Probnik(
                code=code,
                type='stage',
                number=slot_number,
                title=_variant_title(slug, variant),
                description=(
                    f'Реальный вариант олимпиады ({year}, {rnd}). '
                    f'Источник: каталог задач олимпиад. '
                    + (f'Вариант проходит в {len(days)} дня '
                       f'(дни: {days[0]}–{days[-1]}); задачи идут по дням '
                       'подряд — сдавайте по дню за сессию. ' if multi_day
                       else '')
                    + ('Длительность — по регламенту этапа. '
                       if duration else 'Сдача без ограничения времени '
                       '(регламент этапа не подтверждён). ')
                    + 'Самооценка 0–7 за задачу — шкала платформы.'
                ),
                competition=_competition_name(slug),
                grade=grade,
                season_year=year,
                duration_minutes=duration,
                max_score=max_score,
                # Пороги призёра/победителя не выдумываем — вносятся,
                # когда появятся официальные значения (real values TBD).
                threshold_prize=None,
                threshold_winner=None,
                sort_order=0,
                is_published=True,
            )
            db.session.add(p)
            db.session.flush()

            for i, (num, t) in enumerate(_variant_task_numbers(vt), start=1):
                text = (t.get('text') or '').strip()
                if not text:
                    continue
                solution = (t.get('solution') or '').strip()
                db.session.add(OlympiadTask(
                    probnik_id=p.id,
                    number=num,
                    sort_order=i,
                    difficulty=_difficulty_at(i - 1, len(vt)),
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
                    stage=_stage_key(rnd),
                ))
            db.session.flush()
        logger.info('[real_probnik] staged %s: %d tasks', code, len(vt))
        return {'code': code, 'title': _variant_title(slug, variant)}
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] create %s failed: %r', code, e)
        return None


# ─── Выбор следующего пробника ────────────────────────────────────────────

def next_real_probnik(slug: str, grade: Optional[int],
                      used_codes: set) -> Optional[Dict[str, str]]:
    """Следующий реальный вариант по порядку (свежий год → старый).

    Сначала ОДНОЗНАЧНО определяем следующий вариант (первый
    неиспользованный; когда все выданы — снова самый свежий: архив
    конечен, поведение задокументировано для пилота), затем создаём
    именно его. Порядок не «перепрыгивается» при сбое создания:
    следующий вариант выдавался бы вне очереди и разошёлся бы с
    peek_next_probnik (контекст куратора). Если создание не удалось и
    пробника нет в БД — возвращаем None (занятие-пробник без кода).
    """
    pairs = variant_codes(slug, grade)
    if not pairs:
        return None
    choice = next(((i, c, v) for i, (c, v) in enumerate(pairs, start=1)
                  if c not in used_codes), None)
    if choice is None:  # все варианты уже выдавались — снова самый свежий
        choice = (1, pairs[0][0], pairs[0][1])
    idx, code, v = choice
    made = ensure_real_probnik(code, v, slug, number=idx)
    if made:
        return made
    # создание не удалось, но пробник мог существовать раньше
    try:
        from models_olympiad import Probnik
        p = Probnik.query.filter_by(code=code).first()
        if p is not None:
            return {'code': p.code, 'title': p.title or p.code}
    except Exception as e:  # noqa: BLE001
        logger.warning('[real_probnik] fallback lookup failed: %r', e)
    return None


def peek_next_probnik(slug: str, grade: Optional[int],
                      used_codes: set) -> Optional[Dict[str, str]]:
    """Ближайший реальный вариант БЕЗ записи в БД (для контекста куратора).

    Порядок тот же, что и у next_real_probnik — куратор видит заранее,
    какой вариант олимпиады ждёт ученика на занятии-пробнике.
    """
    for code, v in variant_codes(slug, grade):
        if code in used_codes:
            continue
        return {'code': code, 'title': _variant_title(slug, v)}
    pairs = variant_codes(slug, grade)
    if pairs:
        code, v = pairs[0]
        return {'code': code, 'title': _variant_title(slug, v)}
    return None


# ─── Чертежи к задачам реального пробника ─────────────────────────────────

def figures_for_task(probnik_code: str, task_number: str) -> Dict[str, list]:
    """Чертежи условия/решения задачи реального пробника из каталога.

    Возвращает {'condition': [{'file','url'}, ...], 'solution': [...]} —
    url указывает на /static/olymp_figures/<путь> (каталогные чертежи
    лежат там, а не в /static/figures — см. templates/olympiad/*).

    Номер задачи ищется через ТУ ЖЕ нумерацию, что при создании
    OlympiadTask (_variant_task_numbers): дубли номеров каталога
    получают «день.номер» — прямое сравнение с полем num каталога
    здесь было бы неверным.
    """
    empty = {'condition': [], 'solution': []}
    if not probnik_code.startswith('real-'):
        return empty
    parts = probnik_code.split('-')
    if len(parts) < 5 or not parts[-1].startswith('g'):
        return empty
    grade = _as_int(parts[-1][1:])
    # код: real-<slug...>-<год>-<этап+теги>-g<класс>. Год — первый
    # 4-значный сегмент после slug (slug может содержать дефисы,
    # позиция года в parts не фиксирована)
    year_idx = None
    for idx in range(1, len(parts) - 1):
        cand = _as_int(parts[idx])
        if cand is not None and len(parts[idx]) == 4 and _MIN_YEAR <= cand <= 2100:
            year_idx = idx
            break
    if year_idx is None or year_idx < 2:
        return empty
    year = _as_int(parts[year_idx])
    slug = '-'.join(parts[1:year_idx])
    if year is None or grade is None or not slug:
        return empty

    # ищем вариант с этим кодом (этап определяется по коду однозначно)
    target = None
    for code, v in variant_codes(slug, grade):
        if code == probnik_code:
            target = v
            break
    if target is None:
        return empty

    # та же нумерация, что в БД: номер -> задача каталога
    numbers = dict(_variant_task_numbers(target['tasks']))
    t = numbers.get(str(task_number or '').strip())
    if t is None:
        return empty
    return {
        'condition': [_fig(f) for f in (t.get('fig_statement') or [])],
        'solution': [_fig(f) for f in (t.get('fig_solution') or [])],
    }


def _fig(path: str) -> Dict[str, str]:
    """Чертёж каталога: и файл, и публичный URL (/static/olymp_figures/...)."""
    return {'file': path, 'url': f'/static/olymp_figures/{path}'}
