# -*- coding: utf-8 -*-
"""
routes/__init__.py — ADMIN_BASE_V1 (06.10.2026) + PWA_INSTALL_V1 (11.10.2026)
+ SITE_NOTICE_V1 (11.10.2026).

Автоматическая регистрация blueprint «База» (routes/admin_base.py),
blueprint PWA (routes/pwa.py) и blueprint одноразовых уведомлений
(routes/site_notices.py) без правки app.py. Файл превращает `routes/`
в обычный пакет (раньше был namespace package); все существующие импорты
`from routes.xxx import ...` работают как прежде.

Как это работает: при первом `app.register_blueprint(...)` любого другого
blueprint мы один раз дорегистрируем `admin_base_bp`, `pwa_bp` и `site_notices_bp`
в это же приложение и вешаем after_request-хуки.

Отключить: ADMIN_BASE_AUTOREG=0, PWA_AUTOREG=0 и/или SITE_NOTICES_AUTOREG=0.
Ручная регистрация (эквивалент):
    from routes.admin_base import admin_base_bp
    app.register_blueprint(admin_base_bp)
    from routes.pwa import install_pwa
    install_pwa(app)
    from routes.site_notices import site_notices_bp
    app.register_blueprint(site_notices_bp)
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_NAV_SNIPPET = (
    '<div id="admin-base-nav" style="position:fixed;right:18px;bottom:18px;z-index:30000;">'
    '<a href="/admin/base" style="display:inline-block;padding:10px 16px;border-radius:12px;'
    'background:#f4b942;color:#0b1020;font-weight:800;text-decoration:none;'
    'box-shadow:0 6px 24px rgba(0,0,0,.35);font-family:inherit;">📦 База</a></div>'
)
_NAV_PATHS = ("/admin/users", "/admin/stats", "/admin/daily", "/admin/sections", "/admin/support")


def _install_pwa(app) -> None:
    """PWA_INSTALL_V1: /sw.js, /site.webmanifest, /offline + инжектор тегов."""
    if os.environ.get("PWA_AUTOREG", "1") == "0":
        return
    if getattr(app, "_pwa_installed", False):
        return
    try:
        from routes.pwa import install_pwa
        install_pwa(app)
    except Exception as e:  # noqa: BLE001
        logger.exception("[pwa] auto-register failed: %r", e)


def _install_site_notices(app) -> None:
    """SITE_NOTICE_V1: одноразовые уведомления (/api/site-notice/*)."""
    if os.environ.get("SITE_NOTICES_AUTOREG", "1") == "0":
        return
    if getattr(app, "_site_notices_installed", False):
        return
    app._site_notices_installed = True
    try:
        from routes.site_notices import site_notices_bp
        if "site_notices" not in app.blueprints:
            _ORIG_REGISTER(app, site_notices_bp)
        logger.info("[BP] site_notices_bp registered (/api/site-notice/pending, /api/site-notice/seen)")
        print("[BP] site_notices_bp registered (/api/site-notice/pending, /api/site-notice/seen)")
    except Exception as e:  # noqa: BLE001
        logger.exception("[site_notices] auto-register failed: %r", e)


def _install(app) -> None:
    _install_pwa(app)
    _install_site_notices(app)

    if getattr(app, "_admin_base_installed", False):
        return
    app._admin_base_installed = True
    try:
        from routes.admin_base import admin_base_bp
        if "admin_base" not in app.blueprints:
            _ORIG_REGISTER(app, admin_base_bp)
        logger.info("[BP] admin_base_bp registered (/admin/base, /admin/base/user/<id>)")
        print("[BP] admin_base_bp registered (/admin/base, /admin/base/user/<id>)")
    except Exception as e:  # noqa: BLE001
        logger.exception("[admin_base] auto-register failed: %r", e)
        return

    @app.after_request
    def _admin_base_nav(resp):
        try:
            from flask import request
            p = request.path or ""
            if not p.startswith(_NAV_PATHS) or p.startswith("/admin/base"):
                return resp
            if resp.direct_passthrough or resp.status_code != 200:
                return resp
            ct = (resp.content_type or "").lower()
            if "text/html" not in ct:
                return resp
            body = resp.get_data(as_text=True)
            if "admin-base-nav" in body or "</body>" not in body:
                return resp
            resp.set_data(body.replace("</body>", _NAV_SNIPPET + "</body>", 1))
        except Exception:  # noqa: BLE001
            pass
        return resp


try:
    import flask as _flask

    _ORIG_REGISTER = _flask.Flask.register_blueprint

    if os.environ.get("ADMIN_BASE_AUTOREG", "1") != "0" and \
            not getattr(_flask.Flask.register_blueprint, "_admin_base_patched", False):

        def _patched_register_blueprint(self, blueprint, **options):
            result = _ORIG_REGISTER(self, blueprint, **options)
            if getattr(blueprint, "name", "") not in ("admin_base", "pwa", "site_notices"):
                _install(self)
            return result

        _patched_register_blueprint._admin_base_patched = True  # type: ignore[attr-defined]
        _flask.Flask.register_blueprint = _patched_register_blueprint  # type: ignore[assignment]
except Exception as _e:  # noqa: BLE001
    logger.warning("[admin_base] autoreg hook not installed: %r", _e)
