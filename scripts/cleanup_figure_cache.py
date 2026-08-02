#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/cleanup_figure_cache.py — Чистка осиротевших SVG-файлов в кеше чертежей.

Удаляет файлы static/figures/cache/*.svg, чей хеш не соответствует
ни одному figure_json в БД (adaptive_tasks).

Запуск (без флага --dry-run — реальное удаление):
    python scripts/cleanup_figure_cache.py
    python scripts/cleanup_figure_cache.py --dry-run   # только показать

Не запускается автоматически — только вручную.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv

    print("=" * 60)
    print("CLEANUP FIGURE CACHE")
    print("=" * 60)

    from services.figure_cache import _CACHE_DIR, list_orphan_files, used_hashes_from_db

    print(f"\nCache directory: {_CACHE_DIR}")

    # Собираем используемые хеши
    print("Collecting used hashes from DB...")
    used = used_hashes_from_db()
    print(f"  Used hashes: {len(used)}")

    # Перечисляем файлы кеша
    if not os.path.isdir(_CACHE_DIR):
        print("  Cache directory does not exist — nothing to clean.")
        return

    all_files = [f for f in os.listdir(_CACHE_DIR) if f.endswith('.svg')]
    total_size = sum(
        os.path.getsize(os.path.join(_CACHE_DIR, f))
        for f in all_files
    )
    print(f"  Cache files: {len(all_files)} ({total_size:,} bytes)")

    # Находим осиротевшие
    orphans = []
    for fname in all_files:
        h = fname[:-4]
        if h not in used:
            fpath = os.path.join(_CACHE_DIR, fname)
            fsize = os.path.getsize(fpath)
            orphans.append((fpath, fsize))

    if not orphans:
        print("\nNo orphan files — cache is clean.")
        return

    orphan_size = sum(sz for _, sz in orphans)
    print(f"\nOrphan files: {len(orphans)} ({orphan_size:,} bytes)")

    for fpath, fsize in orphans:
        if dry_run:
            print(f"  [DRY-RUN] would delete: {os.path.basename(fpath)} ({fsize:,} bytes)")
        else:
            try:
                os.remove(fpath)
                print(f"  DELETED: {os.path.basename(fpath)} ({fsize:,} bytes)")
            except OSError as e:
                print(f"  ERROR deleting {os.path.basename(fpath)}: {e}")

    if dry_run:
        print(f"\n[DRY-RUN] Would free {orphan_size:,} bytes from {len(orphans)} files.")
        print("Run without --dry-run to actually delete.")
    else:
        remaining = len([f for f in os.listdir(_CACHE_DIR) if f.endswith('.svg')])
        print(f"\nDone. Remaining cache files: {remaining}")


if __name__ == "__main__":
    main()
