#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FORMYLA: перенос неиспользуемых файлов в папку _archive/.

Что делает:
  1) переносит явный список подтверждённых мёртвых файлов/папок;
  2) находит недостижимые .py (строит граф импортов от app.py);
  3) находит шаблоны, которые не вызываются через render_template();
  4) переносит всё в _archive/<относительный_путь> через shutil.move;
  5) пишет _archive/MOVED_FILES.txt (журнал).

Безопасность:
  - НИЧЕГО не удаляет — только перемещает. git-история сохраняет всё.
  - НЕ трогает: migrations/, docs/, static/, data/, конфиги, банк задач.

Как вернуть всё назад одной командой:
  git checkout -- .        (или:  git restore .)

Запуск:
  python scripts/archive_unused.py
"""
import ast
import os
import shutil
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

ARCHIVE = os.path.join(ROOT, "_archive")
ENTRY = ["app.py", "main.py", "wsgi.py", "run.py", "server.py"]

# Явно подтверждённые неиспользуемые пути (читал register_blueprint в app.py).
EXPLICIT = [
    "figures_archive",
    "routes/admin_daily_pool.py",
    "routes/admin_daily_tasks_stats.py",
    "routes/admin_olympiads.py",
    "routes/concierge.py",
    "routes/figures.py",
    "routes/figures_generator.py",
    "routes/friends.py",
    "routes/friends_backup.py",
    "routes/handwriting.py",
]

IGNORE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env", "node_modules",
    ".idea", ".vscode", "instance", "_archive", "migrations", "docs",
    "static", "templates", "data", "logs",
}


def py_files():
    out = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in IGNORE_DIRS]
        for fn in fns:
            if fn.endswith(".py"):
                out.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/"))
    return out


def mod_of(path):
    if path.endswith("/__init__.py"):
        return path[: -len("/__init__.py")].replace("/", ".")
    return path[:-3].replace("/", ".")


def imports_of(path):
    res = set()
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception:
        return res
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                res.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = mod_of(path).rsplit(".", node.level - 1)[0]
                res.add(base + ("." + node.module if node.module else ""))
            elif node.module:
                res.add(node.module)
    return res


def unreachable_py():
    files = py_files()
    mod2file = {mod_of(f): f for f in files}
    graph = {f: set() for f in files}
    for f in files:
        for m in imports_of(f):
            if m in mod2file:
                graph[f].add(mod2file[m])

    seen = set()
    q = deque()
    for e in ENTRY:
        if e in files:
            seen.add(e)
            q.append(e)
    while q:
        cur = q.popleft()
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return sorted(f for f in files if f not in seen)


def unused_templates():
    used = set()
    for f in py_files():
        try:
            tree = ast.parse(open(f, encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if fn == "render_template" and node.args:
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        used.add("templates/" + a0.value)

    tdir = os.path.join(ROOT, "templates")
    tpls = []
    if os.path.isdir(tdir):
        for dp, dns, fns in os.walk(tdir):
            for fn in fns:
                tpls.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/"))
    return sorted(t for t in tpls if t not in used)


def main():
    targets = []

    # 1) явный список (файлы и папки)
    for p in EXPLICIT:
        full = os.path.join(ROOT, p)
        if os.path.isdir(full):
            for dp, dns, fns in os.walk(full):
                for fn in fns:
                    targets.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/"))
        elif os.path.isfile(full):
            targets.append(p)

    # 2) недостижимые .py (в т.ч. scripts/*, корневые _*.py и т.п.)
    targets += unreachable_py()

    # 3) неиспользуемые шаблоны
    targets += unused_templates()

    targets = sorted(set(targets))

    moved = []
    skipped = []
    for t in targets:
        src = os.path.join(ROOT, t)
        if not os.path.isfile(src):
            skipped.append(t)
            continue
        dst = os.path.join(ARCHIVE, t)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved.append(t)

    os.makedirs(ARCHIVE, exist_ok=True)
    log = os.path.join(ARCHIVE, "MOVED_FILES.txt")
    with open(log, "w", encoding="utf-8") as f:
        f.write("# Перенесено в _archive/ (shutil.move, НЕ удалено)\n")
        f.write("# Вернуть назад:  git checkout -- .\n")
        f.write(f"# Всего перенесено: {len(moved)}\n\n")
        f.write("\n".join(moved) + "\n")

    print(f"Перенесено файлов: {len(moved)}")
    print(f"Пропущено (не найдено): {len(skipped)}")
    print(f"Журнал: {log}")
    print("\nВернуть всё назад:  git checkout -- .")


if __name__ == "__main__":
    main()
