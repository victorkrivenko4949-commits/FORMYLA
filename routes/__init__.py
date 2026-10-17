# -*- coding: utf-8 -*-
"""
routes/__init__.py — ADMIN_BASE_V1 (06.10.2026) + PWA_INSTALL_V1 (11.10.2026)
+ SITE_NOTICE_V1 (11.10.2026) + OLYMP_CATALOG_V3 (14.10.2026) + CHAT_DOCS_V1 (15.10.2026)
+ ADMIN_NOTICES_V1 (18.10.2026).

Автоматическая регистрация blueprint «База» (routes/admin_base.py),
blueprint PWA (routes/pwa.py), blueprint одноразовых уведомлений
(routes/site_notices.py), blueprint каталога олимпиадных задач
(routes/olymp_catalog.py, /olymp-catalog), blueprint вложений чата
(routes/chat_attachments.py — документы в чате, фикс фото, компактное меню)
и blueprint админ-уведомлений (routes/admin_notices.py — кнопка «🔔 Уведомления»
в шапке у админа + модалка для пользователей) без правки app.py. Файл превращает `routes/`
в обычный пакет (раньше был namespace package); все существующие импорты
`from routes.xxx import ...` работают как прежде.

Как это работает: при первом `app.register_blueprint(...)` любого другого
blueprint мы один раз дорегистрируем `admin_base_bp`, `pwa_bp`, `site_notices_bp`,
`olymp_catalog_bp`, `chat_attachments_bp` и `admin_notices_bp` в это же приложение
и вешаем after_request-хуки.

Отключить: ADMIN_BASE_AUTOREG=0, PWA_AUTOREG=0, SITE_NOTICES_AUTOREG=0,
OLYMP_CATALOG_AUTOREG=0, CHAT_ATTACHMENTS_AUTOREG=0 и/или ADMIN_NOTICES_AUTOREG=0.
Ручная регистрация (эквивалент):
    from routes.admin_base import admin_base_bp
    app.register_blueprint(admin_base_bp)
    from routes.pwa import install_pwa
    install_pwa(app)
    from routes.site_notices import site_notices_bp
    app.register_blueprint(site_notices_bp)
    from routes.olymp_catalog import install_olymp_catalog
    install_olymp_catalog(app)
    from routes.chat_attachments import install_chat_attachments
    install_chat_attachments(app)
    from routes.admin_notices import install_admin_notices
    install_admin_notices(app)
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


def _install_olymp_catalog(app) -> None:
    """OLYMP_CATALOG_V3: закрытый каталог олимпиадных задач (/olymp-catalog) + пункт меню."""
    if os.environ.get("OLYMP_CATALOG_AUTOREG", "1") == "0":
        return
    if getattr(app, "_olymp_catalog_installed", False):
        return
    try:
        from routes.olymp_catalog import install_olymp_catalog
        install_olymp_catalog(app)
    except Exception as e:  # noqa: BLE001
        logger.exception("[olymp_catalog] auto-register failed: %r", e)


def _install_chat_attachments(app) -> None:
    """CHAT_DOCS_V1: документы в чате, фикс отправки фото, компактное меню сообщения."""
    if os.environ.get("CHAT_ATTACHMENTS_AUTOREG", "1") == "0":
        return
    if getattr(app, "_chat_attachments_installed", False):
        return
    try:
        from routes.chat_attachments import install_chat_attachments
        install_chat_attachments(app)
    except Exception as e:  # noqa: BLE001
        logger.exception("[chat_attachments] auto-register failed: %r", e)


def _install_admin_notices(app) -> None:
    """ADMIN_NOTICES_V1: раздел «🔔 Уведомления» (/admin/notices) + модалка у пользователей."""
    if os.environ.get("ADMIN_NOTICES_AUTOREG", "1") == "0":
        return
    if app.extensions.get("admin_notices_installed"):
        return
    try:
        from routes.admin_notices import install_admin_notices
        install_admin_notices(app, register=_ORIG_REGISTER)
    except Exception as e:  # noqa: BLE001
        logger.exception("[admin_notices] auto-register failed: %r", e)


def _install(app) -> None:
    _install_pwa(app)
    _install_site_notices(app)
    _install_olymp_catalog(app)
    _install_chat_attachments(app)
    _install_admin_notices(app)
    if os.environ.get("SURVEYS_AUTOREG", "1") != "0":
        from routes.surveys import install_surveys
        install_surveys(app, register=_ORIG_REGISTER)

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
            if getattr(blueprint, "name", "") not in ("admin_base", "pwa", "site_notices", "olymp_catalog", "chat_attachments", "surveys", "admin_notices"):
                _install(self)
            return result

        _patched_register_blueprint._admin_base_patched = True  # type: ignore[attr-defined]
        _flask.Flask.register_blueprint = _patched_register_blueprint  # type: ignore[assignment]
except Exception as _e:  # noqa: BLE001
    logger.warning("[admin_base] autoreg hook not installed: %r", _e)
