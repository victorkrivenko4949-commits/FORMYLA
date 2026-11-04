# -*- coding: utf-8 -*-
"""tests/test_daily_olympiad.py — OLYMPIAD_DAILY_V1: задачи дня под выбранную
олимпиаду (пункты 5-8).

Проверки детерминированные, без LLM:
* профили — точные theme_id из theme_registry (неизвестный ID — ошибка
  теста, а не молчаливый пропуск);
* каждая тема профиля обеспечена задачами в FORMYLA_BANK.jsonl для этого
  класса (иначе «Задач пока нет»);
* месячный цикл пользователя с олимпиадой строится из профиля, с
  приоритетом слабости ученика; без олимпиады — прежнее поведение,
  строго без изменений;
* неподдерживаемая олимпиада не подменяется молча общим пулом
  (статус no_profile, цикл не трогается);
* rollover (31 день) продолжает профиль, а не уходит в общий пул;
* apply идемпотентен и не ломает текущую тему дня;
* выданный сет несёт контекст: смена олимпиады без ответов → перевыпуск,
  с ответами — история сохраняется;
* страница задач дня честно помечает олимпиаду.

Run: pytest tests/test_daily_olympiad.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest


# ─── Хелперы ─────────────────────────────────────────────────────────────


def _mk_user(app, email: str, grade: int = 9):
    from models import db, User
    from models_curator import CuratorState
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, nickname=email.split('@')[0])
            db.session.add(u)
            db.session.flush()
        cs = CuratorState.query.filter_by(user_id=u.id).first()
        if cs is None:
            cs = CuratorState(user_id=u.id)
            db.session.add(cs)
        cs.grade = grade
        cs.prep_state = json.dumps({
            'intake': {'completed': True, 'grade': grade},
        })
        db.session.commit()
        return u.id


def _mk_olympiad(app, slug: str, name: str):
    from models import db, OlympiadPrep
    with app.app_context():
        o = OlympiadPrep.query.filter_by(slug=slug).first()
        if not o:
            o = OlympiadPrep(slug=slug, name=name, short_name=name[:40],
                            grades=json.dumps([5, 6, 7, 8, 9, 10, 11]))
            db.session.add(o)
            db.session.flush()
        db.session.commit()
        return o.id


def _mk_plan(app, user_id: int, olympiad_id: int):
    from models import db, PrepPlan
    with app.app_context():
        plan = PrepPlan.query.filter_by(user_id=user_id).first()
        if plan:
            plan.olympiad_id = olympiad_id
            plan.status = 'active'
        else:
            plan = PrepPlan(user_id=user_id, olympiad_id=olympiad_id,
                            status='active',
                            start_date=datetime.utcnow().date(),
                            target_date=datetime.utcnow().date() + timedelta(days=90))
            db.session.add(plan)
        db.session.commit()
        return plan.id


def _get_mc(app, user_id: int):
    from models_curator import CuratorState
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if not cs or not cs.prep_state:
            return {}
        raw = cs.prep_state
        prep = raw if isinstance(raw, dict) else json.loads(raw)
        return prep.get('monthly_cycle') or {}


def _set_probe_done_today(app, user_id: int):
    """Снять утренний срез: probe_last_date = сегодня И тема дня закрыта
    в done_themes (иначе get_cycle_info/pick_daily_set считают цикл
    blocked и задачи дня не выдаются — рендерится ветка «Сначала тест»)."""
    from models import db
    from models_curator import CuratorState
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        prep = cs.prep_state
        if isinstance(prep, str):
            prep = json.loads(prep)
        mc = prep.get('monthly_cycle') or {}
        mc['last_probe_date'] = datetime.now(timezone.utc).date().isoformat()
        # тема дня считается протестированной
        from curator.monthly_cycle import get_cycle_info
        cur = get_cycle_info(user_id).get('current_theme')
        if cur:
            done = list(mc.get('done_themes') or [])
            if cur not in done:
                done.append(cur)
            mc['done_themes'] = done
        prep['monthly_cycle'] = mc
        cs.prep_state = json.dumps(prep, ensure_ascii=False)
        db.session.commit()


# ─── Валидность профилей ────────────────────────────────────────────────


def test_profiles_reference_real_registry(app):
    from services.daily_olympiad import OLYMPIAD_PROFILES
    from services.theme_registry import themes_of_grade
    problems = []
    for slug, prof in OLYMPIAD_PROFILES.items():
        for grade, themes in prof['grade_plans'].items():
            valid = set(themes_of_grade(grade))
            for t in themes:
                if t not in valid:
                    problems.append(f'{slug} класс {grade}: неизвестная тема {t}')
    assert not problems, 'Профили ссылаются на темы вне реестра: ' + '; '.join(problems)


def test_profiles_have_bank_tasks():
    """Каждая тема профиля должна иметь задачи в банке для этого класса."""
    from collections import Counter
    from services.daily_olympiad import OLYMPIAD_PROFILES
    from services.theme_registry import theme_title
    bank = Counter()
    with open(_ROOT / 'FORMYLA_BANK.jsonl', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                bank[(r.get('grade'), r.get('topic'))] += 1
    problems = []
    for slug, prof in OLYMPIAD_PROFILES.items():
        for grade, themes in prof['grade_plans'].items():
            for t in themes:
                if bank.get((grade, theme_title(t)), 0) == 0:
                    problems.append(f'{slug} класс {grade}: тема {t} без задач в банке')
    assert not problems, 'Темы профилей без покрытия банком: ' + '; '.join(problems)


def test_profile_for_boundaries(app):
    from services.daily_olympiad import profile_for
    assert profile_for('vsosh', 9) is not None
    assert profile_for('no-such-olympiad', 9) is None
    assert profile_for('vsosh', 12) is None   # класс не покрывается профилем
    assert profile_for('vsosh', None) is None


# ─── Контекст и цикл ────────────────────────────────────────────────────


def test_daily_context_applied(app):
    from services.daily_olympiad import daily_context
    from curator.monthly_cycle import build_or_get_cycle
    uid = _mk_user(app, 'odo1@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    build_or_get_cycle(uid, 9)  # цикл из профиля — только тогда applied
    ctx = daily_context(uid)
    assert ctx['status'] == 'applied'
    assert ctx['slug'] == 'vsosh'
    assert ctx['grade'] == 9


def test_daily_context_pending_until_cycle_applied(app):
    """Профиль выбран, но цикл ещё не применён — честный pending."""
    from services.daily_olympiad import daily_context
    uid = _mk_user(app, 'odo12@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    assert daily_context(uid)['status'] == 'pending'


def test_daily_context_no_olympiad(app):
    from services.daily_olympiad import daily_context
    uid = _mk_user(app, 'odo2@test.local', grade=9)
    assert daily_context(uid) == {'status': 'no_olympiad'}


def test_cycle_built_from_profile(app):
    from curator.monthly_cycle import build_or_get_cycle
    from services.daily_olympiad import profile_for
    uid = _mk_user(app, 'odo3@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    mc = build_or_get_cycle(uid, 9)
    prof = profile_for('vsosh', 9)
    assert len(mc['themes']) == 7
    assert set(mc['themes']) <= set(prof['themes'])
    assert mc['olympiad_slug'] == 'vsosh'
    assert mc['olympiad_grade'] == 9


def test_cycle_without_olympiad_unchanged(app):
    """Без олимпиады — прежнее поведение, строго без изменений."""
    from curator.monthly_cycle import build_or_get_cycle
    uid = _mk_user(app, 'odo4@test.local', grade=9)
    mc = build_or_get_cycle(uid, 9)
    assert len(mc['themes']) == 7
    assert 'olympiad_slug' not in mc
    assert 'olympiad_unsupported' not in mc


def test_unsupported_slug_no_silent_generic(app):
    """Неподдерживаемая олимпиада: статус no_profile, цикл НЕ подменяется."""
    from curator.monthly_cycle import build_or_get_cycle, apply_olympiad_cycle
    from services.daily_olympiad import daily_context
    uid = _mk_user(app, 'odo5@test.local', grade=9)
    oid = _mk_olympiad(app, 'unknown-slug', 'Неизвестная олимпиада')
    _mk_plan(app, uid, oid)
    mc_before = build_or_get_cycle(uid, 9)
    ctx = daily_context(uid)
    assert ctx['status'] == 'no_profile'
    assert ctx['slug'] == 'unknown-slug'
    res = apply_olympiad_cycle(uid)
    assert res['applied'] is False
    assert res['reason'] == 'no_profile'
    mc_after = _get_mc(app, uid)
    assert mc_after['themes'] == mc_before['themes']       # цикл не тронут
    assert mc_after.get('olympiad_unsupported') is True     # пометка честная


def test_weakness_orders_selection(app):
    """Слабость ученика первична: измеренные темы идут раньше."""
    from curator.monthly_cycle import build_or_get_cycle
    from models import db
    from models_curator import CuratorState
    uid = _mk_user(app, 'odo6@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)

    # без измерений — редакционный порядок (первая тема окна)
    mc = build_or_get_cycle(uid, 9)
    assert mc['themes'][0] == 'G9_T01'

    # слабость в теме окна (G9_T10, позиция 7 пула) → она первая
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=uid).first()
        cs.level_by_theme = json.dumps({
            'G9_T10': {'mu': 1.0},   # очень слаб
            'G9_T01': {'mu': 4.0},   # силён
        })
        db.session.commit()
    from curator.monthly_cycle import _get_monthly_cycle, _save_monthly_cycle
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=uid).first()
        raw = _get_monthly_cycle(cs)
        raw.pop('themes', None)      # заставить пересобрать темы
        _save_monthly_cycle(cs, raw)
        db.session.commit()
    mc2 = build_or_get_cycle(uid, 9)
    assert mc2['themes'][0] == 'G9_T10', 'слабейшая тема должна идти первой'


def test_by_section_fallback_orders_selection(app):
    """level_by_theme пуст, но by_section заполнен (анкета): темы слабого
    раздела идут раньше — случай, который просило проверить ревью."""
    from curator.monthly_cycle import build_or_get_cycle
    from models import db
    from models_curator import CuratorState
    uid = _mk_user(app, 'odo13@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    # слабый раздел — геометрия (в окне есть G9_T16)
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=uid).first()
        cs.level_mu = 3.0
        cs.level_sigma = 0.5
        cs.level_by_section = json.dumps({
            'algebra': {'mu': 4.0, 'sigma': 0.5, 'n': 3},
            'geometry': {'mu': 1.2, 'sigma': 0.5, 'n': 3},
            'number_theory': {'mu': 3.5, 'sigma': 0.5, 'n': 3},
            'combinatorics': {'mu': 3.0, 'sigma': 0.5, 'n': 3},
            'logic': {'mu': 3.0, 'sigma': 0.5, 'n': 3},
        })
        db.session.commit()
    mc = build_or_get_cycle(uid, 9)
    assert mc['themes'][0] == 'G9_T16', (
        'тема слабого раздела (геометрия) должна идти первой при пустом level_by_theme'
    )


def test_section_cap_strict(app):
    """MAX_PER_SECTION действует строго: не более 2 тем на секцию."""
    from curator.monthly_cycle import build_or_get_cycle
    from services.theme_registry import section_of_theme
    from collections import Counter
    uid = _mk_user(app, 'odo14@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    mc = build_or_get_cycle(uid, 9)
    counts = Counter(section_of_theme(t) or '?' for t in mc['themes'])
    assert all(c <= 2 for c in counts.values()), f'нарушен лимит секций: {counts}'


def test_rotation_across_months_no_stuck_seven(app):
    """Ротация оффсетом: хвост профиля ротируется между месяцами —
    «залипшей» семёрки нет (4 последовательных месяца, пул из 12 тем)."""
    from curator.monthly_cycle import build_or_get_cycle, get_cycle_info, _save_monthly_cycle, _get_monthly_cycle
    from models import db
    from models_curator import CuratorState
    from services.daily_olympiad import profile_for
    uid = _mk_user(app, 'odo15@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    prof = profile_for('vsosh', 9)
    assert len(prof['themes']) == 12

    months = []
    mc = build_or_get_cycle(uid, 9)
    months.append(list(mc['themes']))
    for _ in range(3):
        # «месяц прошёл»: 32 дня назад + finished
        with app.app_context():
            cs = CuratorState.query.filter_by(user_id=uid).first()
            raw = _get_monthly_cycle(cs)
            raw['started_at'] = (
                datetime.now(timezone.utc) - timedelta(days=32)
            ).isoformat()
            raw['finished_at'] = datetime.now(timezone.utc).isoformat()
            _save_monthly_cycle(cs, raw)
            db.session.commit()
        info = get_cycle_info(uid)
        months.append(list(info['themes']))
    # все 12 тем профиля прошли за 4 месяца
    union = set()
    for m in months:
        union |= set(m)
    assert union == set(prof['themes']), (
        f'за 4 месяца должны ротироваться все темы профиля, прошло: {sorted(union)}'
    )
    # месяц 3 не повторяет месяц 1 (нет «залипания»)
    assert set(months[2]) != set(months[0]) or sorted(months[2]) != sorted(months[0]), (
        'третий месяц не должен быть копией первого'
    )


def test_rollover_continues_olympiad(app):
    """После 31 дня цикл продолжается из профиля, а не из общего пула."""
    from curator.monthly_cycle import build_or_get_cycle, get_cycle_info, _save_monthly_cycle
    from models import db
    from models_curator import CuratorState
    from services.daily_olympiad import profile_for
    uid = _mk_user(app, 'odo7@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    build_or_get_cycle(uid, 9)
    prof = profile_for('vsosh', 9)

    # «месяц прошёл»: started_at 32 дня назад
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=uid).first()
        raw = cs.prep_state
        prep = raw if isinstance(raw, dict) else json.loads(raw)
        prep['monthly_cycle']['started_at'] = (
            datetime.now(timezone.utc) - timedelta(days=32)
        ).isoformat()
        _save_monthly_cycle(cs, prep['monthly_cycle'])
        db.session.commit()

    info = get_cycle_info(uid)
    assert info.get('themes')
    assert set(info['themes']) <= set(prof['themes']), (
        'rollover должен продолжать профиль олимпиады, а не общий пул'
    )
    mc_now = _get_mc(app, uid)
    assert mc_now.get('olympiad_slug') == 'vsosh'


def test_apply_idempotent_preserves_current_day(app):
    """Смена олимпиады: цикл пересобран, тема дня сохранена; идемпотентно."""
    from curator.monthly_cycle import apply_olympiad_cycle, build_or_get_cycle
    from services.daily_olympiad import profile_for
    uid = _mk_user(app, 'odo8@test.local', grade=9)
    oid_vsosh = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    oid_lomonosov = _mk_olympiad(app, 'lomonosov', 'Олимпиада «Ломоносов»')
    _mk_plan(app, uid, oid_vsosh)
    mc = build_or_get_cycle(uid, 9)
    # «сегодня 10-й день цикла» — сдвигаем started_at на 9 дней назад
    from curator.monthly_cycle import _save_monthly_cycle, _get_monthly_cycle
    from models import db
    from models_curator import CuratorState
    with app.app_context():
        cs = CuratorState.query.filter_by(user_id=uid).first()
        raw = _get_monthly_cycle(cs)
        raw['started_at'] = (
            datetime.now(timezone.utc) - timedelta(days=9)
        ).isoformat()
        _save_monthly_cycle(cs, raw)
        db.session.commit()
    day_idx = 10
    cur = mc['themes'][(day_idx - 1) % len(mc['themes'])]
    # смена олимпиады → цикл пересобирается под новый профиль
    _mk_plan(app, uid, oid_lomonosov)
    res = apply_olympiad_cycle(uid)
    assert res['applied'] is True
    assert res['reason'] == 'rebuilt'
    new_mc = _get_mc(app, uid)
    # текущая тема дня сохранена на своей позиции
    assert new_mc['themes'][(day_idx - 1) % len(new_mc['themes'])] == cur
    assert set(new_mc['themes']) <= set(profile_for('lomonosov', 9)['themes'])
    # идемпотентность
    res2 = apply_olympiad_cycle(uid)
    assert res2['reason'] == 'already'
    assert _get_mc(app, uid)['themes'] == new_mc['themes']


def test_apply_second_circle_on_exhaustion(app):
    """Исчерпание тем профиля — второй круг профиля, НЕ общий пул."""
    from curator.monthly_cycle import _olympiad_cycle_themes
    from services.daily_olympiad import profile_for
    uid = _mk_user(app, 'odo9@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)
    prof = profile_for('vsosh', 9)
    covered = set(prof['themes'])  # всё покрыто
    res = _olympiad_cycle_themes(uid, 9, covered)
    assert res is not None
    assert set(res[0]) <= set(prof['themes']), (
        'при исчерпании профиль должен начаться вторым кругом'
    )


# ─── Контекст сета и перевыпуск ─────────────────────────────────────────


def test_pick_daily_set_context_nondestructive(app):
    """Смена олимпиады: сегодняшний сет СОХРАНЯЕТСЯ (даже без ответов) —
    история не удаляется; честная пометка stale_context; новый профиль
    действует со следующей выдачи (ревью раунда 4: удаление не одобрено)."""
    uid = _mk_user(app, 'odo10@test.local', grade=9)
    oid_vsosh = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    oid_lomonosov = _mk_olympiad(app, 'lomonosov', 'Олимпиада «Ломоносов»')
    _mk_plan(app, uid, oid_vsosh)

    from curator.monthly_cycle import build_or_get_cycle
    build_or_get_cycle(uid, 9)
    _set_probe_done_today(app, uid)

    from services.daily_task_rotation import pick_daily_set
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    r1 = pick_daily_set(uid)
    assert r1.get('count', 0) > 0, 'банк должен выдать задачи по теме профиля'
    assert not r1.get('stale_context')
    with app.app_context():
        s = DailyTaskSet.query.filter_by(user_id=uid).first()
        assert s is not None
        set_id = s.id
        n_items = DailyTaskItem.query.filter_by(daily_set_id=s.id).count()
        assert s.olympiad_context and json.loads(s.olympiad_context)['olympiad_slug'] == 'vsosh'

    # смена олимпиады: сет сохраняется, отдаётся с пометкой прежнего контекста
    _mk_plan(app, uid, oid_lomonosov)
    from curator.monthly_cycle import apply_olympiad_cycle
    apply_olympiad_cycle(uid)
    _set_probe_done_today(app, uid)
    r2 = pick_daily_set(uid)
    assert r2.get('stale_context') is True, 'сет под прежний контекст — честная пометка'
    assert r2.get('count') == r1.get('count')
    with app.app_context():
        s2 = DailyTaskSet.query.filter_by(user_id=uid).first()
        assert s2.id == set_id, 'сет не должен удаляться/пересоздаваться'
        assert DailyTaskItem.query.filter_by(daily_set_id=s2.id).count() == n_items
        # контекст сета НЕ перезаписывается — он остаётся фактом истории
        assert json.loads(s2.olympiad_context)['olympiad_slug'] == 'vsosh'

    # daily_context честно помечает прежнюю выдачу
    from services.daily_olympiad import daily_context
    ctx = daily_context(uid)
    assert ctx['status'] == 'stale_set'
    assert ctx['former_name'] == 'Всероссийская олимпиада школьников'


def test_http_regression_switch_shows_stale_marking(app, client):
    """HTTP-регрессия (ревью раунда 4, п.1): существующий сегодняшний сет →
    смена олимпиады → GET /daily_tasks/ показывает ПРЕЖНИЙ набор с честной
    пометкой, а не бейдж новой олимпиады."""
    # uid=1 — пилотный аккаунт (victor): для пилотов /daily_tasks уходит
    # в «день метода» и задачи не выдаются. Юзер-заглушка -> наш id=2, не пилот.
    _mk_user(app, 'odo15filler@test.local', grade=9)
    uid = _mk_user(app, 'odo16@test.local', grade=9)
    oid_vsosh = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    oid_lomonosov = _mk_olympiad(app, 'lomonosov', 'Олимпиада «Ломоносов»')
    _mk_plan(app, uid, oid_vsosh)

    from curator.monthly_cycle import build_or_get_cycle
    build_or_get_cycle(uid, 9)
    _set_probe_done_today(app, uid)

    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)

    # первый заход — БЕЗ предварительного сета: сет создаётся самим
    # маршрутом через pick_daily_set (или банком с штампом контекста в
    # bank_issues), контекст олимпиады фиксируется при выдаче.
    rv = client.get('/daily_tasks/')
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert 'подготовка к олимпиаде «Всероссийская олимпиада школьников»' in body
    assert '⚠️' not in body, 'первая выдача — без пометки stale'

    # ТЕСТ-ИНФРА: фикстура держит постоянный app-контекст, поэтому teardown
    # запроса не выполняется (Flask гонит teardown только у ВНЕШНЕГО контекста)
    # и сессия маршрута остаётся с открытой read-транзакцией — она блокирует
    # запись в file-based SQLite. В проде запрос всегда внешний контекст и
    # teardown срабатывает. Явно снимаем сессию после GET.
    from models import db as _db_mod
    _db_mod.session.remove()
    # смена олимпиады
    # сначала зафиксируем прежний сет (ревью раунда 5: неизменность)
    from daily_tasks.models import DailyTaskSet as _DTS
    from daily_tasks.models import DailyTaskItem as _DTI
    _today = datetime.now(timezone.utc).date()
    _set_before = _DTS.query.filter_by(user_id=uid, target_date=_today).first()
    assert _set_before is not None, 'сет должен был быть создан первым GET'
    _ctx_before = _set_before.olympiad_context
    _items_before = sorted(
        r[0] for r in _DTI.query.with_entities(_DTI.id)
        .filter_by(daily_set_id=_set_before.id).all()
    )
    assert _items_before, 'в выданном сете должны быть задачи'
    _mk_plan(app, uid, oid_lomonosov)

    rv2 = client.get('/daily_tasks/')
    assert rv2.status_code == 200
    body2 = rv2.get_data(as_text=True)
    # прежний набор остаётся (не «Задач пока нет»), с честной пометкой
    assert 'выдан под олимпиаду «Всероссийская олимпиада школьников»' in body2, (
        'прежняя выдача должна быть честно помечена, а не подписана новой олимпиадой'
    )
    assert 'подготовка к олимпиаде «Олимпиада «Ломоносов»»' not in body2, (
        'новый профиль не подписывает прежний сет'
    )
    # сет не пересоздаётся: тот же ID, те же задачи, прежний контекст
    _set_after = _DTS.query.filter_by(user_id=uid, target_date=_today).first()
    assert _set_after.id == _set_before.id, 'сет не должен пересоздаваться при смене олимпиады'
    assert _set_after.olympiad_context == _ctx_before, 'контекст выданного сета не перезаписывается'
    _items_after = sorted(
        r[0] for r in _DTI.query.with_entities(_DTI.id)
        .filter_by(daily_set_id=_set_after.id).all()
    )
    assert _items_after == _items_before, 'задачи сета не меняются'


def test_grade_switch_marks_stale_set(app, client):
    """Ревью раунда 5: смена КЛАССА при той же олимпиаде
    (ВсОШ-9 → ВсОШ-11) — прежний сет не получает applied:
    сравнивается полный ключ контекста (слаг+класс+версия), а не только слаг."""
    from models import db
    from models import PrepPlan
    from daily_tasks.models import DailyTaskSet
    from services.daily_olympiad import daily_context, context_key
    from services.daily_task_rotation import _context_json
    import json as _json
    uid = _mk_user(app, 'odo18@test.local', grade=9)
    oid_vsosh = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid_vsosh)
    from curator.monthly_cycle import build_or_get_cycle
    build_or_get_cycle(uid, 9)
    _set_probe_done_today(app, uid)

    with app.app_context():
        # сет «выдан» сегодня под ВсОШ-9: контекст зафиксирован
        set_row = DailyTaskSet(
            user_id=uid, target_date=datetime.now(timezone.utc).date(),
            status='ready', triggered_by='formyla_bank',
            generated_at=datetime.now(timezone.utc), class_level=9,
            olympiad_context=_context_json(uid),
        )
        db.session.add(set_row)
        db.session.commit()
        assert daily_context(uid)['status'] == 'applied', (
            'сет под текущий контекст (ВсОШ-9) — applied'
        )

        # смена класса: тот же слаг, target_grade=11
        plan = PrepPlan.query.filter_by(user_id=uid).first()
        plan.target_grade = 11
        db.session.commit()

        ctx = daily_context(uid)
        assert ctx['status'] == 'stale_set', (
            'смена класса должна честно помечаться stale_set, а не applied'
        )
        assert ctx['former_name'] == 'Всероссийская олимпиада школьников'
        # сет не тронут: контекст прежний (класс 9)
        db.session.refresh(set_row)
        assert _json.loads(set_row.olympiad_context)['grade'] == 9
        # текущий ключ — уже 11 класс
        assert context_key(uid)['grade'] == 11


def test_lifecycle_transitions(app):
    """Полный жизненный цикл (ревью раунда 4, п.4):
    нет цикла → профиль; профиль → нет олимпиады (общий восстановлен);
    профиль → неподдерживаемая (общий восстановлен)."""
    from curator.monthly_cycle import apply_olympiad_cycle, build_or_get_cycle
    from services.daily_olympiad import daily_context, profile_for
    uid = _mk_user(app, 'odo17@test.local', grade=9)
    oid_vsosh = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    oid_unknown = _mk_olympiad(app, 'unknown-slug', 'Неизвестная олимпиада')

    # 1) нет цикла → штатное создание с профилем
    _mk_plan(app, uid, oid_vsosh)
    res = apply_olympiad_cycle(uid)
    assert res['reason'] == 'created'
    mc = _get_mc(app, uid)
    assert mc.get('themes') and mc.get('started_at') and mc.get('day_index') == 1
    assert set(mc['themes']) <= set(profile_for('vsosh', 9)['themes'])
    assert daily_context(uid)['status'] == 'applied'

    # 2) профильный цикл → олимпиада удалена: общий цикл восстановлен
    from models import db
    from models import PrepPlan
    with app.app_context():
        PrepPlan.query.filter_by(user_id=uid).delete()
        db.session.commit()
    res2 = apply_olympiad_cycle(uid)
    assert res2['applied'] is False
    assert res2.get('restored_generic') is True
    mc2 = _get_mc(app, uid)
    assert not mc2.get('olympiad_slug'), 'метки профиля должны быть сняты'
    prof_themes = set(profile_for('vsosh', 9)['themes'])
    # общий цикл — не обязан быть подмножеством профиля
    from services.theme_registry import themes_of_grade
    assert set(mc2['themes']) <= set(themes_of_grade(9))

    # 3) общий цикл → неподдерживаемая олимпиада: пометка, цикл не трогается
    _mk_plan(app, uid, oid_unknown)
    res3 = apply_olympiad_cycle(uid)
    assert res3['reason'] == 'no_profile'
    mc3 = _get_mc(app, uid)
    assert mc3['themes'] == mc2['themes']
    assert mc3.get('olympiad_unsupported') is True

    # 4) профильный цикл → неподдерживаемая: общий восстановлен
    _mk_plan(app, uid, oid_vsosh)
    apply_olympiad_cycle(uid)   # снова профильный
    _mk_plan(app, uid, oid_unknown)
    res4 = apply_olympiad_cycle(uid)
    assert res4.get('restored_generic') is True
    mc4 = _get_mc(app, uid)
    assert not mc4.get('olympiad_slug')


def test_effective_grade_target_grade(app):
    """PrepPlan.target_grade (подготовка за другой класс) учитывается."""
    from models import db, PrepPlan
    from services.daily_olympiad import user_cycle_grade
    uid = _mk_user(app, 'odo18@test.local', grade=9)   # куратор: 9
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    plan_id = _mk_plan(app, uid, oid)
    with app.app_context():
        plan = db.session.get(PrepPlan, plan_id)
        plan.target_grade = 11
        db.session.commit()
    assert user_cycle_grade(uid) == 11
    # профиль 11 класса доступен
    from services.daily_olympiad import profile_for
    assert profile_for('vsosh', 11) is not None


# ─── Маршрут ─────────────────────────────────────────────────────────────


def test_route_shows_olympiad_badge(app, client):
    uid = _mk_user(app, 'odo11@test.local', grade=9)
    oid = _mk_olympiad(app, 'vsosh', 'Всероссийская олимпиада школьников')
    _mk_plan(app, uid, oid)

    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)

    rv = client.get('/daily_tasks/')
    assert rv.status_code == 200
    body = rv.get_data(as_text=True)
    assert 'подготовка к олимпиаде' in body, (
        'страница задач дня должна честно помечать выбранную олимпиаду'
    )
