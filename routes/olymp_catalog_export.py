# -*- coding: utf-8 -*-
"""OLYMP_CATALOG_V3.4 — экспорт задач каталога: Markdown, LaTeX, текст, JSON."""
from __future__ import annotations

import os
import re

from flask import Response, request, url_for

from routes.olymp_catalog_clean import STATUS_LABEL


def _fig_url(f: str) -> str:
    return request.host_url.rstrip("/") + url_for("olymp_catalog.figure", subpath=f)


def task_md(t: dict, slug: str, with_solution: bool = True) -> str:
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


def tex_escape_text(s: str) -> str:
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


def task_tex(t: dict) -> str:
    title = "%s %s. %s%s. %s класс, задача %s" % (
        t["olymp"], t["year"], t["round"], (", день %s" % t["day"]) if t.get("day") else "", t["grade"], t["num"])
    body = ["\\documentclass[12pt,a4paper]{article}",
            "\\usepackage[utf8]{inputenc}", "\\usepackage[T2A]{fontenc}", "\\usepackage[russian]{babel}",
            "\\usepackage{amsmath,amssymb,amsthm}", "\\usepackage{graphicx}", "\\usepackage[margin=2cm]{geometry}",
            "\\begin{document}", "\\section*{%s}" % tex_escape_text(title), "",
            "\\textbf{Условие.} " + tex_escape_text(t["text"].strip()), ""]
    for f in t.get("fig_statement") or []:
        body += ["% рисунок к условию: " + f, "% \\includegraphics[width=.6\\textwidth]{%s}" % os.path.basename(f), ""]
    if t.get("answer"):
        body += ["\\textbf{Ответ.} " + tex_escape_text(str(t["answer"]).strip()), ""]
    if t.get("solution"):
        body += ["\\textbf{Решение.} " + tex_escape_text(t["solution"].strip()), ""]
        for f in t.get("fig_solution") or []:
            body += ["% рисунок к решению: " + f, ""]
    if t.get("source"):
        body += ["\\bigskip\\noindent{\\small Источник: " + tex_escape_text(str(t["source"])) + "}"]
    body += ["\\end{document}", ""]
    return "\n".join(body)


def task_txt(t: dict) -> str:
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


def public_task(t: dict) -> dict:
    keys = ("uid", "olymp", "year", "round", "day", "grade", "num", "text", "answer", "solution",
            "status", "source", "fig_statement", "fig_solution", "garbled")
    return {k: t.get(k) for k in keys}


def download(content: str, filename: str, mime: str) -> Response:
    safe = re.sub(r"[^A-Za-z0-9._\-]", "_", filename)
    resp = Response(content, mimetype=mime + "; charset=utf-8")
    resp.headers["Content-Disposition"] = "attachment; filename=%s" % safe
    return resp
