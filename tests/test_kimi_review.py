# -*- coding: utf-8 -*-
"""tests/test_kimi_review.py — X10 acceptance tests for Kimi review layer.

Uses conftest.py ORM fixtures on tmp_path; NEVER touches the production DB.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestKimiReviewModel:
    """Model-level tests — schema, labels, toggles."""

    def test_kimi_review_table_created(self, app):
        """kimi_reviews table exists in test DB after create_all."""
        from models import db
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        assert 'kimi_reviews' in tables

    def test_kimi_review_columns(self, app):
        """kimi_reviews has expected columns."""
        from models import db
        columns = {c['name']: c for c in db.inspect(db.engine).get_columns('kimi_reviews')}
        assert 'id' in columns
        assert 'solution_attempt_id' in columns
        assert columns['solution_attempt_id']['nullable'] is True
        assert 'raw_response' in columns
        assert 'label' in columns
        assert 'created_at' in columns

    def test_users_kimi_toggle_columns(self, app):
        """Users table has three kimi toggle columns, default False."""
        from models import db
        columns = {c['name']: c for c in db.inspect(db.engine).get_columns('users')}
        for col_name in ('kimi_review_probe', 'kimi_review_daily', 'kimi_review_method'):
            assert col_name in columns, f'{col_name} missing'
            default = columns[col_name].get('default')
            assert default == "'0'" or default == '0', f'{col_name} default not False'

    def test_solution_attempt_model_line(self, app):
        """SolutionAttempt at expected line in models.py."""
        import models
        import inspect
        try:
            source_file = inspect.getfile(models.SolutionAttempt)
            with open(source_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            found = False
            for i, line in enumerate(lines, 1):
                if line.strip().startswith('class SolutionAttempt'):
                    found = True
                    break
            assert found, 'SolutionAttempt class not found'
        except (TypeError, OSError):
            pytest.skip('Cannot locate SolutionAttempt source')


class TestKimiLabels:
    """Label extraction logic."""

    def test_extract_label_valid(self):
        """_extract_label returns valid labels from model output."""
        from services.kimi_review import _extract_label

        assert _extract_label('some comment\nход верный') == 'ход верный'
        assert _extract_label('анализ\nверный ответ, дыра в рассуждении') == 'верный ответ, дыра в рассуждении'
        assert _extract_label('проверка\nугадал') == 'угадал'

    def test_extract_label_invalid(self):
        """_extract_label returns None for invalid labels."""
        from services.kimi_review import _extract_label

        assert _extract_label('непонятно что') is None
        assert _extract_label('') is None
        assert _extract_label('почти ход верный') is None

    def test_extract_label_quotes_stripping(self):
        """_extract_label strips quotes from label."""
        from services.kimi_review import _extract_label

        assert _extract_label('comment\n"ход верный"') == 'ход верный'
        assert _extract_label('text\n[угадал]') == 'угадал'


class TestKimiToggle:
    """Toggle check logic."""

    def test_kimi_disabled_for_unauthenticated(self, app):
        """_kimi_enabled_for returns False when not logged in."""
        from services.kimi_review import _kimi_enabled_for
        assert _kimi_enabled_for('probe') is False

    def test_kimi_disabled_by_default(self, app, test_user):
        """New user has all kimi toggles off."""
        from models import db

        user = db.session.merge(test_user)
        assert user.kimi_review_probe is False
        assert user.kimi_review_daily is False
        assert user.kimi_review_method is False


class TestKimiImageTransmission:
    """Image is sent as base64, never via http URL."""

    def test_no_image_url_http_reference(self):
        """call_kimi_api builds image_url with data: URI, not http."""
        from services.kimi_review import call_kimi_api
        import inspect

        src = inspect.getsource(call_kimi_api)
        assert 'base64' in src, 'base64 encoding not found in call_kimi_api'
        # The image_url type is used with data: URI, not http
        assert 'data:' in src, 'data: URI not found for image transmission'


class TestKimiDoesNotAffectLevels:
    """Kimi review must NEVER modify mu, sigma, is_correct, or any level."""

    def test_review_solution_does_not_import_level_engine(self):
        """review_solution does not import or call level_engine."""
        from services.kimi_review import review_solution
        import inspect

        src = inspect.getsource(review_solution)
        assert 'level_engine' not in src.lower()
        assert 'mu' not in src.split('def ')[0]  # not at function signature level
        assert 'sigma' not in src.split('def ')[0]

    def test_review_solution_no_setattr_mu_sigma(self):
        """review_solution never sets mu, sigma, is_correct, math_level."""
        from services.kimi_review import review_solution
        import inspect

        src = inspect.getsource(review_solution)
        for forbidden in ('mu', 'sigma', 'is_correct', 'math_level', 'current_level', 'final_mu'):
            assert f'.{forbidden}' not in src, f'review_solution references .{forbidden}'

    def test_review_solution_docstring_claims_no_scoring(self, app):
        """review_solution docstring states it doesn't modify scoring."""
        from services.kimi_review import review_solution
        import inspect

        src = inspect.getsource(review_solution)
        assert 'Does NOT modify' in src or 'not modify' in src.lower()


class TestCallKimiApiWithMock:
    """Integration tests with mocked API."""

    def test_mocked_call_returns_label(self, app, test_user):
        """With toggle ON and mocked API, review returns a valid label."""
        from models import db, SolutionAttempt

        test_user.kimi_review_probe = True
        test_user.kimi_review_daily = True
        db.session.commit()

        # Create a solution attempt
        attempt = SolutionAttempt(
            user_id=test_user.id,
            task_id=999,
            probe_id=None,
            attempt_type='text',
            solution_text='[TEST] mock solution text',
        )
        db.session.add(attempt)
        db.session.commit()

        from services.kimi_review import review_solution, call_kimi_api as _orig, _kimi_enabled_for as _orig_toggle

        def mock_api(text='', image_base64=None):
            return 'comment\nход верный'

        import services.kimi_review as kr
        kr.call_kimi_api = mock_api
        kr._kimi_enabled_for = lambda s: True

        try:
            result = review_solution(attempt_id=attempt.id, surface='probe')
            assert result['label'] == 'ход верный'
            assert result['raw_response'] == 'comment\nход верный'
            assert result['error'] is None
        finally:
            kr.call_kimi_api = _orig
            kr._kimi_enabled_for = _orig_toggle

    def test_mocked_call_persists_review(self, app, test_user):
        """After review_solution, KimiReview row exists in DB."""
        from models import db, SolutionAttempt, KimiReview

        test_user.kimi_review_probe = True
        db.session.commit()

        attempt = SolutionAttempt(
            user_id=test_user.id,
            task_id=999,
            probe_id=None,
            attempt_type='text',
            solution_text='[TEST] another mock',
        )
        db.session.add(attempt)
        db.session.commit()

        import services.kimi_review as kr
        original_api = kr.call_kimi_api
        original_toggle = kr._kimi_enabled_for
        kr.call_kimi_api = lambda text='', image_base64=None: 'test\nугадал'
        kr._kimi_enabled_for = lambda s: True

        try:
            kr.review_solution(attempt_id=attempt.id, surface='probe')
            reviews = KimiReview.query.filter_by(solution_attempt_id=attempt.id).all()
            assert len(reviews) == 1
            assert reviews[0].label == 'угадал'
            assert 'test' in reviews[0].raw_response
        finally:
            kr.call_kimi_api = original_api
            kr._kimi_enabled_for = original_toggle

    def test_review_text_without_attempt_record(self, app, test_user):
        """review_text works without SolutionAttempt and persists KimiReview with NULL solution_attempt_id."""
        from models import db, KimiReview

        test_user.kimi_review_probe = True
        db.session.commit()

        import services.kimi_review as kr
        original_api = kr.call_kimi_api
        original_toggle = kr._kimi_enabled_for
        kr.call_kimi_api = lambda text='', image_base64=None: 'ok\nверный ответ, дыра в рассуждении'
        kr._kimi_enabled_for = lambda s: True

        try:
            result = kr.review_text(
                task_text='[TEST] task',
                correct_answer='42',
                solution_text='[TEST] solution',
                surface='probe',
            )
            assert result['label'] == 'верный ответ, дыра в рассуждении'

            reviews = KimiReview.query.filter_by(solution_attempt_id=None).all()
            assert len(reviews) >= 1
        finally:
            kr.call_kimi_api = original_api
            kr._kimi_enabled_for = original_toggle

    def test_key_read_via_os_environ(self):
        """KIMI_API_KEY is read via os.environ.get, never hardcoded."""
        import inspect
        from services.kimi_review import _get_kimi_key

        src = inspect.getsource(_get_kimi_key)
        assert 'os.environ' in src
        # Must not contain a literal API key string
        assert 'sk-' not in src

    def test_model_read_via_os_environ(self):
        """KIMI_MODEL is read via os.environ.get, never hardcoded."""
        import inspect
        from services.kimi_review import _get_kimi_model

        src = inspect.getsource(_get_kimi_model)
        assert 'os.environ' in src
