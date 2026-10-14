# -*- coding: utf-8 -*-
"""
Blueprint: Каталог олимпиадных задач (olymp_catalog) — OLYMP_CATALOG_V1

Endpoints:
  GET /olympiads                         — каталог олимпиад (таблица)
  GET /olympiads/<slug>                  — задачи олимпиады: год → этап → день → класс → №
  GET /olympiads/<slug>/<uid>            — одна задача
  GET /olympiads/figures/<path>          — рисунки (static/olymp_figures/...)

Доступ: только авторизованные пользователи из белого списка.
Белый список — переменная окружения OLYMP_CATALOG_USERS (через запятую),
по умолчанию "lavrik,victor". Сравнение без учёта регистра с полями
nickname, name, email, часть email до @, telegram_username, display_name.
Данные: data/olymp_catalog/_index.json + data/olymp_catalog/<slug>.json
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re
from collections import OrderedDict

from flask import Blueprint, abort, render_template, send_from_directory, redirect, url_for, request
from flask_login import current_user

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_ROOT, "data", "olymp_catalog")
_FIG_DIR = os.path.join(_ROOT, "static", "olymp_figures")

olymp_catalog_bp = Blueprint("olymp_catalog", __name__, template_folder="../templates")

_cache: dict = {}


def _allowed_users() -> set:
    raw = os.environ.get("OLYMP_CATALOG_USERS", "lavrik,victor")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _user_identities(user) -> set:
    ids = set()
    for attr in ("nickname", "name", "email", "telegram_username", "display_name", "username"):
        try:
            v = getattr(user, attr, None)
        except Exception:  # noqa: BLE001
            v = None
        if v:
            v = str(v).strip().lower()
            ids.add(v)
            if "@" in v:
                ids.add(v.split("@", 1)[0])
    return ids


def is_catalog_user(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(_user_identities(user) & _allowed_users())


def catalog_access_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            try:
                return redirect(url_for("login", next=request.path))
            except Exception:  # noqa: BLE001
                abort(401)
        if not is_catalog_user(current_user):
            logger.warning("[olymp_catalog] forbidden for user id=%s", getattr(current_user, "id", "?"))
            return render_template("olymp_catalog/denied.html"), 403
        return f(*args, **kwargs)
    return wrapped


def _load(name: str):
    if name in _cache:
        return _cache[name]
    path = os.path.join(_DATA_DIR, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    _cache[name] = data
    return data


def _grade_key(g):
    try:
        return int(g)
    except Exception:  # noqa: BLE001
        return 99


def _group(tasks):
    """year -> sections(round, day) -> grades -> tasks, порядок как в файле."""
    years: "OrderedDict[int, OrderedDict]" = OrderedDict()
    for t in tasks:
        y = years.setdefault(t["year"], OrderedDict())
        sec = y.setdefault((t["round"], t["day"]), OrderedDict())
        sec.setdefault(t["grade"], []).append(t)
    result = []
    for y, secs in years.items():
        sec_list = []
        for (rnd, day), grades in secs.items():
            g_list = sorted(grades.items(), key=lambda kv: _grade_key(kv[0]))
            sec_list.append({"round": rnd, "day": day, "grades": g_list,
                             "count": sum(len(v) for _, v in g_list),
                             "anchor": "y%s_%s_%s" % (y, re.sub(r"\W", "", rnd), day)})
        result.append({"year": y, "sections": sec_list})
    return result


STATUS_LABEL = {
    "official_found": "официальное", "official": "официальное", "AI_verified": "проверено ИИ",
    "gemini_solved": "Gemini", "official_variant": "вариант источника", "AI_generated": "сгенерировано",
    "AI_generated_with_hints": "набросок", "unresolved": "не решено", "broken_text": "условие повреждено",
    "figure_only": "только рисунок",
}


@olymp_catalog_bp.route("/olympiads")
@catalog_access_required
def index():
    meta = _load("_index") or []
    total = sum(m["count"] for m in meta)
    with_figs = sum(m["with_figs"] for m in meta)
    return render_template("olymp_catalog/index.html", meta=meta, total=total, with_figs=with_figs)


@olymp_catalog_bp.route("/olympiads/<slug>")
@catalog_access_required
def olympiad(slug):
    if not re.fullmatch(r"[a-z0-9\-]+", slug):
        abort(404)
    tasks = _load(slug)
    if tasks is None:
        abort(404)
    meta = next((m for m in (_load("_index") or []) if m["slug"] == slug), None)
    q = (request.args.get("q") or "").strip().lower()
    if q:
        tasks = [t for t in tasks if q in (t["text"] + " " + t["solution"] + " " + t["answer"]).lower()]
    return render_template("olymp_catalog/olympiad.html", slug=slug, meta=meta, years=_group(tasks),
                           count=len(tasks), q=q, labels=STATUS_LABEL)


@olymp_catalog_bp.route("/olympiads/<slug>/<uid>")
@catalog_access_required
def task(slug, uid):
    if not re.fullmatch(r"[a-z0-9\-]+", slug):
        abort(404)
    tasks = _load(slug) or []
    t = next((x for x in tasks if x["uid"] == uid or x["uid"].startswith(uid)), None)
    if not t:
        abort(404)
    return render_template("olymp_catalog/task.html", slug=slug, t=t, labels=STATUS_LABEL)


@olymp_catalog_bp.route("/olympiads/figures/<path:subpath>")
@catalog_access_required
def figure(subpath):
    return send_from_directory(_FIG_DIR, subpath)


def install_olymp_catalog(app) -> None:
    if getattr(app, "_olymp_catalog_installed", False):
        return
    app._olymp_catalog_installed = True
    if "olymp_catalog" not in app.blueprints:
        app.register_blueprint(olymp_catalog_bp)
    logger.info("[BP] olymp_catalog_bp registered (/olympiads)")
    print("[BP] olymp_catalog_bp registered (/olympiads)")
