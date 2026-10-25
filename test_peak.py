import os
# -*- coding: utf-8 -*-
"""Тест peak_from_events (чистая логика пика одновременных) и detect_device."""
import sys, types
from datetime import datetime, timedelta

# ── стабы зависимостей services/user_returns.py (не тянем flask/models) ──
class _Dummy:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        # декораторы вида bp.route(...)
        def _wrap(*a, **k):
            def _dec(fn):
                return fn
            return _dec
        return _wrap


def _mk(name, attrs):
    m = types.ModuleType(name)
    for attr in attrs:
        setattr(m, attr, _Dummy)
    return m


sys.modules['flask'] = _mk('flask', ('Blueprint', 'request', 'jsonify',
                                     'render_template_string', 'abort'))
sys.modules['flask_login'] = _mk('flask_login', ('current_user', 'login_required'))

sqla = _mk('sqlalchemy', ('text', 'inspect'))
sqla_t = _mk('sqlalchemy.types', ('DateTime', 'TIMESTAMP', 'Date'))
sqla.types = sqla_t
sys.modules['sqlalchemy'] = sqla
sys.modules['sqlalchemy.types'] = sqla_t

models_m = types.ModuleType('models')


class _DB:
    session = None


models_m.db = _DB()
sys.modules['models'] = models_m

import importlib.util
spec = importlib.util.spec_from_file_location(
    'user_returns', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services', 'user_returns.py'))
ur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ur)
print('module loaded OK')

NOW = datetime(2026, 10, 25, 15, 0, 0)

def ev(*pairs):
    """{uid: [dt,...]}"""
    return {uid: [NOW + timedelta(minutes=m) if m >= 0 else
                  datetime(2026, 10, 25, 0, 0) + timedelta(minutes=m)
                  for m in mins] for uid, mins in pairs}

# ── Тест 1: двое онлайн одновременно ──
# A: действие 12:00 → интервал [12:00, 13:00]; B: действие 12:30 → [12:30, 13:30]
# пик = 2 в 12:30, online_now (в 15:00) = 0
d = ur.peak_from_events({
    1: [datetime(2026, 10, 25, 12, 0)],
    2: [datetime(2026, 10, 25, 12, 30)],
}, gap_min=60, now=NOW)
assert d['peak_ever'] == 2, d
assert d['peak_today'] == 2, d
assert d['peak_ever_at'] == '25.10.2026 12:30', d
assert d['online_now'] == 0, d
assert d['peak_today'] >= d['online_now']
print('T1 two concurrent OK:', d['peak_ever'], d['peak_ever_at'])

# ── Тест 2: инвариант peak_today >= online_now; один активен сейчас ──
d = ur.peak_from_events({
    1: [datetime(2026, 10, 25, 14, 30)],   # 30 мин назад → онлайн
    2: [datetime(2026, 10, 25, 12, 0)],    # [12:00, 13:00] — не пересекается с 1
}, gap_min=60, now=NOW)
assert d['online_now'] == 1, d
assert d['peak_today'] == 1, d
assert d['peak_today'] >= d['online_now']
print('T2 online_now OK:', d['online_now'], 'peak_today:', d['peak_today'])

# ── Тест 3: вчерашний визит через полночь ──
# действие в 23:50 вчера → интервал до 00:50 сегодня: попадает в base сегодняшнего дня
d = ur.peak_from_events({
    1: [datetime(2026, 10, 24, 23, 50)],
    2: [datetime(2026, 10, 25, 0, 10)],
}, gap_min=60, now=NOW)
assert d['peak_today'] == 2, d             # в 00:10 оба «на сайте»
assert d['peak_yesterday'] == 1, d
print('T3 midnight OK: today', d['peak_today'], 'yesterday', d['peak_yesterday'])

# ── Тест 4: метки из будущего игнорируются ──
d = ur.peak_from_events({
    1: [datetime(2026, 10, 25, 16, 30)],   # из будущего
    2: [datetime(2026, 10, 25, 12, 0)],
}, gap_min=60, now=NOW)
assert d['peak_ever'] == 1, d
assert d['online_now'] == 0, d
print('T4 future timestamps OK')

# ── Тест 5: один визит из двух действий (пауза 30 мин) = интервал [10:00, 11:00+60] ──
d = ur.peak_from_events({
    1: [datetime(2026, 10, 25, 10, 0), datetime(2026, 10, 25, 10, 30)],
}, gap_min=60, now=NOW)
assert d['visits'] == 1, d
assert d['peak_ever'] == 1, d
assert d['peak_ever_at'] == '25.10.2026 10:00', d
print('T5 single visit interval OK')

# ── Тест 6: пауза > 60 мин = два визита, не растягивает интервал ──
d = ur.peak_from_events({
    1: [datetime(2026, 10, 25, 10, 0), datetime(2026, 10, 25, 12, 0)],
}, gap_min=60, now=NOW)
assert d['visits'] == 2, d
print('T6 two visits OK')

# ── Тест 7: peak_yesterday — трое вчера в 20:00 ──
d = ur.peak_from_events({
    1: [datetime(2026, 10, 24, 20, 0)],
    2: [datetime(2026, 10, 24, 20, 5)],
    3: [datetime(2026, 10, 24, 20, 30)],
}, gap_min=60, now=NOW)
assert d['peak_yesterday'] == 3, d
assert d['peak_today'] == 0, d
assert d['peak_ever'] == 3, d
print('T7 yesterday OK')

# ── Тест 8: detect_device ──
import importlib.util as _iu
spec2 = _iu.spec_from_file_location(
    'admin_support', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'routes', 'admin_support.py'))
try:
    spec2.loader.exec_module  # импорт требует flask — тестируем функцию напрямую
    raise SystemExit('unexpected')
except SystemExit:
    pass
# скопируем функцию через исходник
import re as _re
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'routes', 'admin_support.py'), encoding='utf-8').read()
fn = _re.search(r"def detect_device.*?\n    return 'pc'\n", src, _re.S).group(0)
ns = {}
exec(fn, ns)
detect_device = ns['detect_device']
assert detect_device('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15') == 'mobile'
assert detect_device('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36') == 'mobile'
assert detect_device('Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)') == 'mobile'
assert detect_device('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0') == 'pc'
assert detect_device('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)') == 'pc'
assert detect_device('') is None
assert detect_device(None) is None
assert detect_device('Googlebot/2.1 (+http://www.google.com/bot.html)') is None
print('T8 detect_device OK')

print('ALL TESTS PASSED')
