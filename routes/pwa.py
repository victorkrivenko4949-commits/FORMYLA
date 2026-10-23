# -*- coding: utf-8 -*-
"""
routes/pwa.py — PWA_INSTALL_V3 (11.10.2026).

Делает сайт устанавливаемым приложением (PWA) без правки app.py и base.html:
  * GET  /sw.js              — service worker с корневым scope «/»
  * GET  /site.webmanifest   — манифест приложения (+ алиас /manifest.json)
  * GET  /offline            — офлайн-заглушка
  * POST /api/pwa/installed  — фиксирует установку приложения (таблица pwa_installs)
  * GET  /admin/pwa/stats    — JSON-сводка установок (только админ)
  * after_request            — вставляет <link rel="manifest"> и pwa_install.js
                               в HTML-страницы разрешённых пользователей.

Статистика установок: таблица `pwa_installs` создаётся автоматически при первой
записи. Раздел «База» (/admin/base) подхватывает её сам (категория «Активность»,
«Установки приложения (PWA)»). Установки тестовых аккаунтов (PWA_ALLOWED_USERS,
пока доступ не открыт всем) помечаются is_test=1 и в «реальный» счётчик не входят.

Регистрируется автоматически из routes/__init__.py (как admin_base).
Отключить: переменная окружения PWA_AUTOREG=0.

ОГРАНИЧЕНИЕ ПО АККАУНТАМ (этап тестирования): manifest и кнопка «Скачать
приложение» вставляются только пользователям из PWA_ALLOWED_USERS
(по умолчанию «lavrik,victor»; сравнение по nickname ИЛИ username, без учёта
регистра). Чтобы открыть всем — PWA_ALLOWED_USERS=* в окружении.
PWA_STATS_EXCLUDE_USERS — доп. список аккаунтов, чьи установки считать тестовыми
даже после открытия всем (по умолчанию «lavrik,victor»).

Когда будет удобно править base.html — добавьте в <head>:
    <link rel="manifest" href="/site.webmanifest">
и перед </body>:
    <script defer src="/static/js/pwa_install.js?v=5"></script>
Инжектор увидит, что теги уже есть, и ничего вставлять не будет.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

logger = logging.getLogger(__name__)

pwa_bp = Blueprint("pwa", __name__)

PWA_VERSION = "5"
_MANIFEST_TAG = '<link rel="manifest" href="/site.webmanifest">'
_SCRIPT_TAG = '<script defer src="/static/js/pwa_install.js?v=%s"></script>' % PWA_VERSION
_HEAD_RE = re.compile(r"<head(\s[^>]*)?>", re.IGNORECASE)


def _env_set(name: str, default: str) -> set[str]:
    return {u.strip().lower() for u in os.environ.get(name, default).split(",") if u.strip()}


# Кому показывать PWA на этапе теста. "*" — всем.
_ALLOWED_USERS = _env_set("PWA_ALLOWED_USERS", "lavrik,victor")
# Чьи установки всегда считать тестовыми (не входят в «реальный» счётчик).
_TEST_USERS = _env_set("PWA_STATS_EXCLUDE_USERS", "lavrik,victor")


def _current_user_names() -> tuple[object | None, set[str]]:
    """(current_user | None, {nickname, username} в нижнем регистре)."""
    try:
        from flask_login import current_user
        if not getattr(current_user, "is_authenticated", False):
            return None, set()
        if getattr(current_user, "is_guest", False):
            return None, set()
        names = {
            str(getattr(current_user, attr, "") or "").strip().lower()
            for attr in ("nickname", "username")
        }
        names.discard("")
        return current_user, names
    except Exception:  # noqa: BLE001
        return None, set()


def _user_allowed() -> bool:
    """True, если текущий пользователь входит в PWA_ALLOWED_USERS (или там «*»)."""
    if not _ALLOWED_USERS or "*" in _ALLOWED_USERS:
        return True
    _, names = _current_user_names()
    return bool(names & _ALLOWED_USERS)


def _static_dir() -> str:
    return current_app.static_folder or os.path.join(current_app.root_path, "static")


# ──────────────────────────────────────────────────────────────────────
# Таблица установок
# ──────────────────────────────────────────────────────────────────────
try:
    from models import db
except Exception as _e:  # noqa: BLE001
    db = None  # type: ignore[assignment]
    logger.warning("[pwa] models.db unavailable, install stats disabled: %r", _e)

PwaInstall = None
if db is not None:
    class PwaInstall(db.Model):  # type: ignore[no-redef]
        """Одна строка = одна установка приложения на устройство."""
        __tablename__ = "pwa_installs"
        __table_args__ = {"extend_existing": True}

        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, nullable=True, index=True)
        username = db.Column(db.String(120), nullable=True)
        platform = db.Column(db.String(32), nullable=True)     # android / ios / desktop / other
        source = db.Column(db.String(32), nullable=True)       # appinstalled / timer / standalone_launch
        user_agent = db.Column(db.String(300), nullable=True)
        is_test = db.Column(db.Boolean, nullable=False, default=False)
        created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

_table_ready = False


def _ensure_table() -> bool:
    global _table_ready
    if _table_ready:
        return True
    if db is None or PwaInstall is None:
        return False
    try:
        PwaInstall.__table__.create(bind=db.engine, checkfirst=True)
        _table_ready = True
    except Exception as e:  # noqa: BLE001
        logger.warning("[pwa] create pwa_installs failed: %r", e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
    return _table_ready


def _platform_from_ua(ua: str) -> str:
    u = (ua or "").lower()
    if "android" in u:
        return "android"
    if "iphone" in u or "ipad" in u or "ipod" in u:
        return "ios"
    if "windows" in u or "macintosh" in u or "linux" in u or "cros" in u:
        return "desktop"
    return "other"


# ──────────────────────────────────────────────────────────────────────
# Маршруты
# ──────────────────────────────────────────────────────────────────────
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


@pwa_bp.route("/api/pwa/installed", methods=["POST"])
def api_installed():
    """Клиент сообщает об установке (appinstalled / первый запуск standalone)."""
    if not _ensure_table():
        return jsonify(ok=False, error="stats unavailable"), 503
    data = request.get_json(silent=True) or {}
    ua = (request.headers.get("User-Agent") or "")[:300]
    platform = str(data.get("platform") or _platform_from_ua(ua))[:32].lower()
    source = str(data.get("source") or "appinstalled")[:32]

    user, names = _current_user_names()
    uid = None
    uname = None
    if user is not None:
        try:
            uid = int(getattr(user, "id", None))
        except Exception:  # noqa: BLE001
            uid = None
        uname = (str(getattr(user, "username", "") or getattr(user, "nickname", "") or "")[:120]) or None

    restricted = bool(_ALLOWED_USERS) and "*" not in _ALLOWED_USERS
    is_test = bool(names & _TEST_USERS) or (restricted and bool(names & _ALLOWED_USERS))

    try:
        # Дедупликация: тот же пользователь + платформа за последние 10 минут — не считаем.
        if uid is not None:
            since = datetime.utcnow() - timedelta(minutes=10)
            dup = (PwaInstall.query
                   .filter(PwaInstall.user_id == uid,
                           PwaInstall.platform == platform,
                           PwaInstall.created_at >= since)
                   .first())
            if dup is not None:
                return jsonify(ok=True, duplicate=True, id=dup.id)

        row = PwaInstall(user_id=uid, username=uname, platform=platform, source=source,
                         user_agent=ua, is_test=is_test)
        db.session.add(row)
        db.session.commit()
        logger.info("[pwa] install recorded id=%s user=%s platform=%s test=%s", row.id, uname, platform, is_test)
        return jsonify(ok=True, id=row.id, is_test=is_test)
    except Exception as e:  # noqa: BLE001
        logger.exception("[pwa] record install failed: %r", e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return jsonify(ok=False, error="db error"), 500


@pwa_bp.route("/admin/pwa/stats")
def admin_pwa_stats():
    """JSON-сводка установок приложения (только админ)."""
    user, _ = _current_user_names()
    if user is None or getattr(user, "is_admin", False) is not True:
        abort(403)
    if not _ensure_table():
        return jsonify(ok=False, error="stats unavailable"), 503
    try:
        from sqlalchemy import func
        now = datetime.utcnow()
        q = db.session.query

        def _count(*filters) -> int:
            return int(q(func.count(PwaInstall.id)).filter(*filters).scalar() or 0)

        real = PwaInstall.is_test.is_(False)
        by_platform = {
            p or "other": int(n) for p, n in
            q(PwaInstall.platform, func.count(PwaInstall.id)).filter(real).group_by(PwaInstall.platform).all()
        }
        unique_users = int(q(func.count(func.distinct(PwaInstall.user_id)))
                           .filter(real, PwaInstall.user_id.isnot(None)).scalar() or 0)
        recent = [{
            "id": r.id, "user_id": r.user_id, "username": r.username, "platform": r.platform,
            "source": r.source, "is_test": r.is_test,
            "created_at": r.created_at.isoformat(sep=" ", timespec="seconds") if r.created_at else None,
        } for r in PwaInstall.query.order_by(PwaInstall.created_at.desc()).limit(50).all()]
        return jsonify({
            "generated_at": now.isoformat(sep=" ", timespec="seconds"),
            "installs_total": _count(real),
            "installs_unique_users": unique_users,
            "installs_last_24h": _count(real, PwaInstall.created_at >= now - timedelta(days=1)),
            "installs_last_7d": _count(real, PwaInstall.created_at >= now - timedelta(days=7)),
            "installs_last_30d": _count(real, PwaInstall.created_at >= now - timedelta(days=30)),
            "by_platform": by_platform,
            "test_installs": _count(PwaInstall.is_test.is_(True)),
            "recent": recent,
        })
    except Exception as e:  # noqa: BLE001
        logger.exception("[pwa] stats failed: %r", e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return jsonify(ok=False, error="db error"), 500


# ──────────────────────────────────────────────────────────────────────
# Инжектор manifest + скрипта
# ──────────────────────────────────────────────────────────────────────
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
        # Человеческое имя таблицы в разделе «База».
        try:
            from services import admin_base_stats as _abs
            _abs.TABLE_META["pwa_installs"] = ("Активность", "Установки приложения (PWA)")
        except Exception:  # noqa: BLE001
            pass
        msg = "[BP] pwa_bp registered (/sw.js, /site.webmanifest, /offline, /api/pwa/installed); allowed users: %s" % \
              ", ".join(sorted(_ALLOWED_USERS))
        logger.info(msg)
        print(msg)
    except Exception as e:  # noqa: BLE001
        logger.exception("[pwa] auto-register failed: %r", e)
