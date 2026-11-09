"""Run standalone: python tests_guard/test_payment_test_login_unit.py.
No app import, database connection, provider call or production writes.
"""
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('payment_test_unit', Path(__file__).resolve().parents[1] / 'services/payment_test_login.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PaymentTestUnits(unittest.TestCase):
    def test_hash_accepts_only_exact_code(self):
        value = 'unit-тест'
        hashed = hashlib.pbkdf2_hmac('sha256', value.encode(), b'salt', 100000).hex()
        encoded = '100000$salt$' + hashed
        self.assertTrue(m.verify_code(value, encoded))
        self.assertFalse(m.verify_code(value + 'x', encoded))
        self.assertFalse(m.verify_code('', encoded))
        self.assertFalse(m.verify_code('x' * 129, encoded))
        self.assertFalse(m.verify_code(value, 'broken'))

    def test_origin(self):
        self.assertTrue(m.same_origin('https://formyla.net/login', 'https://formyla.net/'))
        for origin in ('', 'null', 'https://evil.test', 'http://formyla.net', 'https://formyla.net.evil.test'):
            self.assertFalse(m.same_origin(origin, 'https://formyla.net/'))

    def test_limiter(self):
        limit = m.AttemptLimiter()
        self.assertTrue(all(limit.allow('ip', 1) for _ in range(8)))
        self.assertFalse(limit.allow('ip', 2))
        self.assertTrue(limit.allow('other', 2))
        self.assertTrue(limit.allow('ip', 301))

    def test_limiter_bounded(self):
        limit = m.AttemptLimiter()
        for i in range(1024):
            self.assertTrue(limit.allow(str(i), 1))
        self.assertFalse(limit.allow('overflow', 2))
        self.assertTrue(limit.allow('overflow', 301))

    def test_no_privileged_identity(self):
        user = SimpleNamespace(id=8000, is_admin=False, is_guest=False, role='student', email='tester@example.invalid', nickname='payment_test_84')
        self.assertTrue(m.safe_user(user))
        for field, value in (('id', 1), ('id', 5), ('id', 7452), ('is_admin', True), ('is_guest', True), ('role', 'admin'), ('nickname', 'lavrik'), ('email', 'kr1venkovictor@yandex.ru')):
            altered = SimpleNamespace(**vars(user))
            setattr(altered, field, value)
            self.assertFalse(m.safe_user(altered))
        with patch.dict(m.os.environ, {'ADMIN_EMAILS': user.email}):
            self.assertFalse(m.safe_user(user))

    def test_existing_pilot_preserved(self):
        with patch.object(m, 'pilot_access', return_value=False):
            wrapped = m.extend_pilot(lambda uid: uid == 1)
            self.assertTrue(wrapped(1))
            self.assertFalse(wrapped(8000))
        with patch.object(m, 'pilot_access', return_value=True):
            self.assertTrue(m.extend_pilot(lambda uid: False)(8000))


if __name__ == '__main__':
    unittest.main()
