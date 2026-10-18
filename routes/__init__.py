# -*- coding: utf-8 -*-
"""Autoregistration: preserve main notices, Lavrik redirect and stats navigation;
add FUNNEL_V1 and ADMIN_STATS_V1 without editing app.py.
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
_SELF_BLUEPRINTS = ("admin_base", "pwa", "site_notices", "olymp_catalog", "chat_attachments",
                    "surveys", "admin_notices", "stats_page", "funnel", "admin_stats")


def _install_pwa(app) -> None:
    if os.environ.get("PWA_AUTOREG", "1") == "0" or getattr(app, "_pwa_installed", False):
        return
    try:
        from routes.pwa import install_pwa
        install_pwa(app)
    except Exception as e:
        logger.exception("[pwa] auto-register failed: %r", e)


def _install_site_notices(app) -> None:
    if os.environ.get("SITE_NOTICES_AUTOREG", "1") == "0" or getattr(app, "_site_notices_installed", False):
        return
    app._site_notices_installed = True
    try:
        from routes.site_notices import site_notices_bp
        if "site_notices" not in app.blueprints:
            _ORIG_REGISTER(app, site_notices_bp)
        logger.info("[BP] site_notices_bp registered")
    except Exception as e:
        logger.exception("[site_notices] auto-register failed: %r", e)


def _install_olymp_catalog(app) -> None:
    if os.environ.get("OLYMP_CATALOG_AUTOREG", "1") == "0" or getattr(app, "_olymp_catalog_installed", False):
        return
    try:
        from routes.olymp_catalog import install_olymp_catalog
        install_olymp_catalog(app)
    except Exception as e:
        logger.exception("[olymp_catalog] auto-register failed: %r", e)


def _install_chat_attachments(app) -> None:
    if os.environ.get("CHAT_ATTACHMENTS_AUTOREG", "1") == "0" or getattr(app, "_chat_attachments_installed", False):
        return
    try:
        from routes.chat_attachments import install_chat_attachments
        install_chat_attachments(app)
    except Exception as e:
        logger.exception("[chat_attachments] auto-register failed: %r", e)


def _install_admin_notices(app) -> None:
    if os.environ.get("ADMIN_NOTICES_AUTOREG", "1") == "0" or app.extensions.get("admin_notices_installed"):
        return
    try:
        from routes.admin_notices import install_admin_notices
        install_admin_notices(app, register=_ORIG_REGISTER)
    except Exception as e:
        logger.exception("[admin_notices] auto-register failed: %r", e)


def _install_lavrik_support_redirect(app) -> None:
    if os.environ.get("LAVRIK_SUPPORT_REDIRECT", "1") == "0" or getattr(app, "_lavrik_support_redirect_installed", False):
        return
    app._lavrik_support_redirect_installed = True

    @app.before_request
    def _lavrik_support_redirect():
        try:
            from flask import request, redirect
            from flask_login import current_user
            if (request.path or "").rstrip("/") != "/my/support":
                return None
            if not getattr(current_user, "is_authenticated", False):
                return None
            if (getattr(current_user, "nickname", "") or "").lower() != "lavrik":
                return None
            return redirect("/admin/support", code=302)
        except Exception:
            return None


def _install_stats_nav(app) -> None:
    if os.environ.get("STATS_NAV_AUTOREG", "1") == "0" or app.extensions.get("stats_nav_installed"):
        return
    try:
        from routes.stats_nav import install_stats_nav
        install_stats_nav(app, register=_ORIG_REGISTER)
    except Exception as e:
        logger.exception("[stats_nav] auto-register failed: %r", e)


def _install_funnel(app) -> None:
    if os.environ.get("FUNNEL_ENABLED", "1") == "0" or app.extensions.get("funnel_installed"):
        return
    try:
        from services.funnel import install as install_funnel
        install_funnel(app)
    except Exception as e:
        logger.exception("[funnel] auto-register failed: %r", e)


def _install_admin_stats(app) -> None:
    if os.environ.get("ADMIN_STATS_ENABLED", "1") == "0" or app.extensions.get("admin_stats_installed"):
        return
    try:
        from routes.admin_stats import install as install_admin_stats
        install_admin_stats(app)
    except Exception as e:
        logger.exception("[admin_stats] auto-register failed: %r", e)


def _install(app) -> None:
    _install_pwa(app)
    _install_site_notices(app)
    _install_olymp_catalog(app)
    _install_chat_attachments(app)
    _install_admin_notices(app)
    _install_lavrik_support_redirect(app)
    _install_stats_nav(app)
    if os.environ.get("SURVEYS_AUTOREG", "1") != "0":
        from routes.surveys import install_surveys
        install_surveys(app, register=_ORIG_REGISTER)
    _install_funnel(app)
    _install_admin_stats(app)

    if getattr(app, "_admin_base_installed", False):
        return
    app._admin_base_installed = True
    try:
        from routes.admin_base import admin_base_bp
        if "admin_base" not in app.blueprints:
            _ORIG_REGISTER(app, admin_base_bp)
    except Exception as e:
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
            if "text/html" not in (resp.content_type or "").lower():
                return resp
            body = resp.get_data(as_text=True)
            if "admin-base-nav" in body or "</body>" not in body:
                return resp
            resp.set_data(body.replace("</body>", _NAV_SNIPPET + "</body>", 1))
        except Exception:
            pass
        return resp


try:
    import flask as _flask
    _ORIG_REGISTER = _flask.Flask.register_blueprint
    if os.environ.get("ADMIN_BASE_AUTOREG", "1") != "0" and not getattr(_flask.Flask.register_blueprint, "_admin_base_patched", False):
        def _patched_register_blueprint(self, blueprint, **options):
            result = _ORIG_REGISTER(self, blueprint, **options)
            if getattr(blueprint, "name", "") not in _SELF_BLUEPRINTS:
                _install(self)
            return result
        _patched_register_blueprint._admin_base_patched = True
        _flask.Flask.register_blueprint = _patched_register_blueprint
except Exception as _e:
    logger.warning("[admin_base] autoreg hook not installed: %r", _e)
