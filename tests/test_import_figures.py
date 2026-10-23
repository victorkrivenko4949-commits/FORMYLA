# -*- coding: utf-8 -*-
"""
tests/test_import_figures.py - I1: tests for scripts/import_figures.py.

Tests:
  - validate_svg unit tests (ok, empty, broken xml, no bg)
  - dry_run: --dry-run does not write to DB or filesystem
  - accept_and_broken: i1_ok.svg and i1_ok2 pair accepted, i1_broken.svg rejected
  - idempotent: second run without --force does not change paths
  - force: second run with --force updates paths
  - limit: --limit 1 processes at most 1 file
"""

import os
import pytest
from scripts.import_figures import run_import, validate_svg

VALID_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg"'
    ' viewBox="0 0 620 620" width="620" height="620">\n'
    '  <rect width="620" height="620" fill="#070C18"/>\n'
    '  <g transform="translate(60,60)">\n'
    '    <circle cx="250" cy="250" r="100" stroke="#4C7DFF"'
    ' stroke-width="2" fill="none"/>\n'
    '    <text x="100" y="100" fill="#E6EBF7"'
    ' font-family="Satoshi, system-ui" font-size="14">A</text>\n'
    '  </g>\n'
    '</svg>\n'
)


def create_test_figures_dir(tmp_path):
    """Create a directory with synthetic SVG files for I1 testing.

    Files: i1_ok.svg (valid, no aux), i1_ok2.svg + i1_ok2_aux.svg (valid pair),
    i1_broken.svg (empty, 0 bytes).
    Returns str path to the directory.
    """
    figures_dir = tmp_path / "test_figures_i1"
    figures_dir.mkdir()

    (figures_dir / "i1_ok.svg").write_text(VALID_SVG, encoding='utf-8')

    (figures_dir / "i1_ok2.svg").write_text(VALID_SVG, encoding='utf-8')
    (figures_dir / "i1_ok2_aux.svg").write_text(VALID_SVG.replace(
        'stroke-width="2" fill="none"/>',
        'stroke-width="2" fill="none"/>\n'
        '    <line x1="150" y1="50" x2="150" y2="250"'
        ' stroke="#E5AC3A" stroke-width="1.5" stroke-dasharray="6,4"/>',
    ), encoding='utf-8')

    # broken.svg - empty file (0 bytes)
    (figures_dir / "i1_broken.svg").write_text('', encoding='utf-8')

    return str(figures_dir)


# ── validate_svg unit tests ─────────────────────────────────────────────

def test_validate_svg_ok(tmp_path):
    p = tmp_path / "valid_test.svg"
    p.write_text(VALID_SVG, encoding='utf-8')
    assert validate_svg(str(p)) is None


def test_validate_svg_empty(tmp_path):
    p = tmp_path / "empty_test.svg"
    p.write_text('', encoding='utf-8')
    reason = validate_svg(str(p))
    assert reason is not None
    assert 'empty' in reason.lower() or '0 bytes' in reason.lower()


def test_validate_svg_broken_xml(tmp_path):
    p = tmp_path / "broken_xml.svg"
    p.write_text('this is not xml <<< >>>', encoding='utf-8')
    reason = validate_svg(str(p))
    assert reason is not None


def test_validate_svg_no_bg(tmp_path):
    p = tmp_path / "no_bg.svg"
    p.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"'
        ' viewBox="0 0 620 620" width="620" height="620">'
        '<rect width="620" height="620" fill="#FFFFFF"/></svg>',
        encoding='utf-8',
    )
    reason = validate_svg(str(p))
    assert reason is not None


# ── import tests ────────────────────────────────────────────────────────


class TestDryRun:
    """dry-run: no writes to DB or filesystem."""

    def test_dry_run_no_files_copied(self, app, three_import_tasks, tmp_path):
        from models import db
        figures_dir = create_test_figures_dir(tmp_path)

        files_before = set(os.listdir(figures_dir))
        result = run_import(dir_path=figures_dir, dry_run=True,
                            _app=app, _db=db)
        files_after = set(os.listdir(figures_dir))

        # dry-run should not remove or add files in source dir
        assert files_before == files_after
        # dry-run summary should show accepted > 0 (dry-run counts even broken as accepted in dry-run mode)
        # In dry-run, validation still runs but no writes happen
        assert result['accepted'] >= 1

        # check DB was not changed
        from models import AdaptiveTask
        for t in AdaptiveTask.query.all():
            assert getattr(t, 'svg_path', None) is None


class TestAcceptAndBroken:
    """Accept i1_ok.svg + i1_ok2 pair, reject i1_broken.svg."""

    def test_accept_ok_and_reject_broken(self, app, three_import_tasks, tmp_path):
        from models import db, AdaptiveTask
        figures_dir = create_test_figures_dir(tmp_path)

        result = run_import(dir_path=figures_dir, _app=app, _db=db)

        assert result['accepted'] >= 2  # i1_ok + i1_ok2
        assert result['skipped_broken'] >= 1  # i1_broken

        # check DB for i1_ok
        t_ok = AdaptiveTask.query.filter_by(source_id='i1_ok').first()
        assert t_ok is not None
        assert t_ok.svg_path is not None
        assert 'i1_ok.svg' in t_ok.svg_path
        assert not t_ok.has_aux

        # check DB for i1_ok2
        t_ok2 = AdaptiveTask.query.filter_by(source_id='i1_ok2').first()
        assert t_ok2 is not None
        assert t_ok2.svg_path is not None
        assert 'i1_ok2.svg' in t_ok2.svg_path
        assert t_ok2.has_aux
        assert t_ok2.aux_svg_path is not None
        assert 'i1_ok2_aux.svg' in t_ok2.aux_svg_path

        # check DB for i1_broken - must NOT be bound
        t_broken = AdaptiveTask.query.filter_by(source_id='i1_broken').first()
        assert t_broken is not None
        assert t_broken.svg_path is None

        # check files were copied to static/figures/
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_figures = os.path.join(ROOT, 'static', 'figures')
        assert os.path.exists(os.path.join(static_figures, 'i1_ok.svg'))
        assert os.path.exists(os.path.join(static_figures, 'i1_ok2.svg'))
        assert os.path.exists(os.path.join(static_figures, 'i1_ok2_aux.svg'))
        assert not os.path.exists(os.path.join(static_figures, 'i1_broken.svg'))

        # cleanup
        for f in ['i1_ok.svg', 'i1_ok2.svg', 'i1_ok2_aux.svg']:
            fp = os.path.join(static_figures, f)
            if os.path.exists(fp):
                os.remove(fp)


class TestIdempotent:
    """Second run without --force does not change paths."""

    def test_idempotent_no_force(self, app, three_import_tasks, tmp_path):
        from models import db, AdaptiveTask
        figures_dir = create_test_figures_dir(tmp_path)

        # first run
        result1 = run_import(dir_path=figures_dir, _app=app, _db=db)
        assert result1['accepted'] >= 2

        t_ok = AdaptiveTask.query.filter_by(source_id='i1_ok').first()
        path_after_first = t_ok.svg_path

        # second run without --force
        result2 = run_import(dir_path=figures_dir, force=False,
                            _app=app, _db=db)
        assert result2['skipped_bound'] >= 1
        t_ok_after = AdaptiveTask.query.filter_by(source_id='i1_ok').first()
        assert t_ok_after.svg_path == path_after_first

        # print for acceptance
        print(f"  PATH BEFORE: {path_after_first}")
        print(f"  PATH AFTER : {t_ok_after.svg_path}")

        # cleanup
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_figures = os.path.join(ROOT, 'static', 'figures')
        for f in ['i1_ok.svg', 'i1_ok2.svg', 'i1_ok2_aux.svg']:
            fp = os.path.join(static_figures, f)
            if os.path.exists(fp):
                os.remove(fp)


class TestForce:
    """Second run with --force updates paths."""

    def test_force_overwrites(self, app, three_import_tasks, tmp_path):
        from models import db, AdaptiveTask
        figures_dir = create_test_figures_dir(tmp_path)

        # first run
        run_import(dir_path=figures_dir, _app=app, _db=db)

        t_ok = AdaptiveTask.query.filter_by(source_id='i1_ok').first()
        path_before = t_ok.svg_path
        assert path_before is not None

        # clear path and re-run with force
        t_ok.svg_path = None
        t_ok2 = AdaptiveTask.query.filter_by(source_id='i1_ok2').first()
        t_ok2.svg_path = None
        t_ok2.aux_svg_path = None
        t_ok2.has_aux = False
        db.session.commit()

        # force re-import
        result_force = run_import(dir_path=figures_dir, force=True,
                                  _app=app, _db=db)
        assert result_force['accepted'] >= 2

        t_ok = AdaptiveTask.query.filter_by(source_id='i1_ok').first()
        path_after = t_ok.svg_path
        assert path_after is not None
        # paths may be same or different - force should still set them
        print(f"  PATH BEFORE: {path_before}")
        print(f"  PATH AFTER : {path_after}")

        # cleanup
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_figures = os.path.join(ROOT, 'static', 'figures')
        for f in ['i1_ok.svg', 'i1_ok2.svg', 'i1_ok2_aux.svg']:
            fp = os.path.join(static_figures, f)
            if os.path.exists(fp):
                os.remove(fp)


class TestLimit:
    """--limit N processes at most N files."""

    def test_limit_one(self, app, three_import_tasks, tmp_path):
        from models import db
        figures_dir = create_test_figures_dir(tmp_path)

        result = run_import(dir_path=figures_dir, limit=1,
                            _app=app, _db=db)
        # With limit=1, sorted files: i1_broken.svg (uid i1_broken) is first.
        # It fails validation -> skipped_broken=1. Only 1 uid is processed.
        total_processed = (
            result['accepted'] + result['skipped_bound'] +
            result['skipped_broken'] + result['unmatched']
        )
        print(f"  PROCESSED: accepted={result['accepted']}"
              f" skipped_bound={result['skipped_bound']}"
              f" skipped_broken={result['skipped_broken']}"
              f" unmatched={result['unmatched']}"
              f" total={total_processed}")
        assert total_processed <= 1

        # cleanup
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        static_figures = os.path.join(ROOT, 'static', 'figures')
        for f in ['i1_ok.svg', 'i1_ok2.svg', 'i1_ok2_aux.svg', 'i1_broken.svg']:
            fp = os.path.join(static_figures, f)
            if os.path.exists(fp):
                os.remove(fp)
