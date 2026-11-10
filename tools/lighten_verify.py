#!/usr/bin/env python3
"""Проверка «облегчённых» решений каталога олимпиад (data/olymp_catalog/*.json).

Сравнивает файл с версией в git HEAD и проверяет:
  1) структура: JSON валиден, число задач и порядок uid не изменились;
  2) неприкосновенность: answer, status, text, fig_* и прочие поля, кроме
     solution (и вычисляемых quality_issues/needs_review/fig_missing), не тронуты;
  3) качество solution: решение стало короче (но не выхолощено), нет маркдауна
     (###, **, __, ---), нет хвостов «Критерии оценк…» / «Только ответ — …»;
  4) LaTeX: все формулы \(..\) $..$ \[..\] $$..$$ реально парсятся KaTeX
     (тот же набор macros, что на сайте), парность $ и скобок.

Использование:
  python3 tools/lighten_verify.py data/olymp_catalog/vsosh.json [...]
  python3 tools/lighten_verify.py --all
Выход: код 0 — чисто, 1 — есть ошибки. Подробности в stdout.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data", "olymp_catalog")

BAD_STATUSES = {"removed_by_user", "broken_text", "truncated_text", "figure_only"}
PROTECTED_FIELDS = ("uid", "olymp", "year", "round", "day", "grade", "num", "status",
                    "answer", "source", "text", "geo", "fig_statement", "fig_solution")
MIN_LEN = 60            # решение не короче 60 символов
MIN_RATIO = 0.30        # и не меньше 30% исходной длины
MAX_RATIO = 1.00        # облегчение не должно удлинять решение
# uid'ы, для которых разрешён сознательный фикс поля answer (исправление мусора
# в данных, найденного при облегчении). Передаётся: --allow-answer-fix uid,uid
ANSWER_FIX_ALLOWED = set()
# uid'ы, для которых разрешён сознательный фикс поля text (восстановление
# битого/искажённого условия по официальному источнику). --allow-text-fix uid,uid
TEXT_FIX_ALLOWED = set()
# uid'ы, у которых решение сознательно ЗАМЕНЕНО целиком (старое было от другой
# задачи либо неверно): пропускаем проверки длин, но не проверки контента.
REPLACE_ALLOWED = set()
# uid'ы, для которых разрешена правка метаданных (year/round/day/grade/num) —
# переразбивка задач ММО по сборникам. Ответы и тексты остаются защищены.
META_FIX_ALLOWED = set()
MD_PATTERNS = [(r"#{2,}\s", "markdown-заголовок"), (r"\*\*", "markdown-жирный"),
               (r"(?<!\w)__(?!\w)", "markdown-подчёркивание"),
               (r"(?m)^---+\s*$", "markdown-линия")]
TAIL_PATTERNS = [("Критерии оценк", "хвост с критериями"),
                 ("Только ответ", "хвост «Только ответ»"),
                 ("Ответ.", "— проверяется вручную: не ошибка, просто внимание")]


def load_head(path):
    rel = os.path.relpath(path, ROOT)
    out = subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def katex_check(paths):
    """Возвращает (кол-во ошибок, вывод). Node + katex обязателен."""
    env = dict(os.environ)
    for cand in (os.path.join(ROOT, "node_modules"), os.path.join(os.path.dirname(ROOT), "node_modules")):
        if os.path.isdir(os.path.join(cand, "katex")):
            env["NODE_PATH"] = cand
            break
    out = subprocess.run(["node", os.path.join(HERE, "katex_check.js"), *paths],
                         capture_output=True, text=True, env=env)
    return out.stdout.strip(), out.returncode


def check_file(path):
    errors = []
    new = json.load(open(path, encoding="utf-8"))
    old = load_head(path)
    if old is None:
        return [], 0, 0, ["файл новый в git — сравнение пропущено"]
    if len(new) != len(old):
        errors.append(f"число задач изменилось: {len(old)} -> {len(new)}")
        return errors, 0, 0, []
    old_by_uid = {t.get("uid"): t for t in old}
    changed = shortened = 0
    for t in new:
        uid = t.get("uid", "?")
        o = old_by_uid.get(uid)
        if o is None:
            errors.append(f"{uid[:12]}: новый uid (не было в HEAD)")
            continue
        for f in PROTECTED_FIELDS:
            if t.get(f) != o.get(f):
                if f == "answer" and uid in ANSWER_FIX_ALLOWED:
                    print(f"  [фикс ответа] {uid[:12]}: {o.get('answer')!r} -> {t.get('answer')!r}")
                elif f in ("year","round","day","grade","num") and uid in META_FIX_ALLOWED:
                    pass  # сознательная правка метаданных (переразбивка по годам)
                elif f == "text" and uid in TEXT_FIX_ALLOWED:
                    print(f"  [фикс условия] {uid[:12]}: {len(o.get('text') or '')} -> {len(t.get('text') or '')} симв.")
                else:
                    errors.append(f"{uid[:12]}: изменено поле {f!r} — запрещено")
        ns, os_ = t.get("solution") or "", o.get("solution") or ""
        if ns == os_:
            continue
        changed += 1
        if not ns.strip():
            errors.append(f"{uid[:12]}: решение стало пустым")
            continue
        if o.get("status") in BAD_STATUSES:
            continue  # эти статусы вне скоупа, но изменение всё равно логируем выше
        if len(os_) >= 300 and uid not in REPLACE_ALLOWED:
            if len(ns) > len(os_) * MAX_RATIO:
                errors.append(f"{uid[:12]}: решение не стало короче ({len(os_)} -> {len(ns)})")
            if len(ns) < max(MIN_LEN, len(os_) * MIN_RATIO):
                errors.append(f"{uid[:12]}: решение выхолощено ({len(os_)} -> {len(ns)})")
            else:
                shortened += 1
        for pat, why in MD_PATTERNS:
            if re.search(pat, ns):
                errors.append(f"{uid[:12]}: {why} в решении")
        for pat, why in TAIL_PATTERNS[:2]:
            if pat in ns:
                errors.append(f"{uid[:12]}: {why}")
        if ns.count("\\(") != ns.count("\\)"):
            errors.append(f"{uid[:12]}: непарные \\( \\)")
        if ns.count("{") != ns.count("}"):
            errors.append(f"{uid[:12]}: непарные фигурные скобки")
    return errors, changed, shortened, []


def main():
    args = sys.argv[1:]
    allow_answer_fix = []
    allow_text_fix = []
    allow_replace = []
    allow_meta = []
    while args and args[0].startswith("--"):
        if args[0] == "--allow-answer-fix":
            allow_answer_fix = [u.strip() for u in args[1].split(",") if u.strip()]
            args = args[2:]
        elif args[0] == "--allow-meta-fix":
            allow_meta = [u.strip() for u in args[1].split(",") if u.strip()]
            args = args[2:]
        elif args[0] == "--allow-replace":
            allow_replace = [u.strip() for u in args[1].split(",") if u.strip()]
            args = args[2:]
        elif args[0] == "--allow-text-fix":
            allow_text_fix = [u.strip() for u in args[1].split(",") if u.strip()]
            args = args[2:]
        elif args[0] == "--all":
            args = ["--all"]
            break
        else:
            break
    ANSWER_FIX_ALLOWED.clear()
    ANSWER_FIX_ALLOWED.update(allow_answer_fix)
    TEXT_FIX_ALLOWED.clear()
    TEXT_FIX_ALLOWED.update(allow_text_fix)
    REPLACE_ALLOWED.clear()
    REPLACE_ALLOWED.update(allow_replace)
    META_FIX_ALLOWED.clear()
    META_FIX_ALLOWED.update(allow_meta)
    if args == ["--all"]:
        args = sorted(os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR)
                      if f.endswith(".json") and not any(k in f for k in
                      ("log", "_index", "survivors", "leftovers", "collision")))
    total_errors = []
    for path in args:
        errs, changed, shortened, notes = check_file(path)
        rel = os.path.relpath(path, ROOT)
        status = "OK" if not errs else f"{len(errs)} ОШИБОК"
        print(f"{rel}: изменено {changed}, короче стало {shortened}, {status}")
        total_errors += [f"{rel}: {e}" for e in errs]
    katex_out, _ = katex_check(args)
    print("--- KaTeX ---")
    print(katex_out)
    if total_errors:
        print("--- Детали ---")
        for e in total_errors[:80]:
            print(" ", e)
        if len(total_errors) > 80:
            print(f"  ... и ещё {len(total_errors) - 80}")
        sys.exit(1)
    print("ВСЁ ЧИСТО" if "errors: 0" in katex_out else "ЕСТЬ ОШИБКИ KATEX")
    sys.exit(0 if "errors: 0" in katex_out else 1)


if __name__ == "__main__":
    main()
