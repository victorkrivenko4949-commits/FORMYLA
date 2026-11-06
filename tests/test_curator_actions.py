# -*- coding: utf-8 -*-
"""tests/test_curator_actions.py — куратор знает продукт и умеет действовать.

* справка FORMYLA (data/curator_guide.md) уходит в промпт куратора;
* частотные профили олимпиад: популярные темы первыми, затем остальные,
  только классы, где олимпиада реально есть;
* действия куратора: поднять уровень, поменять дни, сменить олимпиаду;
  неудача → подсказка про иконку поддержки.
Без LLM: _call_deepseek подменяется.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from models import db, User, Subscription, OlympiadPrep, PrepPlan
from models_curator import CuratorState
import services.curator_chat as curator_chat
from services import curator_actions as ca


@pytest.fixture(autouse=True)
def _admins(monkeypatch):
    """Админ в тестах — email на adm_ (пока функции только для админов)."""
    monkeypatch.setattr(User, 'is_admin', property(
        lambda self: (self.email or '').startswith('adm_')))


def _user(email, grade=11, plan='premium_intense'):
    u = User(email=email, nickname=email.split('@')[0])
    db.session.add(u)
    db.session.flush()
    cs = CuratorState(user_id=u.id)
    cs.grade = grade
    cs.prep_state = json.dumps({'intake': {'completed': True, 'grade': grade}})
    db.session.add(cs)
    if plan:
        now = datetime.utcnow()
        db.session.add(Subscription(user_id=u.id, plan=plan, status='active',
                                    is_beta_access=True, started_at=now,
                                    expires_at=now + timedelta(days=30)))
    db.session.commit()
    return u.id


def _olymp(slug, name):
    o = OlympiadPrep.query.filter_by(slug=slug).first()
    if not o:
        o = OlympiadPrep(slug=slug, name=name, short_name=name[:40],
                         grades=json.dumps(list(range(5, 12))))
        db.session.add(o)
        db.session.commit()
    return o


# ─── Справка в промпте ───────────────────────────────────────────────────

def test_guide_in_system_prompt(app):
    msgs = curator_chat._system_messages({'user_id': 1, 'admin_features': True})
    joined = '\n'.join(m['content'] for m in msgs)
    assert 'Справка FORMYLA' in joined
    assert '500 ₽' in joined and '800 ₽' in joined      # тарифы из гайда
    assert 'иконку поддержки' in joined                  # куда отправлять
    assert 'set_days' in joined and 'raise_level' in joined


# ─── Частотные профили ───────────────────────────────────────────────────

def test_all_eleven_olympiads_have_profiles():
    from services.daily_olympiad import _freq_data
    olymps = _freq_data()['olympiads']
    expected = {'euler', 'formula-unity', 'kurchatov', 'lomonosov', 'matprazdnik',
                'mmo', 'phystech', 'rosatom', 'spbgu', 'vsosh', 'vysshaya-proba'}
    assert expected <= set(olymps)


def test_rosatom_popular_first_then_rest(app):
    from services.daily_olympiad import profile_for, topic_stats
    prof = profile_for('rosatom', 11, freq=True)
    stats = topic_stats('rosatom', 11)
    popular = [t['id'] for t in stats['themes']]
    assert prof['source'] == 'catalog_frequency'
    assert prof['themes'][:len(popular)] == popular           # сначала частые
    counts = [t['count'] for t in stats['themes']]
    assert counts == sorted(counts, reverse=True)
    assert len(prof['themes']) > len(popular) or len(popular) >= 18  # потом остальные
    assert len(prof['themes']) == len(set(prof['themes']))
    assert prof['pinned'] and prof['pinned'][0] == popular[0]


def test_olympiad_only_in_its_grades(app):
    from services.daily_olympiad import profile_for
    assert profile_for('euler', 8, freq=True) is not None
    assert profile_for('euler', 9, freq=True) is None        # «Эйлер» — только 8 класс
    assert profile_for('rosatom', 5, freq=True) is None      # Росатома для 5 класса нет
    assert profile_for('fiztekh', 10, freq=True) is not None  # slug плана → каталог


def test_freq_profiles_use_registry_and_bank():
    from collections import Counter
    from pathlib import Path
    from services.daily_olympiad import profile_for, _freq_data
    from services.theme_registry import themes_of_grade, theme_title
    bank = Counter()
    root = Path(__file__).resolve().parents[1]
    with open(root / 'FORMYLA_BANK.jsonl', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                bank[(r.get('grade'), r.get('topic'))] += 1
    problems = []
    for slug, grades in _freq_data()['olympiads'].items():
        for g in grades:
            prof = profile_for(slug, int(g), freq=True)
            if not prof:
                continue
            valid = set(themes_of_grade(int(g)))
            for t in prof['themes']:
                if t not in valid or not bank.get((int(g), theme_title(t))):
                    problems.append(f'{slug} {g}: {t}')
    assert not problems, problems


def test_pinned_theme_every_month(app):
    from curator.monthly_cycle import build_or_get_cycle, get_cycle_info, \
        _get_monthly_cycle, _save_monthly_cycle
    from services.daily_olympiad import profile_for
    from datetime import timezone
    uid = _user('adm_pin@test.ru', grade=11, plan=None)
    o = _olymp('rosatom', 'Олимпиада «Росатом»')
    db.session.add(PrepPlan(user_id=uid, olympiad_id=o.id, status='active',
                            start_date=datetime.utcnow().date(),
                            target_date=datetime.utcnow().date() + timedelta(days=90)))
    db.session.commit()
    pinned = profile_for('rosatom', 11, freq=True)['pinned']
    months = [list(build_or_get_cycle(uid, 11)['themes'])]
    for _ in range(3):
        cs = CuratorState.query.filter_by(user_id=uid).first()
        raw = _get_monthly_cycle(cs)
        raw['started_at'] = (datetime.now(timezone.utc) - timedelta(days=32)).isoformat()
        raw['finished_at'] = datetime.now(timezone.utc).isoformat()
        _save_monthly_cycle(cs, raw)
        db.session.commit()
        months.append(list(get_cycle_info(uid)['themes']))
    for m in months:
        assert pinned[0] in m, 'самая частая тема олимпиады должна быть в каждом месяце'


# ─── Действия ────────────────────────────────────────────────────────────

def test_extract_actions_strips_marker():
    text = 'Сделаю.\n[[ACTION {"type": "raise_level"}]]'
    clean, actions = ca.extract_actions(text)
    assert clean == 'Сделаю.'
    assert actions == [{'type': 'raise_level'}]
    assert ca.extract_actions('[[ACTION {битый json}]] ok')[1] == []


def test_raise_level(app):
    from services.level_engine import get_state
    uid = _user('adm_lvl@test.ru')
    cs = CuratorState.query.filter_by(user_id=uid).first()
    cs.level_mu, cs.level_sigma = 2.0, 0.5
    db.session.commit()
    text, res = ca.apply_reply(uid, 'Поднимаю.\n[[ACTION {"type": "raise_level"}]]')
    assert res[0]['ok'] is True
    assert get_state(uid)['level'] == 3
    assert 'ACTION' not in text and 'с 2 до 3' in text
    cs.level_mu = 4.0
    db.session.commit()
    assert ca.change_level(uid, +1)['ok'] is False      # выше 4 некуда


def test_set_days(app):
    from services.schedule_days import get_user_days
    uid = _user('adm_days@test.ru', plan='premium_calm')
    res = ca.set_days(uid, [1, 3, 5])
    assert res['ok'] is True
    assert get_user_days(uid) == [1, 3, 5]
    bad = ca.set_days(uid, [1, 3])                       # «Спокойный» — ровно 3
    assert bad['ok'] is False and get_user_days(uid) == [1, 3, 5]


def test_set_days_without_plan_points_to_support(app):
    uid = _user('adm_nodays@test.ru', plan=None)
    res = ca.set_days(uid, [0, 1, 2])
    assert res['ok'] is False
    assert 'иконку поддержки' in res['message']


def test_set_olympiad_switches_plan(app):
    from services.daily_olympiad import user_olympiad
    uid = _user('adm_ol@test.ru', grade=11)
    vs = _olymp('vsosh', 'ВсОШ')
    _olymp('rosatom', 'Олимпиада «Росатом»')
    db.session.add(PrepPlan(user_id=uid, olympiad_id=vs.id, status='active',
                            start_date=datetime.utcnow().date(),
                            target_date=datetime.utcnow().date() + timedelta(days=90)))
    db.session.commit()
    res = ca.set_olympiad(uid, 'rosatom')
    assert res['ok'] is True, res
    assert user_olympiad(uid)['slug'] == 'rosatom'
    assert 'Росатом' in res['message']


def test_set_olympiad_wrong_grade(app):
    uid = _user('adm_ol5@test.ru', grade=5)
    _olymp('euler', 'Олимпиада им. Эйлера')
    res = ca.set_olympiad(uid, 'euler')
    assert res['ok'] is False


def test_unknown_action_points_to_support(app):
    uid = _user('adm_unk@test.ru')
    _text, res = ca.apply_reply(uid, 'Ок\n[[ACTION {"type": "refund"}]]')
    assert res[0]['ok'] is False and 'иконку поддержки' in res[0]['message']


def test_generate_reply_runs_action(app, monkeypatch):
    from services.level_engine import get_state
    uid = _user('adm_gen@test.ru')
    cs = CuratorState.query.filter_by(user_id=uid).first()
    cs.level_mu, cs.level_sigma = 1.0, 0.5
    db.session.commit()
    seen = {}

    def fake(msgs, thinking=False, max_tokens=1200):
        seen['msgs'] = msgs
        return 'Давай сложнее.\n[[ACTION {"type": "raise_level"}]]'
    monkeypatch.setattr(curator_chat, '_call_deepseek', fake)
    out = curator_chat.generate_reply(uid, 'подними мне уровень')
    assert out['fallback'] is False
    assert get_state(uid)['level'] == 2
    assert '[[ACTION' not in out['content']
    ctx_block = next(m['content'] for m in seen['msgs']
                     if m['content'].startswith('Данные ученика'))
    assert 'уровень задач дня: 1 из 4' in ctx_block
    assert 'дни занятий' in ctx_block


# ─── Не-админам — всё по-старому ─────────────────────────────────────────

def test_non_admin_gets_old_profiles(app):
    from services.daily_olympiad import profile_for, PROFILE_VERSION
    uid = _user('kid@test.ru', grade=11, plan=None)
    assert profile_for('rosatom', 11, user_id=uid) is None    # как раньше: нет профиля
    prof = profile_for('vsosh', 9, user_id=uid)
    assert prof['source'] == 'editorial' and prof['version'] == PROFILE_VERSION
    adm = _user('adm_x@test.ru', grade=11, plan=None)
    assert profile_for('rosatom', 11, user_id=adm)['source'] == 'catalog_frequency'


def test_non_admin_curator_unchanged(app, monkeypatch):
    from services.level_engine import get_state
    uid = _user('kid2@test.ru')
    cs = CuratorState.query.filter_by(user_id=uid).first()
    cs.level_mu, cs.level_sigma = 1.0, 0.5
    db.session.commit()
    seen = {}

    def fake(msgs, thinking=False, max_tokens=1200):
        seen['msgs'] = msgs
        return 'Ок.\n[[ACTION {"type": "raise_level"}]]'
    monkeypatch.setattr(curator_chat, '_call_deepseek', fake)
    out = curator_chat.generate_reply(uid, 'подними уровень')
    joined = '\n'.join(m['content'] for m in seen['msgs'])
    assert 'Справка FORMYLA' not in joined and 'raise_level' not in joined
    assert get_state(uid)['level'] == 1                       # действие НЕ выполнено
    assert '[[ACTION' not in out['content']
