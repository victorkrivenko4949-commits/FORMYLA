# -*- coding: utf-8 -*-
"""
routes/stats_nav.py — STATS_PAGE_V1 (18.10.2026).

Переименование пункта меню «🎓 Куратор подготовки» → «📊 Статистика»
(десктоп-шапка, мобильный drawer, нижняя панель) без правки base.html:
after_request-хук подменяет текст в готовом HTML. Сама страница /prep/coach
теперь показывает только статистику (templates/prep/coach.html).

Отключить: STATS_NAV_AUTOREG=0.
"""
from __future__ import annotations

import re

_DESKTOP = ('🎓 Куратор подготовки', '📊 Статистика')
_DRAWER_RE = re.compile(r'(<span class="drawer-link-icon">)🎓(</span>\s*)Куратор подготовки')
_BOTTOM_RE = re.compile(r'(<span class="bottom-nav-icon">)🎓(</span>\s*<span class="bottom-nav-label">)Куратор(</span>)')


def rename_nav(body: str) -> str:
    if 'Куратор' not in body:
        return body
    body = body.replace(_DESKTOP[0], _DESKTOP[1])
    body = _DRAWER_RE.sub(r'\g<1>📊\g<2>Статистика', body)
    body = _BOTTOM_RE.sub(r'\g<1>📊\g<2>Статистика\g<3>', body)
    return body


def install_stats_nav(app) -> None:
    if app.extensions.get('stats_nav_installed'):
        return
    app.extensions['stats_nav_installed'] = True

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
