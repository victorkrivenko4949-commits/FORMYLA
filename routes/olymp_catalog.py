# -*- coding: utf-8 -*-
"""
Blueprint: Каталог олимпиадных задач (olymp_catalog) — OLYMP_CATALOG_V3

Отдельный раздел сайта на префиксе /olymp-catalog (не пересекается с разделом
«Олимпиады» /olympiads/* — пробники, методы, календарь).

Endpoints:
  GET  /olymp-catalog/                                 — каталог олимпиад
  GET  /olymp-catalog/<slug>                           — задачи олимпиады: год → этап → день → класс → №
  GET  /olymp-catalog/<slug>/<uid>                     — одна задача + ИИ-тьютор
  GET  /olymp-catalog/<slug>/<uid>/export/<fmt>        — скачать задачу: md | tex | txt | json
  GET  /olymp-catalog/<slug>/export/<fmt>              — скачать олимпиаду (фильтры q/year/grade): md | json
  GET  /olymp-catalog/figures/<path>                   — рисунки (static/olymp_figures/...)
  POST /olymp-catalog/api/tutor/prepare                — v4-pro заранее разбирает задачу (кэш)
  POST /olymp-catalog/api/tutor/chat                   — диалог с тьютором по задаче

Доступ: только авторизованные пользователи из белого списка OLYMP_CATALOG_USERS
(по умолчанию "lavrik,victor"). Для них же after_request-хук добавляет пункт
«🗂 Каталог задач олимпиад» в меню «Олимпиады» (десктоп + мобильный drawer)
без правки base.html (тот же приём, что у кнопки «📦 База»). OLYMP_CATALOG_NAV=0 отключает.

Тьютор: deepseek-v4-pro (OLYMP_TUTOR_MODEL), режим thinking. При открытии задачи
фронтенд вызывает /prepare: модель получает условие + эталонное решение и жёсткую
инструкцию «проанализируй, пойми решение, подготовься к вопросам». Конспект
подготовки кэшируется и подкладывается в system-prompt каждого сообщения чата.
Все ответы проходят LaTeX-нормализацию.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict

from flask import (Blueprint, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from flask_login import current_user

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_ROOT, "data", "olymp_catalog")
_FIG_DIR = os.path.join(_ROOT, "static", "olymp_figures")

URL_PREFIX = "/olymp-catalog"

olymp_catalog_bp = Blueprint("olymp_catalog", __name__, template_folder="../templates", url_prefix=URL_PREFIX)

_cache: dict = {}

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
        result.append({"year": y, "sections": sec_list, "count": sum(s["count"] for s in sec_list)})
    return result


def _find_task(slug: str, uid: str):
    if not re.fullmatch(r"[a-z0-9\-]+", slug or ""):
        return None
    tasks = _load(slug) or []
    return next((x for x in tasks if x["uid"] == uid or x["uid"].startswith(uid)), None)


def _filter_tasks(tasks, q: str = "", year: str = "", grade: str = ""):
    if q:
        q = q.lower()
        tasks = [t for t in tasks if q in (t["text"] + " " + t["solution"] + " " + t["answer"]).lower()]
    if year:
        tasks = [t for t in tasks if str(t["year"]) == str(year)]
    if grade:
        tasks = [t for t in tasks if str(t["grade"]) == str(grade)]
    return tasks


STATUS_LABEL = {
    "official_found": "официальное", "official": "официальное", "AI_verified": "проверено ИИ",
    "gemini_solved": "Gemini", "official_variant": "вариант источника", "AI_generated": "сгенерировано",
    "AI_generated_with_hints": "набросок", "unresolved": "не решено", "broken_text": "условие повреждено",
    "figure_only": "только рисунок",
}

# ----------------------------------------------------------------------------
# LaTeX-нормализация
# ----------------------------------------------------------------------------

_UNICODE_MATH = {
    "×": r"\cdot", "·": r"\cdot", "÷": ":", "−": "-", "≤": r"\le", "≥": r"\ge", "≠": r"\ne",
    "±": r"\pm", "∞": r"\infty", "√": r"\sqrt", "°": r"^{\circ}", "∠": r"\angle", "∈": r"\in",
    "∉": r"\notin", "⊂": r"\subset", "∪": r"\cup", "∩": r"\cap", "→": r"\to", "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow", "∑": r"\sum", "∏": r"\prod", "≡": r"\equiv", "≈": r"\approx",
    "²": "^{2}", "³": "^{3}", "π": r"\pi", "α": r"\alpha", "β": r"\beta", "γ": r"\gamma",
}


def _latex_fallback(text: str) -> str:
    """Минимальная нормализация: \\( \\) → $ $, \\[ \\] → $$ $$, юникод-математика внутри $…$."""
    if not text:
        return text
    t = text.replace(r"\(", "$").replace(r"\)", "$").replace(r"\[", "$$").replace(r"\]", "$$")

    def fix_math(m):
        inner = m.group(0)
        for k, v in _UNICODE_MATH.items():
            inner = inner.replace(k, v + " " if v.startswith("\\") and not v.endswith("}") else v)
        return inner

    t = re.sub(r"\$\$.*?\$\$|\$[^$\n]+?\$", fix_math, t, flags=re.S)
    t = re.sub(r"\$\$\s*\n?\s*\$\$", "", t)
    return t


def normalize_tutor_latex(text: str) -> str:
    try:
        from method_week.latex import normalize_latex  # type: ignore
        text = normalize_latex(text)
    except Exception:  # noqa: BLE001
        pass
    return _latex_fallback(text)

# ----------------------------------------------------------------------------
# ИИ-тьютор (deepseek-v4-pro, thinking)
# ----------------------------------------------------------------------------

TUTOR_MODEL = os.environ.get("OLYMP_TUTOR_MODEL", "deepseek-v4-pro").strip()
TUTOR_MAX_TOKENS = int(os.environ.get("OLYMP_TUTOR_MAX_TOKENS", "8000"))
TUTOR_THINKING = os.environ.get("OLYMP_TUTOR_THINKING", "1").strip() not in ("0", "false", "no")
TUTOR_HISTORY = int(os.environ.get("OLYMP_TUTOR_HISTORY", "24"))
_PREP_TTL = int(os.environ.get("OLYMP_TUTOR_PREP_TTL", str(12 * 3600)))

_PREP_CACHE: dict = {}          # uid -> {"brief": str, "ts": float, "usage": dict}
_PREP_LOCKS: dict = {}
_PREP_LOCKS_GUARD = threading.Lock()

SYSTEM_PROMPT = (
    "Ты — ИИ-тьютор FORMYLA по олимпиадной математике (модель deepseek-v4-pro). "
    "Ты уже ЗАРАНЕЕ, до первого вопроса ученика, полностью проанализировал задачу: разобрал условие, "
    "понял эталонное решение по шагам, нашёл ключевую идею, проверил ответ, продумал типичные ошибки и "
    "вероятные вопросы. Ниже даны задача и твой конспект подготовки. Отвечай как преподаватель, который "
    "уже всё знает про эту задачу: без «дайте подумать», сразу по существу.\n\n"
    "ПРАВИЛА:\n"
    "1. Отвечай по-русски, кратко и структурно; Markdown допустим (### заголовки, списки, **жирный**).\n"
    "2. ВСЕ формулы, переменные, числа с операциями — ТОЛЬКО в LaTeX: строчные $...$, выключные $$...$$. "
    "Запрещены \\( \\), \\[ \\], формулы без долларов и юникод-математика (×, ², √, ≤, °) — "
    "используй \\cdot, ^{2}, \\sqrt{}, \\le, ^{\\circ}.\n"
    "3. Если ученик просит подсказку — веди по шагам (сократовский метод), не раскрывай всё сразу. "
    "Если явно просит полное решение — дай полностью и аккуратно.\n"
    "4. Если ученик присылает своё решение — проверь по шагам, укажи первую ошибку и почему это ошибка.\n"
    "5. Если эталонное решение содержит пробел или ошибку — честно скажи и дай исправленную версию.\n"
    "6. Не выдумывай условий, которых нет в задаче. Если чего-то не хватает (например, рисунка) — скажи об этом."
)

PREPARE_PROMPT = (
    "ЖЁСТКАЯ ИНСТРУКЦИЯ: сейчас ученика ещё нет. Проанализируй задачу, ПОЛНОСТЬЮ пойми эталонное решение "
    "(проверь каждый переход и итоговый ответ) и подготовься к вопросам. Результат — твой рабочий конспект, "
    "который ты будешь держать перед глазами во время диалога. Формат — Markdown, формулы только в $...$ / $$...$$:\n\n"
    "### Суть задачи\n1–2 предложения: что дано, что требуется.\n"
    "### Ключевая идея\nГлавный приём/наблюдение, без которого задача не решается.\n"
    "### Решение по шагам\nНумерованный список; для каждого шага — почему он верен.\n"
    "### Проверка ответа\nСверка с эталонным ответом; если есть расхождение — разбор.\n"
    "### Где ученики ошибаются\n3 типичные ошибки.\n"
    "### Вероятные вопросы ученика и заготовки ответов\n5 пунктов «вопрос → короткий ответ».\n"
    "### Подсказки по уровням\nТри подсказки: лёгкая (направление), средняя (ключевой факт), сильная (почти решение).\n"
    "### Замечания к эталону\nЕсли эталон неполон/ошибочен — опиши и исправь; иначе напиши «Эталон корректен»."
)


def _task_context(t: dict) -> str:
    head = "%s, %s, %s" % (t.get("olymp", ""), t.get("year", ""), t.get("round", ""))
    if t.get("day"):
        head += ", день %s" % t["day"]
    head += ", %s класс, задача %s" % (t.get("grade", ""), t.get("num", ""))
    parts = ["ЗАДАЧА: " + head, "УСЛОВИЕ:\n" + (t.get("text") or "").strip()]
    if t.get("fig_statement"):
        parts.append("К условию прилагается рисунок (%d шт.), в текстовом виде он недоступен — опирайся на условие."
                     % len(t["fig_statement"]))
    if t.get("answer"):
        parts.append("ЭТАЛОННЫЙ ОТВЕТ:\n" + str(t["answer"]).strip())
    sol = (t.get("solution") or "").strip()
    if sol:
        parts.append("ЭТАЛОННОЕ РЕШЕНИЕ (статус: %s):\n%s" % (STATUS_LABEL.get(t.get("status"), t.get("status")), sol))
    else:
        parts.append("ЭТАЛОННОЕ РЕШЕНИЕ: отсутствует — реши задачу самостоятельно и будь особенно внимателен.")
    if t.get("source"):
        parts.append("ИСТОЧНИК: " + str(t["source"]))
    return "\n\n".join(parts)


async def _ds_chat(messages, thinking: bool, max_tokens: int, temperature: float):
    from daily_tasks.pipeline.deepseek_client import DeepSeekClient
    async with DeepSeekClient() as client:
        client._model = TUTOR_MODEL  # принудительно v4-pro
        text, usage = await client.async_chat(TUTOR_MODEL, messages, temperature=temperature,
                                              max_tokens=max_tokens, thinking=thinking)
        return text, {"in": usage.input_tokens, "out": usage.output_tokens, "cost_usd": round(usage.cost_usd, 6)}


def _call_model(messages, thinking: bool = True, max_tokens: int = TUTOR_MAX_TOKENS, temperature: float = 0.3):
    return asyncio.run(_ds_chat(messages, thinking, max_tokens, temperature))


def _prep_lock(uid: str) -> threading.Lock:
    with _PREP_LOCKS_GUARD:
        lock = _PREP_LOCKS.get(uid)
        if lock is None:
            lock = _PREP_LOCKS[uid] = threading.Lock()
        return lock


def _get_or_prepare(t: dict, force: bool = False) -> dict:
    uid = t["uid"]
    now = time.time()
    hit = _PREP_CACHE.get(uid)
    if hit and not force and now - hit["ts"] < _PREP_TTL:
        return {**hit, "cached": True}
    with _prep_lock(uid):
        hit = _PREP_CACHE.get(uid)
        if hit and not force and time.time() - hit["ts"] < _PREP_TTL:
            return {**hit, "cached": True}
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _task_context(t) + "\n\n" + PREPARE_PROMPT},
        ]
        t0 = time.time()
        text, usage = _call_model(messages, thinking=TUTOR_THINKING, temperature=0.2)
        brief = normalize_tutor_latex(text).strip()
        entry = {"brief": brief, "ts": time.time(), "usage": usage, "secs": round(time.time() - t0, 1)}
        _PREP_CACHE[uid] = entry
        logger.info("[olymp_tutor] prepared uid=%s in %.1fs usage=%s", uid[:12], entry["secs"], usage)
        return {**entry, "cached": False}

# ----------------------------------------------------------------------------
# Экспорт
# ----------------------------------------------------------------------------

def _fig_url(f: str) -> str:
    return request.host_url.rstrip("/") + url_for("olymp_catalog.figure", subpath=f)


def _task_md(t: dict, slug: str, with_solution: bool = True) -> str:
    title = "%s %s — %s%s — %s класс — задача %s" % (
        t["olymp"], t["year"], t["round"], (" — день %s" % t["day"]) if t.get("day") else "", t["grade"], t["num"])
    out = ["## " + title, "", "**Условие.** " + t["text"].strip(), ""]
    for f in t.get("fig_statement") or []:
        out.append("![рисунок к условию](%s)" % _fig_url(f))
    if t.get("answer"):
        out += ["", "**Ответ.** " + str(t["answer"]).strip()]
    if with_solution and t.get("solution"):
        out += ["", "**Решение.** " + t["solution"].strip()]
        for f in t.get("fig_solution") or []:
            out.append("![рисунок к решению](%s)" % _fig_url(f))
    if t.get("source"):
        out += ["", "_Источник: %s_" % t["source"]]
    out += ["", "_%s · статус решения: %s · %s_" % (
        request.host_url.rstrip("/") + url_for("olymp_catalog.task", slug=slug, uid=t["uid"][:12]),
        STATUS_LABEL.get(t.get("status"), t.get("status")), t["uid"][:12])]
    return "\n".join(out) + "\n"


def _tex_escape_text(s: str) -> str:
    """Экранируем спецсимволы ВНЕ формул; формулы ($…$ / $$…$$) оставляем как есть."""
    parts = re.split(r"(\$\$.*?\$\$|\$[^$\n]+?\$)", s, flags=re.S)
    res = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            res.append(p)
        else:
            p = p.replace("\\", r"\textbackslash{}")
            for a, b in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                         ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
                p = p.replace(a, b)
            res.append(p.replace("\n", "\n\n"))
    return "".join(res)


def _task_tex(t: dict) -> str:
    title = "%s %s. %s%s. %s класс, задача %s" % (
        t["olymp"], t["year"], t["round"], (", день %s" % t["day"]) if t.get("day") else "", t["grade"], t["num"])
    body = ["\\documentclass[12pt,a4paper]{article}",
            "\\usepackage[utf8]{inputenc}", "\\usepackage[T2A]{fontenc}", "\\usepackage[russian]{babel}",
            "\\usepackage{amsmath,amssymb,amsthm}", "\\usepackage{graphicx}", "\\usepackage[margin=2cm]{geometry}",
            "\\begin{document}", "\\section*{%s}" % _tex_escape_text(title), "",
            "\\textbf{Условие.} " + _tex_escape_text(t["text"].strip()), ""]
    for f in t.get("fig_statement") or []:
        body += ["% рисунок к условию: " + f, "% \\includegraphics[width=.6\\textwidth]{%s}" % os.path.basename(f), ""]
    if t.get("answer"):
        body += ["\\textbf{Ответ.} " + _tex_escape_text(str(t["answer"]).strip()), ""]
    if t.get("solution"):
        body += ["\\textbf{Решение.} " + _tex_escape_text(t["solution"].strip()), ""]
        for f in t.get("fig_solution") or []:
            body += ["% рисунок к решению: " + f, ""]
    if t.get("source"):
        body += ["\\bigskip\\noindent{\\small Источник: " + _tex_escape_text(str(t["source"])) + "}"]
    body += ["\\end{document}", ""]
    return "\n".join(body)


def _task_txt(t: dict) -> str:
    out = ["%s %s — %s%s — %s класс — задача %s" % (
        t["olymp"], t["year"], t["round"], (" — день %s" % t["day"]) if t.get("day") else "", t["grade"], t["num"]),
        "", "УСЛОВИЕ", t["text"].strip(), ""]
    if t.get("answer"):
        out += ["ОТВЕТ", str(t["answer"]).strip(), ""]
    if t.get("solution"):
        out += ["РЕШЕНИЕ", t["solution"].strip(), ""]
    if t.get("source"):
        out += ["Источник: " + str(t["source"])]
    return "\n".join(out) + "\n"


def _public_task(t: dict) -> dict:
    keys = ("uid", "olymp", "year", "round", "day", "grade", "num", "text", "answer", "solution",
            "status", "source", "fig_statement", "fig_solution")
    return {k: t.get(k) for k in keys}


def _download(content: str, filename: str, mime: str) -> Response:
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", filename)
    resp = Response(content, mimetype=mime + "; charset=utf-8")
    resp.headers["Content-Disposition"] = "attachment; filename=%s" % safe
    return resp

# ----------------------------------------------------------------------------
# Страницы
# ----------------------------------------------------------------------------

@olymp_catalog_bp.route("/")
@catalog_access_required
def index():
    meta = _load("_index") or []
    total = sum(m["count"] for m in meta)
    with_figs = sum(m["with_figs"] for m in meta)
    return render_template("olymp_catalog/index.html", meta=meta, total=total, with_figs=with_figs,
                           tutor_model=TUTOR_MODEL)


@olymp_catalog_bp.route("/<slug>")
@catalog_access_required
def olympiad(slug):
    if not re.fullmatch(r"[a-z0-9\-]+", slug):
        abort(404)
    all_tasks = _load(slug)
    if all_tasks is None:
        abort(404)
    meta = next((m for m in (_load("_index") or []) if m["slug"] == slug), None)
    q = (request.args.get("q") or "").strip()
    year = (request.args.get("year") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    tasks = _filter_tasks(all_tasks, q.lower(), year, grade)
    grades = sorted({str(t["grade"]) for t in all_tasks}, key=_grade_key)
    years_all = sorted({t["year"] for t in all_tasks}, reverse=True)
    return render_template("olymp_catalog/olympiad.html", slug=slug, meta=meta, years=_group(tasks),
                           count=len(tasks), total=len(all_tasks), q=q, year=year, grade=grade,
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
    prep = _PREP_CACHE.get(t["uid"])
    return render_template("olymp_catalog/task.html", slug=slug, t=t, labels=STATUS_LABEL,
                           prev_t=prev_t, next_t=next_t, tutor_model=TUTOR_MODEL,
                           prep_ready=bool(prep and time.time() - prep["ts"] < _PREP_TTL))


@olymp_catalog_bp.route("/<slug>/<uid>/export/<fmt>")
@catalog_access_required
def export_task(slug, uid, fmt):
    t = _find_task(slug, uid)
    if not t:
        abort(404)
    base = "%s_%s_%s_g%s_n%s" % (slug, t["year"], re.sub(r"\W", "", str(t["round"]))[:12], t["grade"], t["num"])
    if fmt == "md":
        return _download(_task_md(t, slug, with_solution=request.args.get("sol", "1") != "0"), base + ".md", "text/markdown")
    if fmt == "tex":
        return _download(_task_tex(t), base + ".tex", "application/x-tex")
    if fmt == "txt":
        return _download(_task_txt(t), base + ".txt", "text/plain")
    if fmt == "json":
        return _download(json.dumps(_public_task(t), ensure_ascii=False, indent=2), base + ".json", "application/json")
    abort(404)


@olymp_catalog_bp.route("/<slug>/export/<fmt>")
@catalog_access_required
def export_olympiad(slug, fmt):
    if not re.fullmatch(r"[a-z0-9\-]+", slug):
        abort(404)
    all_tasks = _load(slug)
    if all_tasks is None:
        abort(404)
    meta = next((m for m in (_load("_index") or []) if m["slug"] == slug), None)
    q = (request.args.get("q") or "").strip().lower()
    year = (request.args.get("year") or "").strip()
    grade = (request.args.get("grade") or "").strip()
    tasks = _filter_tasks(all_tasks, q, year, grade)
    suffix = "".join(["_%s" % year if year else "", "_g%s" % grade if grade else ""])
    if fmt == "json":
        return _download(json.dumps([_public_task(t) for t in tasks], ensure_ascii=False, indent=2),
                         "%s%s.json" % (slug, suffix), "application/json")
    if fmt == "md":
        name = meta["name"] if meta else slug
        out = ["# %s" % name, "", "Задач: %d. Экспорт из FORMYLA.net · %s" % (len(tasks), time.strftime("%Y-%m-%d")), ""]
        with_sol = request.args.get("sol", "1") != "0"
        for y in _group(tasks):
            out += ["", "# %s год" % y["year"], ""]
            for s in y["sections"]:
                out += ["", "## %s%s" % (s["round"], (" — день %s" % s["day"]) if s["day"] else ""), ""]
                for g, ts in s["grades"]:
                    out += ["", "### %s класс" % g, ""]
                    for t in ts:
                        out.append(_task_md(t, slug, with_solution=with_sol).replace("## ", "#### ", 1))
                        out.append("---")
        return _download("\n".join(out), "%s%s.md" % (slug, suffix), "text/markdown")
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
        res = _get_or_prepare(t, force=bool(data.get("force")))
    except Exception as exc:  # noqa: BLE001
        logger.exception("[olymp_tutor] prepare failed: %s", exc)
        return jsonify(ok=False, error="model_error", detail=str(exc)[:300]), 502
    return jsonify(ok=True, ready=True, cached=res["cached"], brief=res["brief"], secs=res.get("secs"),
                   model=TUTOR_MODEL, usage=res.get("usage"))


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
        prep = _get_or_prepare(t)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[olymp_tutor] prepare inside chat failed: %s", exc)
        prep = {"brief": "(конспект подготовки недоступен — разбирай задачу по ходу ответа, но отвечай уверенно)"}
    system = (SYSTEM_PROMPT + "\n\n=== ЗАДАЧА ===\n" + _task_context(t)
              + "\n\n=== ТВОЙ КОНСПЕКТ ПОДГОТОВКИ (ты уже это проанализировал) ===\n" + prep["brief"])
    messages = [{"role": "system", "content": system}] + clean
    try:
        text, usage = _call_model(messages, thinking=TUTOR_THINKING, temperature=0.3)
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
    except Exception:  # noqa: BLE001
        pass
    return resp


def install_olymp_catalog(app) -> None:
    if getattr(app, "_olymp_catalog_installed", False):
        return
    app._olymp_catalog_installed = True
    if "olymp_catalog" not in app.blueprints:
        app.register_blueprint(olymp_catalog_bp)
    if os.environ.get("OLYMP_CATALOG_NAV", "1") != "0":
        app.after_request(_inject_nav)
    logger.info("[BP] olymp_catalog_bp registered (%s, tutor=%s)", URL_PREFIX, TUTOR_MODEL)
    print("[BP] olymp_catalog_bp registered (%s, tutor=%s)" % (URL_PREFIX, TUTOR_MODEL))
