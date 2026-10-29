# -*- coding: utf-8 -*-
"""
Blueprint: Каталог олимпиадных задач (olymp_catalog) — OLYMP_CATALOG_V3.5

Отдельный раздел сайта на префиксе /olymp-catalog (не пересекается с разделом
«Олимпиады» /olympiads/* — пробники, методы, календарь).

Endpoints:
  GET  /olymp-catalog/                                 — каталог олимпиад
  GET  /olymp-catalog/<slug>                           — задачи олимпиады: год → этап → день → класс → №
  GET  /olymp-catalog/<slug>/<uid>                     — одна задача + ИИ-тьютор
  GET  /olymp-catalog/<slug>/<uid>/export/<fmt>        — скачать задачу: md | tex | txt | json
  GET  /olymp-catalog/<slug>/export/<fmt>              — скачать олимпиаду (фильтры q/year/grade/round): md | json
  GET  /olymp-catalog/figures/<path>                   — рисунки (static/olymp_figures/...)
  GET  /olymp-catalog/qa                               — отчёт чистки данных (JSON)
  GET  /olymp-catalog/gaps                             — дыры в нумерации задач (JSON; ?fmt=md — текст; ?slug=phystech)
  POST /olymp-catalog/api/tutor/prepare                — v4-pro заранее разбирает задачу (кэш)
  POST /olymp-catalog/api/tutor/chat                   — диалог с тьютором по задаче

Доступ: только авторизованные пользователи из белого списка OLYMP_CATALOG_USERS
(по умолчанию "lavrik,victor"). Для них же after_request-хук добавляет пункт
«🗂 Каталог задач олимпиад» в меню «Олимпиады» без правки base.html. OLYMP_CATALOG_NAV=0 отключает.
Скрытые олимпиады: OLYMP_CATALOG_HIDE (по умолчанию "other"). Чистка данных: OLYMP_CATALOG_CLEAN=0 отключает.

V3.5: «День N» показываем только там, где внутри одного (год, этап) реально больше одного дня
(у Физтеха и др. в данных day=0/1 вперемешку при отсутствии дней — раньше рисовалось «День 1»).

Модули: olymp_catalog_clean (чистка JSON при загрузке), olymp_catalog_tutor (deepseek-v4-pro),
olymp_catalog_export (md/tex/txt/json), olymp_catalog_gaps (дыры в нумерации, день).
"""
from __future__ import annotations

import functools
import json
import logging
import os
import re
import time
from collections import OrderedDict

from flask import (Blueprint, Response, abort, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from flask_login import current_user

from routes.olymp_catalog_clean import STATUS_LABEL, clean_task, new_qa
from routes.olymp_catalog_export import download, public_task, task_md, task_tex, task_txt
from routes.olymp_catalog_gaps import multi_day_keys, norm_day, report_md, summarize
from routes.olymp_catalog_tutor import (PREP_CACHE, PREP_TTL, SYSTEM_PROMPT, TUTOR_HISTORY, TUTOR_MODEL,
                                        TUTOR_THINKING, call_model, get_or_prepare, normalize_tutor_latex,
                                        task_context)

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_ROOT, "data", "olymp_catalog")
_FIG_DIR = os.path.join(_ROOT, "static", "olymp_figures")

URL_PREFIX = "/olymp-catalog"

olymp_catalog_bp = Blueprint("olymp_catalog", __name__, template_folder="../templates", url_prefix=URL_PREFIX)

_cache: dict = {}
_QA: dict = {}

_HIDDEN_SLUGS = {x.strip() for x in os.environ.get("OLYMP_CATALOG_HIDE", "other").split(",") if x.strip()}
_CLEAN = os.environ.get("OLYMP_CATALOG_CLEAN", "1").strip() not in ("0", "false", "no")

# ----------------------------------------------------------------------------
# Доступ
# ----------------------------------------------------------------------------

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
    try:
        if not getattr(user, "is_authenticated", False):
            return False
        return bool(_user_identities(user) & _allowed_users())
    except Exception:  # noqa: BLE001
        return False


def catalog_access_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        wants_json = request.path.startswith(URL_PREFIX + "/api/")
        if not current_user.is_authenticated:
            if wants_json:
                return jsonify(ok=False, error="auth_required"), 401
            try:
                return redirect(url_for("login", next=request.path))
            except Exception:  # noqa: BLE001
                abort(401)
        if not is_catalog_user(current_user):
            logger.warning("[olymp_catalog] forbidden for user id=%s", getattr(current_user, "id", "?"))
            if wants_json:
                return jsonify(ok=False, error="forbidden"), 403
            return render_template("olymp_catalog/denied.html"), 403
        return f(*args, **kwargs)
    return wrapped

# ----------------------------------------------------------------------------
# Данные
# ----------------------------------------------------------------------------

def _load(name: str):
    if name in _cache:
        return _cache[name]
    path = os.path.join(_DATA_DIR, name + ".json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if _CLEAN and name != "_index" and isinstance(data, list):
        qa = new_qa()
        qa["tasks"] = len(data)
        for t in data:
            try:
                clean_task(t, qa, _FIG_DIR)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[olymp_catalog] clean failed uid=%s: %s", str(t.get("uid", ""))[:12], exc)
        _QA[name] = qa
        logger.info("[olymp_catalog] cleaned %s: %s", name, qa)
    _cache[name] = data
    return data


def _visible_index():
    return [m for m in (_load("_index") or []) if m.get("slug") not in _HIDDEN_SLUGS]


def _slug_ok(slug: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9\-]+", slug or "")) and slug not in _HIDDEN_SLUGS


def _grade_key(g):
    try:
        return int(g)
    except Exception:  # noqa: BLE001
        return 99


def _group(tasks, all_tasks=None):
    """year -> sections(round, day) -> grades -> tasks, порядок как в файле.

    День подписываем только для (год, этап), где в полном наборе задач олимпиады реально
    больше одного дня; иначе day="" и секции с day=0/1 склеиваются в одну.
    """
    multi = multi_day_keys(all_tasks if all_tasks is not None else tasks)
    years: "OrderedDict[int, OrderedDict]" = OrderedDict()
    for t in tasks:
        y = years.setdefault(t["year"], OrderedDict())
        day = norm_day(t.get("day")) if (t["year"], str(t["round"])) in multi else ""
        sec = y.setdefault((t["round"], day), OrderedDict())
        sec.setdefault(t["grade"], []).append(t)
    result = []
    for y, secs in years.items():
        sec_list = []
        for (rnd, day), grades in secs.items():
            g_list = sorted(grades.items(), key=lambda kv: _grade_key(kv[0]))
            sec_list.append({"round": rnd, "day": day, "grades": g_list,
                             "count": sum(len(v) for _, v in g_list),
                             "anchor": "y%s_%s_%s" % (y, re.sub(r"\W", "", rnd), day)})
        result.append({"year": y, "sections": sec_list, "count": sum(s["count"] for s in sec_list)})
    return result


def _find_task(slug: str, uid: str):
    if not _slug_ok(slug):
        return None
    tasks = _load(slug) or []
    return next((x for x in tasks if x["uid"] == uid or x["uid"].startswith(uid)), None)


def _filter_tasks(tasks, q: str = "", year: str = "", grade: str = "", rnd: str = ""):
    if q:
        q = q.lower()
        tasks = [t for t in tasks if q in (t["text"] + " " + t["solution"] + " " + t["answer"]).lower()]
    if year:
        tasks = [t for t in tasks if str(t["year"]) == str(year)]
    if grade:
        tasks = [t for t in tasks if str(t["grade"]) == str(grade)]
    if rnd:
        # Баг Лаврика #27: фильтр по этапу (round)
        tasks = [t for t in tasks if str(t.get("round", "")) == str(rnd)]
    return tasks


def _rounds(tasks):
    """Список этапов олимпиады в порядке появления в файле (без дублей)."""
    return list(OrderedDict.fromkeys(str(t.get("round", "")) for t in tasks if t.get("round")))

# ----------------------------------------------------------------------------
# Страницы
# ----------------------------------------------------------------------------

@olymp_catalog_bp.route("/")
@catalog_access_required
def index():
    meta = _visible_index()
    total = sum(m["count"] for m in meta)
    with_figs = sum(m["with_figs"] for m in meta)
    return render_template("olymp_catalog/index.html", meta=meta, total=total, with_figs=with_figs,
                           tutor_model=TUTOR_MODEL)


@olymp_catalog_bp.route("/<slug>")
@catalog_access_required
def olympiad(slug):
    if not _slug_ok(slug):
        abort(404)
    all_tasks = _load(slug)
    if all_tasks is None:
        abort(404)
    meta = next((m for m in _visible_index() if m["slug"] == slug), None)
    q = (request.args.get("q") or "").strip()
    year = (request.args.get("year") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    rnd = (request.args.get("round") or "").strip()
    # Баг Лаврика #27: пока ничего не выбрано — показываем только выбор класса и этапа,
    # список задач появляется после выбора (picked).
    picked = bool(q or year or grade or rnd)
    # Каскадные фильтры: опции каждого списка зависят от остальных выборов,
    # поэтому выбрать комбинацию без задач («пустой пробник») нельзя.
    # Санитизация: пришедшие в URL несовместимые значения отбрасываем.
    for _ in range(3):
        grades = sorted({str(t["grade"]) for t in all_tasks
                         if (not rnd or str(t.get("round", "")) == str(rnd))
                         and (not year or str(t["year"]) == str(year))}, key=_grade_key)
        rounds = _rounds([t for t in all_tasks
                          if (not grade or str(t["grade"]) == str(grade))
                          and (not year or str(t["year"]) == str(year))])
        years_all = sorted({t["year"] for t in all_tasks
                            if (not grade or str(t["grade"]) == str(grade))
                            and (not rnd or str(t.get("round", "")) == str(rnd))}, reverse=True)
        if grade and grade not in grades:
            grade = ""
        elif rnd and rnd not in rounds:
            rnd = ""
        elif year and str(year) not in {str(y) for y in years_all}:
            year = ""
        else:
            break
    picked = bool(q or year or grade or rnd)
    tasks = _filter_tasks(all_tasks, q.lower(), year, grade, rnd) if picked else []
    return render_template("olymp_catalog/olympiad.html", slug=slug, meta=meta, years=_group(tasks, all_tasks),
                           count=len(tasks), total=len(all_tasks), q=q, year=year, grade=grade,
                           round=rnd, rounds=rounds, picked=picked,
                           grades=grades, years_all=years_all, labels=STATUS_LABEL)


@olymp_catalog_bp.route("/<slug>/<uid>")
@catalog_access_required
def task(slug, uid):
    t = _find_task(slug, uid)
    if not t:
        abort(404)
    tasks = _load(slug) or []
    idx = next((i for i, x in enumerate(tasks) if x["uid"] == t["uid"]), 0)
    prev_t = tasks[idx - 1] if idx > 0 else None
    next_t = tasks[idx + 1] if idx + 1 < len(tasks) else None
    prep = PREP_CACHE.get(t["uid"])
    return render_template("olymp_catalog/task.html", slug=slug, t=t, labels=STATUS_LABEL,
                           prev_t=prev_t, next_t=next_t, tutor_model=TUTOR_MODEL,
                           prep_ready=bool(prep and time.time() - prep["ts"] < PREP_TTL))


@olymp_catalog_bp.route("/qa")
@catalog_access_required
def qa_report():
    """Отчёт чистки: сколько задач поправлено по каждому типу (загружает все файлы)."""
    for m in _load("_index") or []:
        _load(m.get("slug", ""))
    total = new_qa()
    for st in _QA.values():
        for k, v in st.items():
            total[k] += v
    return jsonify(ok=True, clean_enabled=_CLEAN, total=total, by_olympiad=_QA)


@olymp_catalog_bp.route("/gaps")
@catalog_access_required
def gaps_report():
    """Дыры в нумерации задач по вариантам (год → этап → день → класс).

    /olymp-catalog/gaps            — JSON по всем видимым олимпиадам
    /olymp-catalog/gaps?fmt=md     — читаемый markdown-отчёт (text/plain)
    /olymp-catalog/gaps?slug=phystech — только одна олимпиада
    """
    only = (request.args.get("slug") or "").strip()
    summaries = [summarize(m["slug"], m["name"], _load(m["slug"]) or [])
                 for m in _visible_index() if not only or m["slug"] == only]
    if request.args.get("fmt") == "md":
        return Response(report_md(summaries), mimetype="text/plain; charset=utf-8")
    return jsonify(ok=True, olympiads=summaries)


@olymp_catalog_bp.route("/<slug>/<uid>/export/<fmt>")
@catalog_access_required
def export_task(slug, uid, fmt):
    t = _find_task(slug, uid)
    if not t:
        abort(404)
    base = "%s_%s_%s_g%s_n%s" % (slug, t["year"], re.sub(r"\W", "", str(t["round"]))[:12], t["grade"], t["num"])
    if fmt == "md":
        return download(task_md(t, slug, with_solution=request.args.get("sol", "1") != "0"), base + ".md", "text/markdown")
    if fmt == "tex":
        return download(task_tex(t), base + ".tex", "application/x-tex")
    if fmt == "txt":
        return download(task_txt(t), base + ".txt", "text/plain")
    if fmt == "json":
        return download(json.dumps(public_task(t), ensure_ascii=False, indent=2), base + ".json", "application/json")
    abort(404)


@olymp_catalog_bp.route("/<slug>/export/<fmt>")
@catalog_access_required
def export_olympiad(slug, fmt):
    if not _slug_ok(slug):
        abort(404)
    all_tasks = _load(slug)
    if all_tasks is None:
        abort(404)
    meta = next((m for m in _visible_index() if m["slug"] == slug), None)
    q = (request.args.get("q") or "").strip().lower()
    year = (request.args.get("year") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    rnd = (request.args.get("round") or "").strip()
    tasks = _filter_tasks(all_tasks, q, year, grade, rnd)
    suffix = "".join(["_%s" % year if year else "", "_g%s" % grade if grade else "",
                      "_%s" % re.sub(r"\W", "", rnd)[:12] if rnd else ""])
    if fmt == "json":
        return download(json.dumps([public_task(t) for t in tasks], ensure_ascii=False, indent=2),
                        "%s%s.json" % (slug, suffix), "application/json")
    if fmt == "md":
        name = meta["name"] if meta else slug
        out = ["# %s" % name, "", "Задач: %d. Экспорт из FORMYLA.net · %s" % (len(tasks), time.strftime("%Y-%m-%d")), ""]
        with_sol = request.args.get("sol", "1") != "0"
        for y in _group(tasks, all_tasks):
            out += ["", "# %s год" % y["year"], ""]
            for s in y["sections"]:
                out += ["", "## %s%s" % (s["round"], (" — день %s" % s["day"]) if s["day"] else ""), ""]
                for g, ts in s["grades"]:
                    out += ["", "### %s класс" % g, ""]
                    for t in ts:
                        out.append(task_md(t, slug, with_solution=with_sol).replace("## ", "#### ", 1))
                        out.append("---")
        return download("\n".join(out), "%s%s.md" % (slug, suffix), "text/markdown")
    abort(404)


@olymp_catalog_bp.route("/figures/<path:subpath>")
@catalog_access_required
def figure(subpath):
    return send_from_directory(_FIG_DIR, subpath)

# ----------------------------------------------------------------------------
# API тьютора
# ----------------------------------------------------------------------------

@olymp_catalog_bp.route("/api/tutor/prepare", methods=["POST"])
@catalog_access_required
def api_tutor_prepare():
    data = request.get_json(silent=True) or {}
    t = _find_task(str(data.get("slug", "")), str(data.get("uid", "")))
    if not t:
        return jsonify(ok=False, error="task_not_found"), 404
    try:
        res = get_or_prepare(t, force=bool(data.get("force")))
    except Exception as exc:  # noqa: BLE001
        logger.exception("[olymp_tutor] prepare failed: %s", exc)
        return jsonify(ok=False, error="model_error", detail=str(exc)[:300]), 502
    return jsonify(ok=True, ready=True, cached=res["cached"], brief=res["brief"], secs=res.get("secs"),
                   model=TUTOR_MODEL, usage=res.get("usage"), garbled=bool(t.get("garbled")))


@olymp_catalog_bp.route("/api/tutor/chat", methods=["POST"])
@catalog_access_required
def api_tutor_chat():
    data = request.get_json(silent=True) or {}
    t = _find_task(str(data.get("slug", "")), str(data.get("uid", "")))
    if not t:
        return jsonify(ok=False, error="task_not_found"), 404
    history = data.get("messages") or []
    clean = []
    for m in history[-TUTOR_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            clean.append({"role": role, "content": content[:12000]})
    if not clean or clean[-1]["role"] != "user":
        return jsonify(ok=False, error="no_user_message"), 400
    try:
        prep = get_or_prepare(t)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[olymp_tutor] prepare inside chat failed: %s", exc)
        prep = {"brief": "(конспект подготовки недоступен — разбирай задачу по ходу ответа, но отвечай уверенно)"}
    system = (SYSTEM_PROMPT + "\n\n=== ЗАДАЧА ===\n" + task_context(t)
              + "\n\n=== ТВОЙ КОНСПЕКТ ПОДГОТОВКИ (ты уже это проанализировал) ===\n" + prep["brief"])
    messages = [{"role": "system", "content": system}] + clean
    try:
        text, usage = call_model(messages, thinking=TUTOR_THINKING, temperature=0.3)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[olymp_tutor] chat failed: %s", exc)
        return jsonify(ok=False, error="model_error", detail=str(exc)[:300]), 502
    reply = normalize_tutor_latex(text).strip()
    return jsonify(ok=True, reply=reply, model=TUTOR_MODEL, usage=usage)

# ----------------------------------------------------------------------------
# Пункт меню (инжектор в base.html без правки файла) + регистрация
# ----------------------------------------------------------------------------

_NAV_DESKTOP_MARK = "Календарь олимпиад</a>"
_NAV_DESKTOP_LINK = '<a href="%s/" id="olymp-catalog-nav">🗂 Каталог задач олимпиад</a>' % URL_PREFIX
_NAV_DRAWER_RE = re.compile(r'(<span class="drawer-link-icon">\U0001F3C6</span>\s*Олимпиады\s*</a>)')
_NAV_DRAWER_LINK = ('<a href="%s/" class="drawer-link"><span class="drawer-link-icon">🗂</span>'
                    'Каталог задач олимпиад</a>') % URL_PREFIX
_NAV_BOTTOM_OLD = 'data-path="/olympiads*,/practice*,/olympiad*"'
_NAV_BOTTOM_NEW = 'data-path="/olympiads*,/practice*,/olympiad*,%s*"' % URL_PREFIX


def _inject_nav(resp):
    """Добавляет ссылку на каталог в меню «Олимпиады» только пользователям из белого списка."""
    try:
        if resp.direct_passthrough or resp.status_code != 200:
            return resp
        if "text/html" not in (resp.content_type or "").lower():
            return resp
        if not is_catalog_user(current_user):
            return resp
        body = resp.get_data(as_text=True)
        if "olymp-catalog-nav" in body or _NAV_DESKTOP_MARK not in body:
            return resp
        body = body.replace(_NAV_DESKTOP_MARK, _NAV_DESKTOP_MARK + _NAV_DESKTOP_LINK, 1)
        body = _NAV_DRAWER_RE.sub(lambda m: m.group(1) + _NAV_DRAWER_LINK, body, count=1)
        body = body.replace(_NAV_BOTTOM_OLD, _NAV_BOTTOM_NEW, 1)
        resp.set_data(body)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[olymp_catalog] nav inject skipped: %s", exc)
    return resp


def install_olymp_catalog(app) -> None:
    if getattr(app, "_olymp_catalog_installed", False):
        return
    app._olymp_catalog_installed = True
    if "olymp_catalog" not in app.blueprints:
        app.register_blueprint(olymp_catalog_bp)
    if os.environ.get("OLYMP_CATALOG_NAV", "1") != "0":
        app.after_request(_inject_nav)
    logger.info("[olymp_catalog] installed at %s (clean=%s)", URL_PREFIX, _CLEAN)
