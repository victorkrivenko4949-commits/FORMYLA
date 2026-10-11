# -*- coding: utf-8 -*-
"""
routes/pwa.py — PWA_INSTALL_V2 (11.10.2026).

Делает сайт устанавливаемым приложением (PWA) без правки app.py и base.html:
  * GET /sw.js            — service worker с корневым scope «/»
  * GET /site.webmanifest — манифест приложения (+ алиас /manifest.json)
  * GET /offline          — офлайн-заглушка
  * after_request         — вставляет <link rel="manifest"> в <head> и
                            pwa_install.js перед </body> в HTML-страницы,
                            если их там ещё нет.

Регистрируется автоматически из routes/__init__.py (как admin_base).
Отключить: переменная окружения PWA_AUTOREG=0.

ОГРАНИЧЕНИЕ ПО АККАУНТАМ (этап тестирования): manifest и кнопка «Скачать
приложение» вставляются только пользователям из PWA_ALLOWED_USERS
(по умолчанию «lavrik,victor»; сравнение по nickname ИЛИ username, без учёта
регистра). Чтобы открыть всем — PWA_ALLOWED_USERS=* в окружении.

Когда будет удобно править base.html — добавьте в <head>:
    <link rel="manifest" href="/site.webmanifest">
и перед </body>:
    <script defer src="/static/js/pwa_install.js?v=2"></script>
Инжектор увидит, что теги уже есть, и ничего вставлять не будет.
"""
from __future__ import annotations

import logging
import os
import re

from flask import Blueprint, current_app, send_from_directory

logger = logging.getLogger(__name__)

pwa_bp = Blueprint("pwa", __name__)

PWA_VERSION = "2"
_MANIFEST_TAG = '<link rel="manifest" href="/site.webmanifest">'
_SCRIPT_TAG = '<script defer src="/static/js/pwa_install.js?v=%s"></script>' % PWA_VERSION
_HEAD_RE = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)

# Кому показывать PWA на этапе теста. "*" — всем.
_ALLOWED_USERS = {
    u.strip().lower()
    for u in os.environ.get("PWA_ALLOWED_USERS", "lavrik,victor").split(",")
    if u.strip()
}


def _user_allowed() -> bool:
    """True, если текущий пользователь входит в PWA_ALLOWED_USERS (или там «*»)."""
    if not _ALLOWED_USERS or "*" in _ALLOWED_USERS:
        return True
    try:
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return False
        if getattr(current_user, "is_guest", False):
            return False
        names = {
            str(getattr(current_user, attr, "") or "").strip().lower()
            for attr in ("nickname", "username")
        }
        return bool(names & _ALLOWED_USERS)
    except Exception:  # noqa: BLE001
        return False


def _static_dir() -> str:
    return current_app.static_folder or os.path.join(current_app.root_path, "static")


@pwa_bp.route("/sw.js")
def service_worker():
    resp = send_from_directory(_static_dir(), "sw.js", mimetype="application/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@pwa_bp.route("/site.webmanifest")
@pwa_bp.route("/manifest.json")
def manifest():
    resp = send_from_directory(_static_dir(), "site.webmanifest", mimetype="application/manifest+json")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@pwa_bp.route("/offline")
def offline():
    return send_from_directory(_static_dir(), "offline.html", mimetype="text/html")


def _inject(resp):
    """Добавляет manifest и pwa_install.js в обычный HTML-ответ 200 разрешённого пользователя."""
    try:
        if resp.direct_passthrough or resp.is_streamed or resp.status_code != 200:
            return resp
        ct = (resp.content_type or "").lower()
        if "text/html" not in ct:
            return resp
        if not _user_allowed():
            return resp
        body = resp.get_data(as_text=True)
        if "</body>" not in body:
            return resp
        changed = False
        if 'rel="manifest"' not in body and "rel='manifest'" not in body:
            m = _HEAD_RE.search(body)
            if m:
                body = body[: m.end()] + "\n    " + _MANIFEST_TAG + body[m.end():]
                changed = True
        if "pwa_install.js" not in body:
            j = body.rfind("</body>")  # последний </body>, а не случайный внутри <script>
            body = body[:j] + _SCRIPT_TAG + "\n" + body[j:]
            changed = True
        if changed:
            resp.set_data(body)
    except Exception:  # noqa: BLE001
        pass
    return resp


def install_pwa(app) -> None:
    if getattr(app, "_pwa_installed", False):
        return
    app._pwa_installed = True
    try:
        if "pwa" not in app.blueprints:
            app.register_blueprint(pwa_bp)
        app.after_request(_inject)
        msg = "[BP] pwa_bp registered (/sw.js, /site.webmanifest, /offline); allowed users: %s" % \
              ", ".join(sorted(_ALLOWED_USERS))
        logger.info(msg)
        print(msg)
    except Exception as e:  # noqa: BLE001
        logger.exception("[pwa] auto-register failed: %r", e)
