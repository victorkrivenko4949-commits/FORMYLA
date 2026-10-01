#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FORMYLA: безопасный перенос неиспользуемых файлов в _archive/.

НИЧЕГО не удаляет — использует `git mv` (с fallback на os.rename),
сохраняя структуру папок внутри _archive/. Git-история остаётся страховкой.

Запуск (из корня репозитория, в ветке ai-edits):
    python scripts/archive_unused.py --dry-run   # показать, что будет перенесено
    python scripts/archive_unused.py             # выполнить перенос

Можно откатить:  git checkout main -- .   (или revert коммита)
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(ROOT, "_archive")

# 1) Файлы с 100%-й уверенностью (проверены вручную по app.py)
CONFIRMED_FILES = [
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

# 2) Папки целиком
CONFIRMED_DIRS = [
    "figures_archive",
]

# 3) Корневой мусор — по точным именам (видимые артефакты shell-команд)
ROOT_JUNK = [
    "$null",
    "'2026-08-31",
    "'2026-09-03",
    ".coverage",
    ".migrated",
    "1",
    "20",
    "5",
    "148",
    "Get-ChildItem",
    "Select-String",
    "VICTOR2.0",
    "FORMYLA_AUDIT_FIX_FINAL.py",
]

# 4) Корневой мусор — по префиксу/суффиксу (шаблоны)
ROOT_PATTERNS_PREFIX = [
    "_",           # _*.py, _*.txt, _*.json, _*.html
    "diag_",
    "chk_",
    "dump_",
    "EVIDENCE_",
    "_bak_before_",
    "_6figs",
    "_deliverables",
]
ROOT_PATTERNS_SUFFIX = [
    ".bak",
    ".zip",
    "_FINAL_REPORT.md",
]

# 5) Папки-артефакты в корне
ROOT_JUNK_DIRS = [
    "_6figs",
    "_deliverables",
    "_bak_before_e21",
    "_bak_before_e8e11",
]


def git_mv(src, dst):
    """Переместить через git mv, fallback на os.rename."""
    try:
        subprocess.check_call(["git", "-C", ROOT, "mv", src, dst])
        return True
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        return True
    except Exception as e:
        print(f"  ! Ошибка переноса {src}: {e}")
        return False


def collect():
    """Собрать список (src, dst) для переноса."""
    plan = []

    for f in CONFIRMED_FILES:
        src = os.path.join(ROOT, f)
        if os.path.exists(src):
            plan.append((src, os.path.join(ARCHIVE, f)))

    for d in CONFIRMED_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            plan.append((src, os.path.join(ARCHIVE, d)))

    for d in ROOT_JUNK_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            plan.append((src, os.path.join(ARCHIVE, d)))

    # Корневые файлы
    root_entries = os.listdir(ROOT)
    for name in root_entries:
        src = os.path.join(ROOT, name)
        if not os.path.isfile(src):
            continue
        hit = name in ROOT_JUNK
        if not hit:
            hit = any(name.startswith(p) for p in ROOT_PATTERNS_PREFIX)
        if not hit:
            hit = any(name.endswith(s) for s in ROOT_PATTERNS_SUFFIX)
        if hit:
            plan.append((src, os.path.join(ARCHIVE, name)))

    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="только показать план")
    args = ap.parse_args()

    plan = collect()
    print(f"К переносу: {len(plan)} элементов\n")

    moved = 0
    for src, dst in plan:
        rel = os.path.relpath(src, ROOT)
        print(f"  {'[dry-run] ' if args.dry_run else ''}{rel} -> _archive/")
        if not args.dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if git_mv(src, dst):
                moved += 1

    if args.dry_run:
        print(f"\nЭто режим просмотра. Запусти без --dry-run для переноса.")
    else:
        print(f"\nПеренесено: {moved}. Не забудь закоммитить: git add -A && git commit")


if __name__ == "__main__":
    main()
