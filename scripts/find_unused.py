#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FORMYLA: анализ неиспользуемых файлов.

Строит граф импортов от точек входа и печатает:
  1) недостижимые .py файлы (не импортируются из точек входа ни напрямую, ни транзитивно);
  2) шаблоны templates/, не вызываемые через render_template().

Запуск (из корня репозитория):
    python scripts/find_unused.py

Только чтение — ничего не изменяет.
"""
import ast
import os
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = ["app.py", "main.py", "wsgi.py", "run.py", "server.py"]
IGNORE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env", "node_modules",
    ".idea", ".vscode", "instance", "figures_archive", "_archive",
    "migrations", "scripts", "docs",
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
        p = path[: -len("/__init__.py")].replace("/", ".")
        return p or path
    return path[:-3].replace("/", ".")


def imports_of(path):
    res = set()
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
    except Exception:
        return res
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                res.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # относительный импорт
                parts = mod_of(path).split(".")
                if node.level - 1 < len(parts):
                    base = ".".join(parts[: -(node.level - 1)] if node.level > 1 else parts)
                else:
                    base = ""
                if node.module:
                    res.add((base + "." + node.module).lstrip("."))
                else:
                    res.add(base)
            elif node.module:
                res.add(node.module)
    return res


def build_graph():
    files = py_files()
    mod2file = {mod_of(f): f for f in files}
    graph = {}
    for f in files:
        graph[f] = set()
        for m in imports_of(f):
            if m in mod2file:
                graph[f].add(mod2file[m])
    return files, graph, mod2file


def reachable():
    files, graph, _ = build_graph()
    seen = set()
    q = deque()
    for e in ENTRY:
        if e in files:
            q.append(e)
            seen.add(e)
    while q:
        cur = q.popleft()
        for nxt in graph.get(cur, ()):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return files, seen


def templates_used():
    used = set()
    for f in py_files():
        try:
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if fn == "render_template" and node.args:
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        used.add("templates/" + a0.value)
    return used


def main():
    files, seen = reachable()
    unused_py = sorted(f for f in files if f not in seen)
    print("=== НЕДОСТИЖИМЫЕ .py (не импортируются из точек входа) ===")
    for f in unused_py:
        print(f)
    print("\nВсего .py: %d | недостижимых: %d" % (len(files), len(unused_py)))

    used = templates_used()
    tpl_files = []
    tdir = os.path.join(ROOT, "templates")
    if os.path.isdir(tdir):
        for dp, dns, fns in os.walk(tdir):
            for fn in fns:
                tpl_files.append(
                    os.path.relpath(os.path.join(dp, fn), ROOT).replace(os.sep, "/")
                )
    unused_tpl = sorted(t for t in tpl_files if t not in used)
    print("\n=== ШАБЛОНЫ без render_template() ===")
    for t in unused_tpl:
        print(t)
    print("\nВсего шаблонов: %d | без вызова: %d" % (len(tpl_files), len(unused_tpl)))


if __name__ == "__main__":
    main()
