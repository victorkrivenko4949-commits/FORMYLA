# services/daily_olympiad.py — профили олимпиад для «Задач дня» (пункты 5-8).
#
# Задачи дня выдаются по месячному циклу куратора (curator/monthly_cycle):
# 7 тем месяца → тема дня → задачи из FORMYLA_BANK.jsonl по (класс, тема,
# уровень). До этого модуля выбор тем не зависел от выбранной учеником
# олимпиады. Здесь — редакционные профили «что популярно в каждой
# олимпиаде», выраженные точными theme_id из theme_registry (G{grade}_T{n}).
#
# Принципы (согласованы с ревью 2026-10-28):
# * профили — это РЕДАКЦИОННЫЕ ПРИОРИТЕТЫ ПОДГОТОВКИ, а не проценты
#   популярности: база — официальные программы и реальные варианты;
# * слабость ученика первична, редакционный порядок задаёт пул и порядок
#   при отсутствии измерений;
# * точные theme_id (не названия): неизвестный ID должен выявляться
#   тестом, а не молча пропускаться;
# * профили покрывают только реально поддерживаемые классы (пересечение
#   каталога приложения и верифицированных материалов олимпиады);
# * непокрытая олимпиада НЕ подменяется молча общим пулом: статус
#   no_profile возвращается явно (в UI — честная пометка).
#
# Профили покрывают действующий прод-каталог олимпиад (olympiad_prep):
# vsosh, turnir-gorodov, lomonosov, vysshaya-proba, matprazdnik, mmo,
# euler, pokori-vorobievy-gory.

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Версия профилей: инкрементируется при изменении приоритетов — тогда
# месячные циклы помечаются устаревшими и пересобираются, а выданные
# ранее сеты сверяются по ключу контекста.
PROFILE_VERSION = 1

# ── Редакционные профили ────────────────────────────────────────────────
# Каждый профиль: класс → УПОРЯДОЧЕННЫЙ список theme_id (приоритет убывает).
# Первые темы попадают в первый месяц цикла, хвост — в последующие.
# Порядок внутри профиля — редакционный; слабость ученика (level_engine)
# переупорядочивает выборку внутри пула при наличии измерений.

OLYMPIAD_PROFILES: Dict[str, Dict] = {

    # Всероссийская олимпиада школьников по математике — школьный и
    # муниципальный этапы. База: методические рекомендации
    # (Санкт-Петербург, с. 28-29 — темы по классам 5-11) и архив
    # vos.olimpiada.ru.
    'vsosh': {
        'name': 'Всероссийская олимпиада школьников',
        'basis': [
            'https://vos.olimpiada.ru/archive — архив заданий школьного этапа',
            'Методические рекомендации по проведению школьного этапа (СПб, 5-11 классы): '
            'https://mon.tatarstan.ru/file/2529446/',
        ],
        'grade_plans': {
            5: ['G5_T03', 'G5_T02', 'G5_T17', 'G5_T08', 'G5_T07',
                'G5_T04', 'G5_T05', 'G5_T12', 'G5_T14', 'G5_T15',
                'G5_T18', 'G5_T11'],
            6: ['G6_T03', 'G6_T01', 'G6_T08', 'G6_T18', 'G6_T04',
                'G6_T06', 'G6_T09', 'G6_T13', 'G6_T19', 'G6_T12',
                'G6_T15', 'G6_T16'],
            7: ['G7_T03', 'G7_T01', 'G7_T05', 'G7_T07', 'G7_T12',
                'G7_T10', 'G7_T13', 'G7_T14', 'G7_T19', 'G7_T16',
                'G7_T02', 'G7_T04'],
            8: ['G8_T01', 'G8_T05', 'G8_T06', 'G8_T16', 'G8_T03',
                'G8_T14', 'G8_T07', 'G8_T17', 'G8_T11', 'G8_T12',
                'G8_T19', 'G8_T04'],
            9: ['G9_T01', 'G9_T05', 'G9_T16', 'G9_T07', 'G9_T06',
                'G9_T03', 'G9_T10', 'G9_T11', 'G9_T17', 'G9_T14',
                'G9_T04', 'G9_T12'],
            10: ['G10_T04', 'G10_T09', 'G10_T17', 'G10_T06', 'G10_T10',
                 'G10_T01', 'G10_T05', 'G10_T16', 'G10_T12', 'G10_T07',
                 'G10_T11', 'G10_T03'],
            11: ['G11_T04', 'G11_T10', 'G11_T17', 'G11_T05', 'G11_T11',
                 'G11_T01', 'G11_T06', 'G11_T16', 'G11_T13', 'G11_T07',
                 'G11_T19', 'G11_T02'],
        },
    },

    # Турнир городов. База: Википедия (самая частая тема — комбинаторика,
    # далее алгебра/геометрия/алгебра-ЧТ), архив www.turgor.ru.
    'turnir-gorodov': {
        'name': 'Турнир городов',
        'basis': [
            'https://www.turgor.ru/ — архив заданий (осенний/весенний туры)',
            'https://ru.wikipedia.org/wiki/Турнир_городов — статистика тем: '
            'комбинаторика чаще всего, далее алгебра/ЧТ/геометрия',
        ],
        'grade_plans': {
            8: ['G8_T10', 'G8_T14', 'G8_T15', 'G8_T12', 'G8_T11',
                'G8_T07', 'G8_T17', 'G8_T01', 'G8_T18', 'G8_T19',
                'G8_T13', 'G8_T04'],
            9: ['G9_T10', 'G9_T14', 'G9_T15', 'G9_T12', 'G9_T11',
                'G9_T07', 'G9_T17', 'G9_T01', 'G9_T18', 'G9_T03',
                'G9_T13', 'G9_T16'],
            10: ['G10_T10', 'G10_T14', 'G10_T15', 'G10_T12', 'G10_T11',
                 'G10_T07', 'G10_T17', 'G10_T01', 'G10_T18', 'G10_T04',
                 'G10_T13', 'G10_T05'],
            11: ['G11_T11', 'G11_T15', 'G11_T16', 'G11_T13', 'G11_T12',
                 'G11_T07', 'G11_T17', 'G11_T01', 'G11_T19', 'G11_T04',
                 'G11_T14', 'G11_T05'],
        },
    },

    # Олимпиада «Ломоносов». База: реальные варианты (mathus.ru PDF):
    # арифметика/ребусы, ЧТ, геометрия, комбинаторика, игры, текстовые.
    'lomonosov': {
        'name': 'Олимпиада «Ломоносов»',
        'basis': [
            'https://olimpiada.ru/activity/348/tasks — архив заданий',
            'Реальные варианты: https://mathus.ru/olympiads/lomonosov25_5-6.pdf, '
            'lomonosov25_9.pdf, lomonosov25_10-11.pdf — арифметика, ЧТ, геометрия',
        ],
        'grade_plans': {
            5: ['G5_T03', 'G5_T01', 'G5_T02', 'G5_T17', 'G5_T11',
                'G5_T07', 'G5_T08', 'G5_T04', 'G5_T10', 'G5_T14',
                'G5_T16', 'G5_T12'],
            6: ['G6_T03', 'G6_T01', 'G6_T02', 'G6_T18', 'G6_T12',
                'G6_T08', 'G6_T04', 'G6_T10', 'G6_T15', 'G6_T19',
                'G6_T16', 'G6_T13'],
            7: ['G7_T03', 'G7_T04', 'G7_T01', 'G7_T12', 'G7_T16',
                'G7_T07', 'G7_T10', 'G7_T13', 'G7_T18', 'G7_T05',
                'G7_T11', 'G7_T19'],
            8: ['G8_T03', 'G8_T04', 'G8_T01', 'G8_T12', 'G8_T16',
                'G8_T06', 'G8_T10', 'G8_T13', 'G8_T18', 'G8_T09',
                'G8_T11', 'G8_T17'],
            9: ['G9_T04', 'G9_T03', 'G9_T01', 'G9_T12', 'G9_T16',
                'G9_T06', 'G9_T10', 'G9_T13', 'G9_T18', 'G9_T05',
                'G9_T11', 'G9_T17'],
            10: ['G10_T03', 'G10_T04', 'G10_T01', 'G10_T12', 'G10_T16',
                 'G10_T06', 'G10_T10', 'G10_T13', 'G10_T18', 'G10_T05',
                 'G10_T11', 'G10_T17'],
            11: ['G11_T04', 'G11_T03', 'G11_T01', 'G11_T13', 'G11_T17',
                 'G11_T06', 'G11_T11', 'G11_T14', 'G11_T19', 'G11_T05',
                 'G11_T12', 'G11_T18'],
        },
    },

    # «Высшая проба» (НИУ ВШЭ). База: официальные списки тем по классам
    # (olymp.hse.ru PDFs): функции/графики, уравнения, неравенства,
    # системы, комбинаторика и логика, ЧТ, геометрия.
    'vysshaya-proba': {
        'name': 'Высшая проба (НИУ ВШЭ)',
        'basis': [
            'https://olymp.hse.ru/data/2018/03/23/1149612685/vp-matematika-topics.pdf — '
            'официальные списки тем по классам 7-11',
            'https://olymp.hse.ru/data/2024/09/24/2104834895/ — программа '
            '«Комбинаторика и логика» (ноябрь 2024): перебор, Дирихле, графы, игры',
        ],
        'grade_plans': {
            8: ['G8_T06', 'G8_T05', 'G8_T07', 'G8_T10', 'G8_T01',
                'G8_T16', 'G8_T11', 'G8_T03', 'G8_T14', 'G8_T12',
                'G8_T17', 'G8_T08'],
            9: ['G9_T06', 'G9_T05', 'G9_T07', 'G9_T10', 'G9_T01',
                'G9_T16', 'G9_T11', 'G9_T04', 'G9_T14', 'G9_T12',
                'G9_T17', 'G9_T09'],
            10: ['G10_T06', 'G10_T05', 'G10_T07', 'G10_T10', 'G10_T01',
                 'G10_T16', 'G10_T11', 'G10_T03', 'G10_T14', 'G10_T12',
                 'G10_T17', 'G10_T09'],
            11: ['G11_T06', 'G11_T05', 'G11_T07', 'G11_T11', 'G11_T01',
                 'G11_T17', 'G11_T12', 'G11_T03', 'G11_T15', 'G11_T13',
                 'G11_T16', 'G11_T10'],
        },
    },

    # «Покори Воробьёвы горы!» (МГУ). База: ключи и варианты (mathus.ru,
    # pvg.mk.ru): текстовые задачи, ЧТ, инварианты, последовательности,
    # игры, геометрия; 10-11 — функции и параметры.
    'pokori-vorobievy-gory': {
        'name': '«Покори Воробьёвы горы!»',
        'basis': [
            'https://pvg.mk.ru/ — официальная страница олимпиады',
            'Реальные варианты и ключи: https://mathus.ru/olympiads/pvg23_10-11.pdf, '
            'pvg23_5-6_keys.pdf — текстовые, ЧТ, геометрия, параметры',
        ],
        'grade_plans': {
            5: ['G5_T04', 'G5_T05', 'G5_T02', 'G5_T09', 'G5_T11',
                'G5_T07', 'G5_T15', 'G5_T17', 'G5_T14', 'G5_T01',
                'G5_T10', 'G5_T16'],
            6: ['G6_T04', 'G6_T05', 'G6_T01', 'G6_T10', 'G6_T12',
                'G6_T08', 'G6_T16', 'G6_T19', 'G6_T15', 'G6_T02',
                'G6_T11', 'G6_T18'],
            7: ['G7_T05', 'G7_T06', 'G7_T01', 'G7_T09', 'G7_T10',
                'G7_T08', 'G7_T13', 'G7_T19', 'G7_T14', 'G7_T02',
                'G7_T11', 'G7_T17'],
            8: ['G8_T09', 'G8_T01', 'G8_T08', 'G8_T10', 'G8_T14',
                'G8_T13', 'G8_T18', 'G8_T19', 'G8_T04', 'G8_T12',
                'G8_T11', 'G8_T16'],
            9: ['G9_T01', 'G9_T09', 'G9_T10', 'G9_T14', 'G9_T13',
                'G9_T18', 'G9_T16', 'G9_T03', 'G9_T12', 'G9_T11',
                'G9_T05', 'G9_T06'],
            10: ['G10_T01', 'G10_T09', 'G10_T10', 'G10_T14', 'G10_T13',
                 'G10_T18', 'G10_T16', 'G10_T03', 'G10_T12', 'G10_T11',
                 'G10_T05', 'G10_T06'],
            11: ['G11_T01', 'G11_T09', 'G11_T11', 'G11_T15', 'G11_T14',
                 'G11_T19', 'G11_T17', 'G11_T03', 'G11_T13', 'G11_T12',
                 'G11_T05', 'G11_T06'],
        },
    },

    # Московская математическая олимпиада (ММО/МОШ). База: архив
    # olympiads.mccme.ru/mmo — ЧТ, игры, геометрия, комбинаторика,
    # конструкции, неравенства.
    'mmo': {
        'name': 'Московская математическая олимпиада',
        'basis': [
            'https://olympiads.mccme.ru/mmo/ — архив заданий и решений 8-11 классов',
            'https://mos.olimpiada.ru/upload/files/olympiad/Gorodsik/6-7/2019-20/otvety_i_resheniya.pdf '
            '— типовые темы: ЧТ, игры, конструкции',
        ],
        'grade_plans': {
            8: ['G8_T01', 'G8_T13', 'G8_T16', 'G8_T10', 'G8_T14',
                'G8_T03', 'G8_T11', 'G8_T17', 'G8_T07', 'G8_T15',
                'G8_T19', 'G8_T12'],
            9: ['G9_T01', 'G9_T13', 'G9_T16', 'G9_T10', 'G9_T14',
                'G9_T04', 'G9_T11', 'G9_T17', 'G9_T07', 'G9_T15',
                'G9_T12', 'G9_T03'],
            10: ['G10_T01', 'G10_T13', 'G10_T16', 'G10_T10', 'G10_T14',
                 'G10_T04', 'G10_T11', 'G10_T17', 'G10_T07', 'G10_T15',
                 'G10_T12', 'G10_T03'],
            11: ['G11_T01', 'G11_T14', 'G11_T17', 'G11_T11', 'G11_T15',
                 'G11_T04', 'G11_T12', 'G11_T18', 'G11_T07', 'G11_T16',
                 'G11_T13', 'G11_T03'],
        },
    },

    # Олимпиада имени Леонарда Эйлера — 8 класс (региональный уровень
    # ВсОШ для восьмиклассников). База: matol.ru — делимость, неравенства,
    # графы, игры, геометрия.
    'euler': {
        'name': 'Олимпиада имени Леонарда Эйлера',
        'basis': [
            'https://olimpiada.ru/activity/29 — олимпиада для 8 класса',
            'https://matol.ru/ — решения регионального этапа: '
            'делимость, неравенства, графы, игры, геометрия',
        ],
        'grade_plans': {
            8: ['G8_T01', 'G8_T07', 'G8_T12', 'G8_T13', 'G8_T16',
                'G8_T03', 'G8_T14', 'G8_T11', 'G8_T17', 'G8_T10',
                'G8_T18', 'G8_T04'],
        },
    },

    # Математический праздник — 6-7 классы. База: архив
    # olympiads.mccme.ru/matprazdnik — разрезания, конструкции, ребусы,
    # логика, взвешивания, делимость.
    'matprazdnik': {
        'name': 'Математический праздник',
        'basis': [
            'https://olympiads.mccme.ru/matprazdnik/ — задачи и решения 6-7 классов',
            'https://olympiads.mccme.ru/matprazdnik/2016/66-17%20(1).pdf — типовые темы: '
            'разрезания, ребусы, логика, весы',
        ],
        'grade_plans': {
            6: ['G6_T03', 'G6_T19', 'G6_T08', 'G6_T16', 'G6_T12',
                'G6_T01', 'G6_T10', 'G6_T11', 'G6_T15', 'G6_T17',
                'G6_T13', 'G6_T18'],
            7: ['G7_T03', 'G7_T19', 'G7_T08', 'G7_T12', 'G7_T10',
                'G7_T01', 'G7_T09', 'G7_T11', 'G7_T14', 'G7_T18',
                'G7_T13', 'G7_T16'],
        },
    },
}


def profile_for(slug: str, grade: Optional[int]) -> Optional[Dict]:
    """Профиль олимпиады для класса: {'slug', 'name', 'version', 'themes'}.

    Возвращает None, если олимпиада не поддерживается профилями или
    профиль не покрывает этот класс (не молча подменяя общим пулом).
    """
    if not slug or grade is None:
        return None
    prof = OLYMPIAD_PROFILES.get(slug)
    if not prof:
        return None
    try:
        grade = int(grade)
    except (TypeError, ValueError):
        return None
    themes = (prof.get('grade_plans') or {}).get(grade)
    if not themes:
        return None
    return {
        'slug': slug,
        'name': prof['name'],
        'version': PROFILE_VERSION,
        'themes': list(themes),
    }


def user_olympiad(user_id: int) -> Optional[Dict]:
    """Выбранная учеником олимпиада: {'slug', 'name', 'grade'} или None.

    Источник: активный PrepPlan → OlympiadPrep.slug. Класс — из состояния
    куратора (anketa), т.к. именно он управляет месячным циклом задач дня.
    """
    try:
        from models import PrepPlan, OlympiadPrep, User
        plan = (
            PrepPlan.query.filter_by(user_id=user_id, status='active')
            .order_by(PrepPlan.id.desc())
            .first()
        )
        if not plan or not plan.olympiad_id:
            return None
        olympiad = db_get_olympiad(plan.olympiad_id)
        if not olympiad:
            return None
        grade = user_cycle_grade(user_id)
        if not grade:
            return None
        return {
            'slug': olympiad.slug,
            'name': olympiad.name,
            'grade': grade,
            'plan_id': plan.id,
        }
    except Exception:
        logger.exception('daily_olympiad.user_olympiad failed user=%s', user_id)
        return None


def db_get_olympiad(olympiad_id):
    from models import OlympiadPrep
    return OlympiadPrep.query.get(olympiad_id)


def user_cycle_grade(user_id: int) -> Optional[int]:
    """Единый effective_grade для профиля, банка и контекста.

    Приоритет (ревью 2026-10-28, раунд 4): явный класс подготовки
    PrepPlan.target_grade → класс куратора (CuratorState.grade) →
    анкета (intake/onboarding) → preferred_grade/class_level пользователя.
    """
    # 1. явный класс подготовки из активного плана
    try:
        from models import PrepPlan
        plan = (
            PrepPlan.query.filter_by(user_id=user_id, status='active')
            .order_by(PrepPlan.id.desc())
            .first()
        )
        if plan is not None and getattr(plan, 'target_grade', None):
            return int(plan.target_grade)
    except Exception:
        pass
    # 2. класс куратора
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is not None and getattr(cs, 'grade', None):
            return int(cs.grade)
    except Exception:
        logger.exception('daily_olympiad.user_cycle_grade failed user=%s', user_id)
    # 3. анкета
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is not None and cs.prep_state:
            prep = cs.prep_state
            if isinstance(prep, str):
                import json as _json
                try:
                    prep = _json.loads(prep)
                except (ValueError, TypeError):
                    prep = {}
            if isinstance(prep, dict):
                for key in ('intake', 'onboarding'):
                    block = prep.get(key) or {}
                    if isinstance(block, dict) and block.get('grade'):
                        return int(block['grade'])
    except Exception:
        pass
    # 4. пользователь
    try:
        from models import User
        u = User.query.get(user_id)
        if u is not None:
            g = getattr(u, 'preferred_grade', None) or getattr(u, 'class_level', None)
            if g:
                return int(g)
    except Exception:
        pass
    return None


def _current_cycle_marks(user_id: int) -> Dict:
    """Метк месячного цикла (olympiad_*) без изменения состояния."""
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is None or not cs.prep_state:
            return {}
        prep = cs.prep_state
        if isinstance(prep, str):
            import json as _json
            try:
                prep = _json.loads(prep)
            except (ValueError, TypeError):
                return {}
        mc = (prep or {}).get('monthly_cycle') or {}
        return mc if isinstance(mc, dict) else {}
    except Exception:
        return {}


def _today_set_context(user_id: int) -> Optional[Dict]:
    """Контекст сегодняшней выдачи задач дня (если есть).

    OLYMPIAD_DAILY_V1: DailyTaskSet.olympiad_context — основной источник;
    fallback — штамп в bank_issues (бан-поток маршрута не создаёт сет,
    задачи выдаются из daily_task_bank; штамп ставится в build_daily_set).
    """
    try:
        from datetime import date as _date
        from daily_tasks.models import DailyTaskSet
        s = DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=_date.today(),
        ).first()
        if s is not None and s.olympiad_context:
            import json as _json
            ctx = _json.loads(s.olympiad_context)
            if isinstance(ctx, dict):
                return ctx
        # бан-поток: сет не создаётся, смотрим штамп в bank_issues
        from models import BankIssue
        bi = (
            BankIssue.query
            .filter(
                BankIssue.user_id == user_id,
                BankIssue.issued_date == _date.today(),
                BankIssue.olympiad_context.isnot(None),
            )
            .first()
        )
        if bi is not None and bi.olympiad_context:
            import json as _json
            ctx = _json.loads(bi.olympiad_context)
            return ctx if isinstance(ctx, dict) else None
        return None
    except Exception:
        return None


def _today_set_exists(user_id: int) -> bool:
    """Есть ли вообще выдача задач на сегодня (сет или бан-выдача).

    Ревью раунда 5: выдача БЕЗ контекста олимпиады не считается
    автоматически совместимой с профилем — её тоже честно помечаем.
    """
    try:
        from datetime import date as _date
        from daily_tasks.models import DailyTaskSet
        if DailyTaskSet.query.filter_by(
            user_id=user_id, target_date=_date.today(),
        ).first() is not None:
            return True
        from models import BankIssue, db as _db
        return _db.session.query(
            BankIssue.query.filter(
                BankIssue.user_id == user_id,
                BankIssue.issued_date == _date.today(),
            ).exists()
        ).scalar() or False
    except Exception:
        return False


def daily_context(user_id: int) -> Dict:
    """Фактический контекст олимпиады для страницы задач дня и API.

    Разделяем выбранный профиль и фактический контекст выдачи (ревью
    раунда 4): бейдж «подготовка к олимпиаде X» показывается только если
    цикл ДЕЙСТВИТЕЛЬНО построен из профиля, а показанный сет выдан под
    тот же контекст. Сет под прежнюю олимпиаду честно помечается как
    прежняя выдача (stale_set), а не подписывается новой.

    Ревью раунда 5: сравниваем ПОЛНЫЙ ключ контекста (слаг+класс+
    версия профиля), а не только слаг — смена класса (ВсОШ-9 →
    ВсОШ-11) тоже честно помечается. Выдача без контекста (до выбора
    олимпиады / до этого деплоя) не считается совместимой.

    status:
      * 'no_olympiad'  — олимпиада не выбрана: поведение без изменений;
      * 'no_profile'   — выбрана, но профиль для неё/класса не готов;
      * 'pending'      — профиль есть, но цикл ещё не применён;
      * 'stale_set'    — сегодняшний сет выдан под ПРЕЖНИЙ контекст
                         (или без контекста); новый профиль — со следующей
                         выдачи;
      * 'applied'      — цикл из профиля, сет совместим.
    """
    uo = user_olympiad(user_id)
    if not uo:
        return {'status': 'no_olympiad'}
    prof = profile_for(uo['slug'], uo['grade'])
    if not prof:
        return {
            'status': 'no_profile',
            'slug': uo['slug'],
            'name': uo['name'],
            'grade': uo['grade'],
        }
    base = {
        'slug': prof['slug'],
        'name': prof['name'],
        'grade': uo['grade'],
        'profile_version': prof['version'],
    }
    # Ревью раунда 5: сравниваем ПОЛНЫЙ ключ контекста (слаг+класс+версия),
    # а не только слаг. Выдача без контекста — тоже несовместима.
    if _today_set_exists(user_id):
        set_ctx = _today_set_context(user_id)
        cur_key = context_key(user_id) or {}
        if not set_ctx:
            # выдан до выбора олимпиады / до этого деплоя — не подписываем
            # новой олимпиадой, новый профиль действует со следующей выдачи
            return {
                'status': 'stale_set',
                'slug': prof['slug'],
                'name': prof['name'],
                'grade': uo['grade'],
                'former_name': None,
                'profile_version': prof['version'],
            }
        if (
            set_ctx.get('olympiad_slug') != cur_key.get('olympiad_slug')
            or set_ctx.get('grade') != cur_key.get('grade')
            or set_ctx.get('profile_version') != cur_key.get('profile_version')
        ):
            former = OLYMPIAD_PROFILES.get(set_ctx.get('olympiad_slug') or '', {}) or {}
            return {
                'status': 'stale_set',
                'slug': prof['slug'],
                'name': prof['name'],
                'grade': uo['grade'],
                'former_name': former.get('name') or set_ctx.get('olympiad_slug'),
                'profile_version': prof['version'],
            }
    # цикл действительно построен из профиля?
    mc = _current_cycle_marks(user_id)
    marks_match = (
        mc.get('olympiad_slug') == prof['slug']
        and mc.get('olympiad_profile_version') == prof['version']
        and mc.get('olympiad_grade') == uo['grade']
        and bool(mc.get('themes'))
    )
    if not marks_match:
        return {'status': 'pending', **base}
    return {'status': 'applied', **base}


def context_key(user_id: int) -> Optional[Dict]:
    """Ключ совместимости выданного сета: слаг + класс + версия профиля.

    Сравнивается с olympiad_context сета: несовпадение = сет выдан под
    другой контекст (смена олимпиады/класса/профиля).
    """
    try:
        uo = user_olympiad(user_id)
        if not uo:
            return None
        return {
            'olympiad_slug': uo['slug'],
            'grade': uo['grade'],
            'profile_version': PROFILE_VERSION,
        }
    except Exception:
        return None
