"""Standalone unit/SQLite tests: python tests/test_readiness_survey_unit.py.
These do not start the production app or access its database.
"""
import ast
import json
from pathlib import Path
import sqlite3
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'routes' / 'surveys.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
PARTS = [node for node in TREE.body if
         (isinstance(node, ast.FunctionDef) and node.name in ('completed_intake', 'distribution'))
         or (isinstance(node, ast.Assign) and any(
             isinstance(t, ast.Name) and t.id in ('OPTIONS', 'SCHEMA') for t in node.targets))]
NS = {'json': json}
exec(compile(ast.Module(body=PARTS, type_ignores=[]), str(SOURCE), 'exec'), NS)
INSERT = next(node.value for node in ast.walk(TREE)
              if isinstance(node, ast.Constant) and isinstance(node.value, str)
              and node.value.startswith('INSERT INTO readiness_survey_answers'))


class ReadinessTests(unittest.TestCase):
    def test_completed(self):
        self.assertTrue(NS['completed_intake']({'intake': {'completed': True}}))

    def test_skipped(self):
        self.assertFalse(NS['completed_intake']({'intake': {'completed': True, 'skipped': True}}))

    def test_unfinished(self):
        self.assertFalse(NS['completed_intake']({'intake': {'completed': False}}))

    def test_json_state(self):
        self.assertTrue(NS['completed_intake']('{"intake":{"completed":true}}'))

    def test_invalid_states(self):
        for value in (None, [], 'bad json', {'intake': []}, {}):
            with self.subTest(value=value):
                self.assertFalse(NS['completed_intake'](value))

    def test_zero_answers(self):
        stats = NS['distribution'](NS['OPTIONS'], {})
        self.assertEqual(stats['total'], 0)
        self.assertEqual([r['percent'] for r in stats['options']], [0, 0, 0])

    def test_percentages(self):
        stats = NS['distribution'](NS['OPTIONS'], {'yes': 2, 'try': 1, 'not_yet': 1})
        self.assertEqual(stats['total'], 4)
        self.assertEqual([r['percent'] for r in stats['options']], [50.0, 25.0, 25.0])

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute('PRAGMA foreign_keys=ON')
        self.conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        self.conn.execute('INSERT INTO users VALUES (1)')
        self.conn.execute(NS['SCHEMA'])

    def tearDown(self):
        self.conn.close()

    def test_repeat_keeps_first_answer(self):
        self.conn.execute(INSERT, {'uid': 1, 'answer': 'yes'})
        self.conn.execute(INSERT, {'uid': 1, 'answer': 'not_yet'})
        self.assertEqual(self.conn.execute('SELECT answer FROM readiness_survey_answers').fetchall(), [('yes',)])

    def test_invalid_answer_constraint(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(INSERT, {'uid': 1, 'answer': 'invalid'})

    def test_user_delete_cascades(self):
        self.conn.execute(INSERT, {'uid': 1, 'answer': 'try'})
        self.conn.execute('DELETE FROM users WHERE id=1')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM readiness_survey_answers').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
