# -*- coding: utf-8 -*-
"""
routes/stats_nav.py — STATS_PAGE_V1 + THEME_EVAL_V1 (18.10.2026).

1) Переименование пункта меню «🎓 Куратор подготовки» → «📊 Статистика»
   (десктоп-шапка, мобильный drawer, нижняя панель) без правки base.html:
   after_request-хук подменяет текст в готовом HTML.
2) before_request на /prep/coach: пересчёт итогов по темам
   (services/theme_level_eval.evaluate_user) — после каждых 10 решённых задач
   дня тема получает уровень 1..4, который попадает в радары.
3) GET /api/stats/theme-eval — итоги по темам для страницы «Статистика».

Отключить: STATS_NAV_AUTOREG=0.
"""
from __future__ import annotations

import re

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

stats_page_bp = Blueprint('stats_page', __name__)

_DESKTOP = ('🎓 Куратор подготовки', '📊 Статистика')
_DRAWER_RE = re.compile(r'(<span class="drawer-link-icon">)🎓(</span>\s*)Куратор подготовки')
_BOTTOM_RE = re.compile(r'(<span class="bottom-nav-icon">)🎓(</span>\s*<span class="bottom-nav-label">)Куратор(</span>)')

_SECTION_RU = {
    'algebra': 'Алгебра', 'geometry': 'Геометрия', 'combinatorics': 'Комбинаторика',
    'logic': 'Логика', 'number_theory': 'Теория чисел',
}


def rename_nav(body: str) -> str:
    if 'Куратор' not in body:
        return body
    body = body.replace(_DESKTOP[0], _DESKTOP[1])
    body = _DRAWER_RE.sub(r'\g<1>📊\g<2>Статистика', body)
    body = _BOTTOM_RE.sub(r'\g<1>📊\g<2>Статистика\g<3>', body)
    return body


def _real_user() -> bool:
    return bool(current_user.is_authenticated and not getattr(current_user, 'is_guest', False))


@stats_page_bp.route('/api/stats/theme-eval')
@login_required
def api_theme_eval():
    if not _real_user():
        return jsonify({'themes': []})
    from services.theme_level_eval import evaluate_user, BLOCK
    data = evaluate_user(current_user.id)
    themes = []
    for t in data['themes'].values():
        themes.append({
            'title': t['title'],
            'theme_id': t['theme_id'],
            'section': t['section'],
            'section_name': _SECTION_RU.get(t['section'] or '', t['section'] or ''),
            'answered': t['answered'],
            'correct_total': t['correct_total'],
            'level': t['level'],
            'last10_level': t['last10_level'],
            'last10_correct': t['last10_correct'],
            'to_next': t['to_next'],
        })
    themes.sort(key=lambda x: (x['level'] is None, -(x['answered'])))
    resp = jsonify({'block': BLOCK, 'answered_total': data['answered_total'], 'themes': themes})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def install_stats_nav(app, register=None) -> None:
    if app.extensions.get('stats_nav_installed'):
        return
    app.extensions['stats_nav_installed'] = True

    if 'stats_page' not in app.blueprints:
        if register is None:
            app.register_blueprint(stats_page_bp)
        else:
            register(app, stats_page_bp)

    @app.before_request
    def _theme_eval_refresh():
        try:
            p = (request.path or '').rstrip('/')
            if p != '/prep/coach' or request.method != 'GET':
                return None
            if not _real_user():
                return None
            from services.theme_level_eval import evaluate_user
            evaluate_user(current_user.id)
        except Exception:  # noqa: BLE001
            pass
        return None

    @app.after_request
    def _stats_nav(response):
        try:
            if (response.status_code != 200 or response.direct_passthrough
                    or response.mimetype != 'text/html'):
                return response
            body = response.get_data(as_text=True)
            if 'Куратор' not in body:
                return response
            new_body = rename_nav(body)
            if new_body != body:
                response.set_data(new_body)
        except Exception:  # noqa: BLE001
            pass
        return response
