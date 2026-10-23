# -*- coding: utf-8 -*-
"""Отчёт о дырах в нумерации задач каталога олимпиад (markdown в stdout).

    python scripts/olymp_catalog_gaps.py              # все олимпиады
    python scripts/olymp_catalog_gaps.py phystech     # одна или несколько (slug)
    python scripts/olymp_catalog_gaps.py > reports/olymp_catalog_gaps.md

Не импортирует Flask и пакет routes — грузит routes/olymp_catalog_gaps.py напрямую.
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "olymp_catalog")


def _load_module():
    path = os.path.join(ROOT, "routes", "olymp_catalog_gaps.py")
    spec = importlib.util.spec_from_file_location("olymp_catalog_gaps", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    mod = _load_module()
    with open(os.path.join(DATA, "_index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    only = set(argv)
    summaries = []
    for m in index:
        if only and m["slug"] not in only:
            continue
        path = os.path.join(DATA, m["slug"] + ".json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            summaries.append(mod.summarize(m["slug"], m["name"], json.load(fh)))
    sys.stdout.write(mod.report_md(summaries))


if __name__ == "__main__":
    main(sys.argv[1:])
