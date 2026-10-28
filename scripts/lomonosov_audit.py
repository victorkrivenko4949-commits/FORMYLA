# -*- coding: utf-8 -*-
"""
lomonosov_audit.py — полная проработка каталога олимпиады «Ломоносов»
(data/olymp_catalog/lomonosov.json).

  1. LaTeX: нормализация + починка типовых поломок, проверка КАЖДОЙ задачи,
     отчёт «было/стало» по uid.
  2. Дыры: (а) варианты год×этап×класс, которых нет совсем (официальная сетка);
     (б) варианты короче нормы (отбор = 10 задач, финал = 7–8);
     (в) пропуски номеров внутри варианта (поле `num`, как в routes/olymp_catalog_gaps.py).
  3. Окончательная сверка: повторный прогон детекторов после починки,
     сводка до/после, список задач, оставшихся «красными».

Запуск:
  python scripts/lomonosov_audit.py                   # dry-run, только отчёты
  python scripts/lomonosov_audit.py --write           # записать исправленный JSON
  python scripts/lomonosov_audit.py --year-mode season_start

Отчёты: reports/lomonosov_audit.md, reports/lomonosov_audit_tasks.csv,
        reports/lomonosov_audit_diff.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "data", "olymp_catalog", "lomonosov.json")
REPORTS = os.path.join(ROOT, "reports")
SLUG = "lomonosov"

sys.path.insert(0, HERE)
try:
    import olymp_fix_rules as R
except Exception:  # автономный режим
    R = None

# Официальная сетка (год = учебный год по ОКОНЧАНИЮ: 2025 = сезон 2024/25).
# Источники: olymp.msu.ru «Задания прошлых лет», mathus.ru/olymp/lomonosov.php.
#   5–6 кл.: с 2016; 7–8 и 9 кл.: с 2011; 10 и 11 раздельно: 2020, 2022–2026;
#   объединённый 10–11: 2005–2019, 2021. Отбор онлайн (10 задач) — с сезона 2010/11.
OFFICIAL_GRID = {
    5: range(2016, 2027), 6: range(2016, 2027),
    7: range(2011, 2027), 8: range(2011, 2027), 9: range(2011, 2027),
    10: [2020] + list(range(2022, 2027)), 11: [2020] + list(range(2022, 2027)),
    "10-11": list(range(2005, 2020)) + [2021],
}
EXPECTED_LEN = {"qual": 10, "final": 8}
SOFT_MIN = {"qual": 10, "final": 7}
ROUND_TITLE = {"qual": "Отборочный этап", "final": "Заключительный этап"}
_NUM_RE = re.compile(r"\d+")


def normalize_unicode(text: str) -> str:
    if R is not None:
        return R.normalize_unicode_math(text)
    if not text:
        return text
    text = text.replace("\u2212", "-")
    text = re.sub(r"[\uE000-\uF8FF\uFFFD\uFFFF\uFEFF]", "", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def convert_dollars(text: str) -> str:
    if R is not None:
        return R.convert_dollar_delims(text)
    if "$" not in text:
        return text
    text = re.sub(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", lambda m: "\\[" + m.group(1).strip() + "\\]", text, flags=re.S)
    return re.sub(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$", lambda m: "\\(" + m.group(1).strip() + "\\)", text)


def canon_round(name: str) -> str | None:
    if R is not None:
        return R.canon_round_key(name or "", SLUG)
    n = (name or "").lower()
    if re.search(r"закл|финал|2\s*тур|второй|final", n):
        return "final"
    if re.search(r"отбор|заоч|1\s*тур|первый|qual", n):
        return "qual"
    return None


def norm_grade(g):
    """7 -> 7; '7' -> 7; '10-11'/'10–11' -> '10-11'; прочее -> None."""
    if isinstance(g, int):
        return g
    if isinstance(g, str):
        s = g.strip().replace("–", "-").replace("—", "-").replace(" ", "")
        if s.isdigit():
            return int(s)
        if re.fullmatch(r"\d{1,2}-\d{1,2}", s):
            return s
    return None


def task_num(rec: dict):
    """Номер задачи: поле `num` («3», «№3», 3), запасные — `number`, `n`."""
    for key in ("num", "number", "n"):
        v = rec.get(key)
        if v is None or v == "":
            continue
        m = _NUM_RE.search(str(v))
        if m:
            return int(m.group())
    return None


# ---------------------------------------------------------------- 1. LaTeX
MATH_SEG_RE = re.compile(r"(\\\((?:[^\\]|\\(?!\\))*?\\\)|\\\[[\s\S]*?\\\])")
LOST_BACKSLASH = [
    "frac", "sqrt", "cdot", "cdots", "ldots", "dots", "leq", "geq", "neq", "le", "ge", "ne",
    "infty", "pi", "alpha", "beta", "gamma", "delta", "varphi", "phi", "lambda", "mu",
    "angle", "triangle", "parallel", "perp", "sin", "cos", "tan", "cot", "log", "ln", "lg",
    "arcsin", "arccos", "arctan", "sum", "prod", "int", "lim", "max", "min", "pm", "mp",
    "times", "div", "equiv", "approx", "Rightarrow", "Leftrightarrow", "in", "notin",
    "subset", "cup", "cap", "emptyset", "forall", "exists", "binom", "overline", "underline",
    "left", "right", "text", "mathbb", "mathrm", "operatorname", "quad", "qquad", "cfrac", "dfrac",
]
_LOST_RE = re.compile(r"(?<![\\A-Za-z])(" + "|".join(sorted(LOST_BACKSLASH, key=len, reverse=True)) + r")(?=[\s{(\[0-9]|$)")
UNICODE_IN_MATH = {
    "≤": r"\le ", "≥": r"\ge ", "⩽": r"\le ", "⩾": r"\ge ", "≠": r"\ne ", "×": r"\times ", "⋅": r"\cdot ", "·": r"\cdot ",
    "∞": r"\infty ", "±": r"\pm ", "∓": r"\mp ", "∈": r"\in ", "∉": r"\notin ", "∠": r"\angle ",
    "△": r"\triangle ", "∥": r"\parallel ", "⊥": r"\perp ", "≈": r"\approx ", "≡": r"\equiv ",
    "→": r"\to ", "⇒": r"\Rightarrow ", "⇔": r"\Leftrightarrow ", "π": r"\pi ", "α": r"\alpha ",
    "β": r"\beta ", "γ": r"\gamma ", "φ": r"\varphi ", "λ": r"\lambda ", "°": r"^\circ ", "◦": r"^\circ ",
    "…": r"\ldots ", "∅": r"\varnothing ", "√": r"\sqrt ", "−": "-", "–": "-", "—": "-",
}
RAW_SYMS = "≤≥⩽⩾≠×⋅∞±∈∉∠√"
_TOK = r"A-Za-z0-9()\[\]{}+\-*/=^_.,|!<>" + RAW_SYMS + "·°◦…"
RAW_MATH_OUTSIDE_RE = re.compile(r"(?<![\\\w])([" + _TOK + r"]*[" + RAW_SYMS + r"][" + _TOK + r"]*)")
TRIG_RU_RE = re.compile(r"(?<![\\A-Za-z])(tg|ctg|arctg|arcctg)(?=[\s(\^0-9a-zA-Z\\])")
_LOST_OUTSIDE_RE = re.compile(r"(?<![\\A-Za-zА-Яа-яЁё])(frac|sqrt|cdot|cdots|ldots|leq|geq|neq|infty|dfrac|binom)(?=[\s{(\d])")
_STOP = re.compile(r"[А-Яа-яЁё\n«»]|\.\s|,\s(?=[А-Яа-яЁё])")


def _fix_math_inner(body: str) -> str:
    s = body
    for k, v in UNICODE_IN_MATH.items():
        s = s.replace(k, v)
    s = _LOST_RE.sub(lambda m: "\\" + m.group(1), s)
    s = TRIG_RU_RE.sub(lambda m: "\\operatorname{" + m.group(1) + "}", s)
    s = re.sub(r"\\([cd]?frac)\s*([0-9A-Za-z])\s*([0-9A-Za-z])(?![A-Za-z0-9])", r"\\\1{\2}{\3}", s)
    s = re.sub(r"\\([cd]?frac)\s*\{([^{}]*)\}\s*([0-9A-Za-z])(?![A-Za-z0-9{])", r"\\\1{\2}{\3}", s)
    s = re.sub(r"\\([cd]?frac)\s*([0-9A-Za-z])\s*\{", r"\\\1{\2}{", s)
    s = re.sub(r"\\sqrt\s+([0-9]+(?:[.,][0-9]+)?|[A-Za-z])(?![A-Za-z0-9])", r"\\sqrt{\1}", s)
    s = re.sub(r"\\sqrt\s*\(([^()]*)\)", r"\\sqrt{\1}", s)
    s = re.sub(r"([\^_])\s+(?=[{(\w\\])", r"\1", s)
    s = re.sub(r"(\\[A-Za-z]+)\s+(?=[\^_])", r"\1", s)
    s = re.sub(r"([\^_])(\d{2,}|[A-Za-z]\d+)(?![\w{])", r"\1{\2}", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if s.count("\\left") != s.count("\\right"):
        s = s.replace("\\left", "").replace("\\right", "")
    opens, closes = s.count("{") - s.count("\\{"), s.count("}") - s.count("\\}")
    if opens > closes:
        s += "}" * (opens - closes)
    return s


def _unnest_delims(text: str) -> str:
    text = re.sub(r"\\\(\s*\\\(", lambda m: "\\(", text)
    text = re.sub(r"\\\)\s*\\\)", lambda m: "\\)", text)
    text = re.sub(r"\\\)\s*\\\(", " ", text)
    text = re.sub(r"\\\(\s*\\\)", "", text)
    text = re.sub(r"\\\[\s*\\\]", "", text)
    out, depth, i = [], 0, 0
    while i < len(text):
        two = text[i:i + 2]
        if two == "\\(":
            if depth == 0:
                out.append(two)
            depth += 1
            i += 2
            continue
        if two == "\\)":
            depth = max(0, depth - 1)
            if depth == 0:
                out.append(two)
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _wrap_frag(frag: str) -> str:
    """Обернуть фрагмент в \\( \\), вынеся наружу хвостовую пунктуацию."""
    core = frag.rstrip(".,;:!?")
    tail = frag[len(core):]
    if not core.strip():
        return frag
    return "\\(" + _fix_math_inner(core) + "\\)" + tail


def _wrap_lost_commands(seg: str) -> str:
    # frac{1}{2}x^2 вне формулы -> оборачиваем в inline-формулу
    if not _LOST_OUTSIDE_RE.search(seg):
        return seg
    out, i = [], 0
    for m in _LOST_OUTSIDE_RE.finditer(seg):
        if m.start() < i:
            continue
        lo = m.start()
        while lo > i and not _STOP.match(seg, lo - 1):
            lo -= 1
        hi = m.end()
        while hi < len(seg) and not _STOP.match(seg, hi):
            hi += 1
        chunk = seg[lo:hi]
        pre = chunk[:len(chunk) - len(chunk.lstrip())]
        post = chunk[len(chunk.rstrip()):]
        out.append(seg[i:lo] + pre + _wrap_frag(chunk.strip()) + post)
        i = hi
    out.append(seg[i:])
    return "".join(out)


def _wrap_raw_math(seg: str) -> str:
    seg = _wrap_lost_commands(seg)
    if not seg or not re.search("[" + RAW_SYMS + "]", seg):
        return seg
    return RAW_MATH_OUTSIDE_RE.sub(lambda m: _wrap_frag(m.group(1)), seg)


def fix_markdown(text: str) -> str:
    if not text or ("*" not in text and "#" not in text):
        return text or ""
    t = re.sub(r"\*\*\s*(?:Решение|РЕШЕНИЕ|Ответ|ОТВЕТ)\s*[.:]?\s*\*\*\s*[.:]?\s*", "", text)
    t = re.sub(r"\*\*([^*\n]{1,200}?)\*\*", r"\1", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    return t.strip()


def fix_latex(text: str) -> str:
    if not text:
        return text or ""
    t = normalize_unicode(fix_markdown(text))
    t = t.replace("\\\\(", "\\(").replace("\\\\)", "\\)")
    t = re.sub(r"\\begin\{(align\*?|gather\*?|eqnarray\*?)\}", lambda m: "\\[\\begin{aligned}", t)
    t = re.sub(r"\\end\{(align\*?|gather\*?|eqnarray\*?)\}", lambda m: "\\end{aligned}\\]", t)
    t = convert_dollars(t)
    # √ 6, √ x -> √{6}: чтобы подкоренное не оторвалось от знака
    t = re.sub(r"√\s*([0-9]+(?:[.,][0-9]+)?|[A-Za-z])(?![\w.])", r"√{\1}", t)
    # разорванные функции из PDF: co \(s^2 x\) -> \(\cos^2 x\), si \(n x\) -> \(\sin x\)
    t = re.sub(r"\bco\s*\\\(\s*s", lambda m: "\\(\\cos ", t)
    t = re.sub(r"\b(?:si|s)\s*\\\(\s*(?:n|in)", lambda m: "\\(\\sin ", t)
    t = re.sub(r"\bt\s*\\\(\s*g", lambda m: "\\(\\operatorname{tg}", t)
    if t.count("$") == 1:
        t = t.replace("$", "")
    t = _unnest_delims(t)
    if t.count("\\(") > t.count("\\)"):
        t += "\\)" * (t.count("\\(") - t.count("\\)"))
    elif t.count("\\)") > t.count("\\("):
        t = re.sub(r"\\\)", "", t, count=t.count("\\)") - t.count("\\("))
    if t.count("\\[") > t.count("\\]"):
        t += "\\]" * (t.count("\\[") - t.count("\\]"))
    parts, pos = [], 0
    for m in MATH_SEG_RE.finditer(t):
        parts.append(_wrap_raw_math(t[pos:m.start()]))
        seg = m.group(0)
        parts.append(seg[:2] + _fix_math_inner(seg[2:-2]) + seg[-2:])
        pos = m.end()
    parts.append(_wrap_raw_math(t[pos:]))
    t = "".join(parts)
    # соседние формулы: \(a\) = \(b\) -> \(a = b\);  \(a\) \(b\) -> \(a b\)
    t = re.sub(r"\\\)\s*([+\-=<>]|\\(?:le|ge|ne|cdot|times|pm)\b)\s*\\\(", r" \1 ", t)
    t = re.sub(r"\\\)\s+\\\(", " ", t)
    t = re.sub(r"\\\)(?=[A-Za-zА-Яа-яЁё0-9])", lambda m: "\\) ", t)
    t = re.sub(r"(?<=[A-Za-zА-Яа-яЁё0-9])\\\(", lambda m: " \\(", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]+\n", "\n", t).strip()
    return t


# ------------------------------------------------------- 1b. проверки задачи
def latex_issues(text: str) -> list[str]:
    out = []
    if not text:
        return out
    if "$" in text:
        out.append("остался $")
    if text.count("\\(") != text.count("\\)"):
        out.append("небаланс \\( \\)")
    if text.count("\\[") != text.count("\\]"):
        out.append("небаланс \\[ \\]")
    for seg in MATH_SEG_RE.findall(text):
        body = seg[2:-2]
        if body.count("{") - body.count("\\{") != body.count("}") - body.count("\\}"):
            out.append("небаланс {} в формуле")
            break
    if re.search(r"\\\(\s*\\\(|\\\)\s*\\\)", text):
        out.append("вложенные \\(")
    if re.search(r"[\uE000-\uF8FF\uFFFD]", text):
        out.append("PUA-символы")
    if any(0x1D400 <= ord(c) <= 0x1D7FF for c in text):
        out.append("math-alphanumerics из PDF")
    if re.search("[" + RAW_SYMS + "]", MATH_SEG_RE.sub(" ", text)):
        out.append("юникод-математика вне формул")
    if re.search(r"(?<![\\A-Za-z])(frac|sqrt|cdot|leq|geq)\s*[{\d]", text):
        out.append("команда без обратного слэша")
    if re.search(r"\bco\s+\\\(|\bs\s*\\\(\s*in", text):
        out.append("разорванная функция (co s / s in)")
    if re.search(r"\\\)\s*[+=\-]\s*\\\(", text):
        out.append("формула разрезана на части")
    return out


def task_issues(rec: dict) -> list[str]:
    issues = []
    text, sol, ans = rec.get("text") or "", rec.get("solution") or "", rec.get("answer") or ""
    issues += ["text: " + i for i in latex_issues(text)]
    issues += ["solution: " + i for i in latex_issues(sol)]
    issues += ["answer: " + i for i in latex_issues(ans)]
    if len(text.strip()) < 40:
        issues.append("условие слишком короткое/пустое")
    elif text.strip()[-1] not in ".?!:;»\"')]":
        issues.append("условие обрывается (нет конечной пунктуации)")
    rk = canon_round(rec.get("round"))
    if rk is None:
        issues.append(f"этап не распознан: {rec.get('round')!r}")
    g = norm_grade(rec.get("grade"))
    if not isinstance(g, int) or not (5 <= g <= 11):
        issues.append(f"класс не точный: {rec.get('grade')!r}")
    n = task_num(rec)
    if n is None or n < 1:
        issues.append(f"номер задачи не задан: {rec.get('num')!r}")
    if not isinstance(rec.get("year"), int):
        issues.append("год не задан")
    if rk == "qual" and not ans.strip():
        issues.append("отбор: нет численного ответа")
    if not ans.strip() and not sol.strip():
        issues.append("нет ни ответа, ни решения")
    if R is not None and R.is_answer_garbage(ans):
        issues.append("мусорный ответ")
    elif R is None and ans.strip() in {"-", "—", "–", "нет", "см. решение"}:
        issues.append("мусорный ответ")
    if len(ans) > 250:
        issues.append("ответ длиннее 250 символов")
    if "**" in sol or "**" in ans:
        issues.append("markdown ** в решении/ответе")
    if re.search(r"(?:^|\n)\s*(Решение|Ответ)\s*[.:]", text):
        issues.append("решение/ответ внутри условия")
    if 0 < len(sol.strip()) < 60:
        issues.append("решение-заглушка (<60 симв.)")
    if re.search(r"(?:см\.?\s*рис|на\s*рисунке)", text, re.I) and not (rec.get("fig_statement") or rec.get("fig_solution")):
        issues.append("упомянут рисунок, файла нет")
    if not (rec.get("source") or "").strip():
        issues.append("нет источника")
    elif R is not None and not R.is_official_url(rec.get("source")):
        issues.append("источник неофициальный")
    if rec.get("status") in ("unresolved", "broken_text", "figure_only"):
        issues.append(f"статус {rec.get('status')}")
    return issues


# --------------------------------------------------------------- 2. дыры
def variant_key(rec: dict, year_mode: str):
    y = rec.get("year")
    if isinstance(y, int) and year_mode == "season_start":
        y += 1
    return (y, canon_round(rec.get("round")) or "?", norm_grade(rec.get("grade")))


def find_gaps(recs: list[dict], year_mode: str) -> dict:
    by_var: dict = defaultdict(list)
    for r in recs:
        by_var[variant_key(r, year_mode)].append(r)
    sort_key = lambda k: (-(k[0] or 0), k[1], str(k[2]))
    numbering = []
    for k in sorted(by_var, key=sort_key):
        items = by_var[k]
        all_nums = [task_num(r) for r in items]
        nums = sorted({n for n in all_nums if n is not None})
        upto = max([EXPECTED_LEN.get(k[1], 0)] + nums)
        missing = [n for n in range(1, upto + 1) if n not in nums]
        dup = sorted(n for n, c in Counter(all_nums).items() if c > 1 and n is not None)
        numbering.append((k, nums, missing, len(items), dup))
    present = set(by_var)
    years_in = {k[0] for k in by_var if isinstance(k[0], int)}
    ymax = max(years_in) if years_in else 0
    absent = []
    for g, years in OFFICIAL_GRID.items():
        for y in years:
            if y > ymax:
                continue
            for rk in ("qual", "final"):
                if rk == "qual" and y < 2011:
                    continue
                if g == "10-11":
                    ok = any((y, rk, gg) in present for gg in (10, 11, "10-11"))
                else:
                    ok = (y, rk, g) in present
                if not ok:
                    absent.append((y, rk, g))
    absent.sort(key=lambda t: (-t[0], t[1], str(t[2])))
    short = [(k, len(v), EXPECTED_LEN[k[1]]) for k, v in by_var.items()
             if k[1] in SOFT_MIN and len(v) < SOFT_MIN[k[1]]]
    short.sort(key=lambda t: sort_key(t[0]))
    return {"by_var": by_var, "numbering": numbering, "absent": absent, "short": short}


def fmt_var(k) -> str:
    y, rk, g = k
    return f"{y}, {ROUND_TITLE.get(rk, rk)}, {g} класс"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--year-mode", choices=["season_end", "season_start"], default="season_end")
    ap.add_argument("--reports", default=REPORTS)
    args = ap.parse_args()

    with open(args.src, encoding="utf-8") as fh:
        data = json.load(fh)
    recs = data if isinstance(data, list) else data.get("tasks") or data.get("items") or []
    os.makedirs(args.reports, exist_ok=True)

    before = {r.get("uid"): task_issues(r) for r in recs}
    diff_rows, changed = [], 0
    for r in recs:
        row = {"uid": r.get("uid"), "changes": {}}
        for f in ("text", "solution", "answer"):
            old = r.get(f) or ""
            new = fix_latex(old)
            if new != old:
                row["changes"][f] = {"before": old, "after": new}
                r[f] = new
        if row["changes"]:
            changed += 1
            diff_rows.append(row)
    after = {r.get("uid"): task_issues(r) for r in recs}
    gaps = find_gaps(recs, args.year_mode)

    def _cat(i):
        return i.split(": ", 1)[1] if i.startswith(("text: ", "solution: ", "answer: ")) else i
    cnt_b = Counter(_cat(i) for v in before.values() for i in v)
    cnt_a = Counter(_cat(i) for v in after.values() for i in v)
    LATEX_WORDS = ("небаланс", "остался $", "юникод", "слэша", "вложен", "PUA", "alphanumerics", "разрезана", "разорванная")
    lx_b = sum(1 for v in before.values() if any(w in i for i in v for w in LATEX_WORDS))
    lx_a = sum(1 for v in after.values() if any(w in i for i in v for w in LATEX_WORDS))
    red = sorted(((r, after[r.get("uid")]) for r in recs if after[r.get("uid")]),
                 key=lambda t: (-len(t[1]), -(t[0].get("year") or 0)))
    diff_by_uid = {d["uid"]: d["changes"] for d in diff_rows}

    if args.write:
        with open(args.src, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(args.reports, "lomonosov_audit_diff.jsonl"), "w", encoding="utf-8") as fh:
        for row in diff_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with open(os.path.join(args.reports, "lomonosov_audit_tasks.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["uid", "year", "round", "grade", "num", "status", "changed_fields", "issues_before", "issues_after"])
        for r in recs:
            u = r.get("uid")
            w.writerow([u, r.get("year"), r.get("round"), r.get("grade"), r.get("num"), r.get("status"),
                        ",".join(diff_by_uid.get(u, {}).keys()), " | ".join(before[u]), " | ".join(after[u])])

    L = [f"# Аудит каталога «Ломоносов» — {datetime.now():%Y-%m-%d %H:%M}\n",
         f"Задач в файле: **{len(recs)}**. Поле `year` = `{args.year_mode}` "
         f"({'2025 = сезон 2024/25' if args.year_mode == 'season_end' else '2025 = сезон 2025/26'}). "
         f"Режим: {'ЗАПИСЬ в lomonosov.json' if args.write else 'dry-run'}.\n",
         "## 0. Что есть в файле (год × этап → задач)\n", "| Год | Отбор | Финал | ? |\n|---|---:|---:|---:|"]
    yrs = Counter(variant_key(r, args.year_mode)[:2] for r in recs)
    for y in sorted({k[0] for k in yrs if isinstance(k[0], int)}, reverse=True):
        L.append(f"| {y} | {yrs.get((y, 'qual'), 0)} | {yrs.get((y, 'final'), 0)} | {yrs.get((y, '?'), 0)} |")
    L += ["", "## 1. LaTeX — починка и проверка каждой задачи\n",
          f"- Изменено задач: **{changed}** (полный diff — `reports/lomonosov_audit_diff.jsonl`).",
          f"- Задач с LaTeX-проблемами: было {lx_b} → стало {lx_a}.",
          f"- Задач без замечаний после прогона: {len(recs) - len(red)} из {len(recs)}.\n",
          "| Проблема | Было | Стало |\n|---|---:|---:|"]
    for key in sorted(set(cnt_b) | set(cnt_a), key=lambda k: -cnt_b.get(k, 0)):
        L.append(f"| {key} | {cnt_b.get(key, 0)} | {cnt_a.get(key, 0)} |")
    L += ["", "### Примеры исправлений (первые 25)\n"]
    for d in diff_rows[:25]:
        for f, ch in d["changes"].items():
            b, a = ch["before"].replace("\n", " ")[:160], ch["after"].replace("\n", " ")[:160]
            L.append(f"- `{d['uid']}` **{f}**: `{b}` → `{a}`")
    L += ["", "## 2. Дыры\n", f"### 2а. Варианты, которых нет совсем (официальная сетка): {len(gaps['absent'])}\n"]
    byy = defaultdict(list)
    for y, rk, g in gaps["absent"]:
        byy[y].append(f"{'отбор' if rk == 'qual' else 'финал'} {g} кл.")
    for y in sorted(byy, reverse=True):
        L.append(f"- **{y}**: " + ", ".join(byy[y]))
    L += ["", f"### 2б. Варианты короче нормы (отбор 10, финал 7–8): {len(gaps['short'])}\n"]
    L += [f"- {fmt_var(k)}: есть {n}, норма {exp}" for k, n, exp in gaps["short"]]
    L += ["", "### 2в. Пропуски номеров внутри вариантов\n"]
    tot = 0
    for k, nums, missing, n, dup in gaps["numbering"]:
        if missing or dup:
            tot += len(missing)
            s = f"- {fmt_var(k)}: есть №{', '.join(map(str, nums)) or '—'}; нет №{', '.join(map(str, missing)) or '—'}"
            if dup:
                s += f"; дубли №{', '.join(map(str, dup))}"
            L.append(s)
    L += [f"\nИтого пропущенных номеров: **{tot}**.\n", "## 3. Окончательная сверка — что осталось красным\n",
          f"Задач с замечаниями: **{len(red)}**. Построчно — `reports/lomonosov_audit_tasks.csv`.\n",
          "| uid | Год / этап / класс / № | Замечания |\n|---|---|---|"]
    for r, iss in red[:150]:
        L.append(f"| `{r.get('uid')}` | {r.get('year')} / {r.get('round')} / {r.get('grade')} / {r.get('num')} | {'; '.join(iss)} |")
    if len(red) > 150:
        L.append(f"| … | ещё {len(red) - 150} | см. CSV |")
    hard = [r for r, iss in red if any(x in " ".join(iss) for x in
            ("небаланс", "остался $", "класс не точный", "номер задачи", "этап не распознан", "условие"))]
    L += ["", "### Готовность к снятию карантина\n",
          f"- Блокирующих задач (ломаный LaTeX / нет класса / номера / этапа / обрыв условия): **{len(hard)}**.",
          f"- Вариантов, отсутствующих целиком: **{len(gaps['absent'])}**; коротких: **{len(gaps['short'])}**.",
          "- `lomonosov` можно убирать из `_EXCLUDED_SLUGS` (services/real_probnik.py), когда блокирующих = 0 "
          "и варианты для пробников не короче нормы."]
    with open(os.path.join(args.reports, "lomonosov_audit.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"tasks={len(recs)} changed={changed} latex {lx_b}->{lx_a} red={len(red)} hard={len(hard)} "
          f"absent={len(gaps['absent'])} short={len(gaps['short'])} missing_numbers={tot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
