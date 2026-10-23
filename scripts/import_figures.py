# -*- coding: utf-8 -*-
"""
scripts/import_figures.py - I1: import ready SVG figures into the database
and copy them into static/figures/ for serving.

Usage:
    python scripts/import_figures.py [--dir PATH] [--dry-run] [--limit N] [--force]

Default source: out/figures_all (fallback to out/figures).
Accepted SVG files must: be non-empty, parse as XML, have <svg> root,
contain #070C18 background, contain 620 canvas dimension.
"""

import argparse
import logging
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='[import_figures] %(levelname)s %(message)s',
)
logger = logging.getLogger('import_figures')

SVG_BACKGROUND = '#070C18'
SVG_CANVAS_DIM = 620


def validate_svg(filepath):
    """Validate an SVG file. Returns None if OK, or a reason string if rejected."""
    try:
        size = os.path.getsize(filepath)
    except OSError as e:
        return f"cannot stat: {e}"
    if size == 0:
        return "empty file (0 bytes)"

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except ET.ParseError as e:
        return f"XML parse error: {e}"
    except Exception as e:
        return f"XML read error: {e}"

    tag = root.tag.lower()
    if 'svg' not in tag:
        return f"not <svg> root: {root.tag}"

    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
            raw = fh.read()
    except Exception as e:
        return f"cannot read file for bg check: {e}"
    if SVG_BACKGROUND not in raw:
        return f"missing background colour {SVG_BACKGROUND}"

    if '620' not in raw:
        return "missing canvas dimension 620"

    return None


def run_import(dir_path=None, dry_run=False, limit=None, force=False,
               _app=None, _db=None):
    """Main import routine, callable from CLI or tests.

    _app: Flask app instance (test fixture). If None, imports real app.
    _db: SQLAlchemy db instance (test fixture). If None, imports real db.
    """
    if _app is not None:
        from models import AdaptiveTask
        _dbx = _db
        static_figures = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', 'figures',
        )
    else:
        from app import app as _real_app, db as _real_db
        from models import AdaptiveTask
        _app = _real_app
        _dbx = _real_db
        static_figures = os.path.join(ROOT, 'static', 'figures')

    if dir_path is None:
        dir_path = os.path.join(ROOT, 'out', 'figures_all')
        if not os.path.isdir(dir_path):
            dir_path = os.path.join(ROOT, 'out', 'figures')
            logger.info("out/figures_all not found, using out/figures")
            print("[import_figures] out/figures_all not found, using out/figures")
        else:
            logger.info("using out/figures_all as source")
            print("[import_figures] using out/figures_all as source")

    source_dir = os.path.abspath(dir_path)

    if not os.path.isdir(source_dir):
        logger.error("source directory not found: %s", source_dir)
        print(f"[import_figures] ERROR: source directory not found: {source_dir}")
        return {
            'accepted': 0, 'skipped_bound': 0, 'skipped_broken': 0,
            'unmatched': 0, 'unmatched_uids': [], 'source_dir': None,
        }

    os.makedirs(static_figures, exist_ok=True)

    if dry_run:
        logger.info("DRY RUN mode - no writes to DB or filesystem")
        print("[import_figures] DRY RUN mode")

    all_files = sorted(
        [f for f in os.listdir(source_dir) if f.endswith('.svg')],
        key=str.lower,
    )
    if limit is not None and limit > 0:
        all_files = all_files[:limit]

    logger.info("found %d SVG files (limit=%s)", len(all_files), limit)

    uid_pattern = re.compile(r'^(.+?)(_aux)?\.svg$')
    pairs = {}
    for fname in all_files:
        m = uid_pattern.match(fname)
        if not m:
            continue
        uid = m.group(1)
        is_aux = m.group(2) == '_aux'
        if uid not in pairs:
            pairs[uid] = {'base': None, 'aux': None}
        if is_aux:
            pairs[uid]['aux'] = fname
        else:
            pairs[uid]['base'] = fname

    accepted = 0
    skipped_bound = 0
    skipped_broken = 0
    unmatched = 0
    unmatched_uids = []
    rejection_reasons = []

    # Use the app context from the caller (test has it pushed, real will be pushed)
    needs_push = (_app is not None and not hasattr(_app, '_test_context_active'))
    if _dbx is not None:
        for uid in sorted(pairs.keys()):
            entry = pairs[uid]

            task = AdaptiveTask.query.filter_by(source_id=uid).first()
            if task is None:
                unmatched += 1
                unmatched_uids.append(uid)
                logger.info("skipped %s: no AdaptiveTask with source_id=%s", uid, uid)
                print(f"  [SKIP] {uid}: no matching task")
                continue

            existing_base = getattr(task, 'svg_path', None)
            if existing_base and not force:
                skipped_bound += 1
                logger.info("skipped %s: already bound (svg_path=%s)", uid, existing_base)
                print(f"  [SKIP] {uid}: already bound to {existing_base}")
                continue

            base_valid = True
            base_rel_path = None
            aux_valid = True
            aux_rel_path = None

            if entry['base']:
                base_src = os.path.join(source_dir, entry['base'])
                reason = validate_svg(base_src)
                if reason is not None:
                    base_valid = False
                    skipped_broken += 1
                    rejection_reasons.append(f"{entry['base']}: {reason}")
                    logger.info("REJECTED %s: %s", entry['base'], reason)
                    print(f"  [REJECT] {entry['base']}: {reason}")
                else:
                    base_rel_path = f"figures/{entry['base']}"

            if entry['aux']:
                aux_src = os.path.join(source_dir, entry['aux'])
                reason = validate_svg(aux_src)
                if reason is not None:
                    aux_valid = False
                    skipped_broken += 1
                    rejection_reasons.append(f"{entry['aux']}: {reason}")
                    logger.info("REJECTED %s: %s", entry['aux'], reason)
                    print(f"  [REJECT] {entry['aux']}: {reason}")
                else:
                    aux_rel_path = f"figures/{entry['aux']}"

            if entry['base'] and not base_valid:
                continue

            if dry_run:
                accepted += 1
                print(f"  [DRY-RUN] {uid}: base={entry['base']}, aux={entry['aux']}")
                continue

            try:
                if entry['base']:
                    shutil.copy2(
                        os.path.join(source_dir, entry['base']),
                        os.path.join(static_figures, entry['base']),
                    )
                    logger.info("copied %s -> static/figures/", entry['base'])

                if entry['aux'] and aux_valid:
                    shutil.copy2(
                        os.path.join(source_dir, entry['aux']),
                        os.path.join(static_figures, entry['aux']),
                    )
                    logger.info("copied %s -> static/figures/", entry['aux'])

                task.svg_path = base_rel_path
                if entry['aux'] and aux_valid:
                    task.aux_svg_path = aux_rel_path
                    task.has_aux = True
                _dbx.session.commit()

                accepted += 1
                print(f"  [ACCEPT] {uid}: base={entry['base']}" +
                      (f" aux={entry['aux']}" if entry['aux'] else ""))

            except Exception as e:
                _dbx.session.rollback()
                logger.error("DB error for %s: %s", uid, e)
                print(f"  [ERROR] {uid}: {e}")

    print()
    print("=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"  source dir : {source_dir}")
    print(f"  accepted   : {accepted}")
    print(f"  skipped    : {skipped_bound + skipped_broken}")
    print(f"    already bound : {skipped_bound}")
    print(f"    failed check  : {skipped_broken}")
    print(f"  unmatched  : {unmatched}")
    print()

    if rejection_reasons:
        print("Rejection details:")
        for r in rejection_reasons:
            print(f"  - {r}")
        print()

    if unmatched_uids:
        print("Unmatched UIDs (no AdaptiveTask with matching source_id):")
        for uid in unmatched_uids:
            print(f"  - {uid}")
        print()

    return {
        'accepted': accepted,
        'skipped_bound': skipped_bound,
        'skipped_broken': skipped_broken,
        'unmatched': unmatched,
        'unmatched_uids': unmatched_uids,
        'source_dir': source_dir,
    }


def main():
    parser = argparse.ArgumentParser(
        description='I1: Import ready SVG figures into AdaptiveTask and static/figures/',
    )
    parser.add_argument(
        '--dir', type=str, default=None,
        help='Source directory (default: out/figures_all, fallback to out/figures)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Scan and report only, no writes to DB or filesystem',
    )
    parser.add_argument(
        '--limit', type=int, default=None,
        help='Process only first N SVG files (alphabetical order)',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Overwrite already-bound svg_path (default: skip bound tasks)',
    )

    args = parser.parse_args()

    from app import app as _real_app, db as _real_db
    with _real_app.app_context():
        run_import(
            dir_path=args.dir,
            dry_run=args.dry_run,
            limit=args.limit,
            force=args.force,
        )


if __name__ == '__main__':
    main()
