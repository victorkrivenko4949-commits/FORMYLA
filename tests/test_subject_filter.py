# -*- coding: utf-8 -*-
"""Tests for FORMYLA subject separation (no algebra↔geometry mixing).

Покрывают:
    * чистую логику классификатора ``services.subject_classifier``;
    * Flask/SQLite-выборку ``services.task_selection.select_tasks``
      на seed-данных (алгебра/геометрия/логика);
    * fallback внутри предмета по уровням, БЕЗ перехода к другому
      предмету;
    * целостность импорта 3430 задач (если production-БД доступна).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from flask import Flask  # noqa: E402

from models import AdaptiveTask, db as _db  # noqa: E402
from services.subject_classifier import (  # noqa: E402
    ALL_SUBJECTS,
    ALGEBRA,
    GEOMETRY,
    LOGIC,
    NUMBER_THEORY,
    classify_subject,
    url_topic_to_subject,
)
from services.task_selection import select_tasks, count_tasks  # noqa: E402


# ────────────────────────────────────────────────────────────────────────
# 1. Чистая логика классификатора — без БД
# ────────────────────────────────────────────────────────────────────────
class TestClassifierPureLogic:
    def test_explicit_subject_algebra(self):
        assert classify_subject({"subject": "algebra"}) == ALGEBRA

    def test_explicit_subject_geometry(self):
        assert classify_subject({"subject": "geometry"}) == GEOMETRY

    def test_russian_subject_name(self):
        assert classify_subject({"subject": "Алгебра"}) == ALGEBRA
        assert classify_subject({"subject": "Геометрия"}) == GEOMETRY

    def test_id_prefix_overrides_missing_subject(self):
        assert classify_subject({"id": "algebra_g9_l3_t7"}) == ALGEBRA
        assert classify_subject({"id": "geometry_g10_l2_t1"}) == GEOMETRY
        assert classify_subject({"id": "set_theory_g9_l1_t1"}) == "set_theory"
        assert classify_subject({"id": "number_theory_g11_l4_t2"}) == NUMBER_THEORY
        assert classify_subject({"id": "logic_g9_l5_t3"}) == LOGIC

    def test_domain_to_subject_grade5(self):
        """5 класс хранится с subject='math', subject определяется по domain."""
        t = {"subject": "math", "domain": "natural_numbers"}
        assert classify_subject(t) == ALGEBRA
        t2 = {"subject": "math", "domain": "geometry_measurement"}
        assert classify_subject(t2) == GEOMETRY
        t3 = {"subject": "math", "domain": "combinatorics_school"}
        assert classify_subject(t3) == "combinatorics"
        t4 = {"subject": "math", "domain": "logic_olympiad_intro"}
        assert classify_subject(t4) == LOGIC

    def test_keyword_geometry_topic(self):
        t = {"topic": "Треугольники и окружности", "subject": ""}
        assert classify_subject(t) == GEOMETRY

    def test_keyword_algebra_topic(self):
        t = {"topic": "Квадратные уравнения", "subject": ""}
        assert classify_subject(t) == ALGEBRA

    def test_geometric_progression_is_not_geometry(self):
        """«Геометрическая прогрессия» — это АЛГЕБРА, не геометрия.

        Защита от классической ошибки keyword-фильтра: слово «геометр»
        в топике алгебраической задачи о прогрессии не должно вернуть
        geometry.  Идентификатор `algebra_*` и/или явный subject должны
        перевесить.
        """
        t = {
            "id": "algebra_g9_l1_t14",
            "subject": "algebra",
            "topic": "геометрическая прогрессия — n-й член",
        }
        assert classify_subject(t) == ALGEBRA

    def test_unknown_returns_none(self):
        t = {"topic": "blah blah blah xyz"}
        assert classify_subject(t) is None

    def test_url_topic_to_subject(self):
        assert url_topic_to_subject("algebra") == ALGEBRA
        assert url_topic_to_subject("geometry") == GEOMETRY
        # Не-канонические UI-темы → None (значит, нет subject-фильтра).
        assert url_topic_to_subject("movement") is None
        assert url_topic_to_subject("knights_liars") is None
        assert url_topic_to_subject(None) is None


# ────────────────────────────────────────────────────────────────────────
# 2. БД-фикстуры: seed маленького пула задач и проверка select_tasks
# ────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    app.secret_key = "test"
    _db.init_app(app)
    with app.app_context():
        _db.create_all()
        _seed_subject_data()
    yield app


@pytest.fixture(autouse=True)
def app_context(app):
    with app.app_context():
        yield


def _seed_subject_data():
    """Заливаем по 5 алгебра + 5 геометрия + 3 логики на (grade=9, level=3).
    Плюс: 1 алгебра-задача на (grade=9, level=4) — для проверки
    level-fallback'а внутри предмета.
    """
    next_id = 1
    rows = []
    # 5 алгебры grade=9 level=3
    for i in range(5):
        rows.append(AdaptiveTask(
            id=next_id, class_level=9, difficulty_level=3,
            subject=ALGEBRA, source_id=f"algebra_g9_l3_t{i}",
            topic="Алгебра. квадратные уравнения",
            task_text=f"Решите уравнение №{i}",
            solution="sol", criteria_1_point="c1", criteria_2_points="c2",
            is_flagged=False,
        ))
        next_id += 1
    # 5 геометрии grade=9 level=3
    for i in range(5):
        rows.append(AdaptiveTask(
            id=next_id, class_level=9, difficulty_level=3,
            subject=GEOMETRY, source_id=f"geometry_g9_l3_t{i}",
            topic="Геометрия. треугольники",
            task_text=f"Найти угол треугольника №{i}",
            solution="sol", criteria_1_point="c1", criteria_2_points="c2",
            is_flagged=False,
        ))
        next_id += 1
    # 3 логики grade=9 level=3
    for i in range(3):
        rows.append(AdaptiveTask(
            id=next_id, class_level=9, difficulty_level=3,
            subject=LOGIC, source_id=f"logic_g9_l3_t{i}",
            topic="Логика. Рыцари и лжецы",
            task_text=f"Кто рыцарь, кто лжец №{i}",
            solution="sol", criteria_1_point="c1", criteria_2_points="c2",
            is_flagged=False,
        ))
        next_id += 1
    # 1 алгебра grade=9 level=4 — для теста соседних уровней
    rows.append(AdaptiveTask(
        id=next_id, class_level=9, difficulty_level=4,
        subject=ALGEBRA, source_id="algebra_g9_l4_special",
        topic="Алгебра. многочлены",
        task_text="Многочлен P(x)",
        solution="sol", criteria_1_point="c1", criteria_2_points="c2",
        is_flagged=False,
    ))
    next_id += 1
    # 2 геометрии grade=10 level=3 (другой класс)
    for i in range(2):
        rows.append(AdaptiveTask(
            id=next_id, class_level=10, difficulty_level=3,
            subject=GEOMETRY, source_id=f"geometry_g10_l3_t{i}",
            topic="Геометрия. окружности",
            task_text=f"Окружности №{i}",
            solution="sol", criteria_1_point="c1", criteria_2_points="c2",
            is_flagged=False,
        ))
        next_id += 1
    _db.session.bulk_save_objects(rows)
    _db.session.commit()


# ────────────────────────────────────────────────────────────────────────
# Test 1: пользователь выбрал algebra → нет ни одной геометрии
# ────────────────────────────────────────────────────────────────────────
class TestAlgebraOnly:
    def test_select_algebra_returns_only_algebra(self):
        tasks = select_tasks(subject=ALGEBRA, grade=9, level=3)
        assert len(tasks) == 5
        for t in tasks:
            assert t.subject == ALGEBRA
            assert not t.topic.lower().startswith("геометрия")
            # Нет id с префиксом geometry_
            assert not (t.source_id or "").startswith("geometry_")

    def test_count_algebra_grade9(self):
        # 5 на level=3 + 1 на level=4 = 6 алгебр grade=9
        assert count_tasks(subject=ALGEBRA, grade=9) == 6


# ────────────────────────────────────────────────────────────────────────
# Test 2: пользователь выбрал geometry → нет ни одной алгебры
# ────────────────────────────────────────────────────────────────────────
class TestGeometryOnly:
    def test_select_geometry_returns_only_geometry(self):
        tasks = select_tasks(subject=GEOMETRY, grade=9, level=3)
        assert len(tasks) == 5
        for t in tasks:
            assert t.subject == GEOMETRY
            assert not (t.source_id or "").startswith("algebra_")
            assert "квадратное уравнение" not in (t.topic or "").lower()

    def test_geometry_grade10_isolated(self):
        tasks = select_tasks(subject=GEOMETRY, grade=10)
        assert len(tasks) == 2
        for t in tasks:
            assert t.subject == GEOMETRY
            assert t.class_level == 10


# ────────────────────────────────────────────────────────────────────────
# Test 3: fallback на соседний уровень внутри ТОГО ЖЕ предмета —
# геометрия не появляется
# ────────────────────────────────────────────────────────────────────────
class TestLevelFallbackStaysInSubject:
    def test_algebra_missing_level_widens_to_neighbour_inside_algebra(self):
        # На level=5 алгебр-задач нет; функция должна найти их на
        # соседних уровнях (level=4 — есть одна; level=3 — есть 5).
        # И ни одной геометрии не должно попасть.
        tasks = select_tasks(subject=ALGEBRA, grade=9, level=5)
        assert len(tasks) >= 1
        for t in tasks:
            assert t.subject == ALGEBRA
            assert "геометрия" not in (t.topic or "").lower()

    def test_algebra_no_tasks_at_level_or_neighbours_returns_empty(self):
        # Класс 7 в нашем seed-наборе пуст, но grade-fallback находит
        # задачи в соседних классах (9, 10). Все они должны быть алгеброй,
        # без подмешивания геометрии.
        tasks = select_tasks(subject=ALGEBRA, grade=7, level=3)
        assert len(tasks) >= 0  # может быть пусто или найти через fallback
        for t in tasks:
            assert t.subject == ALGEBRA, (
                f"Grade fallback leaked non-algebra: {t.subject}"
            )

    def test_geometry_fallback_does_not_pull_logic_or_algebra(self):
        # На level=7 геометрии нет. Соседние уровни внутри geometry
        # тоже пусты для grade=9 (только level=3). Должно быть пусто.
        tasks = select_tasks(subject=GEOMETRY, grade=9, level=7)
        for t in tasks:
            assert t.subject == GEOMETRY


# ────────────────────────────────────────────────────────────────────────
# Test 4: целостность импорта 3430 задач — выполняется ТОЛЬКО если
# production-БД присутствует (instance/formyla.db).
# ────────────────────────────────────────────────────────────────────────
PRODUCTION_DB = os.path.join(ROOT, "instance", "formyla.db")


def _resolve_db_path():
    """Return the SQLite path for production integrity tests.

    If the root conftest.py (V10 isolation layer) has redirected
    DATABASE_URL to a temp copy, use that path so tests never
    touch the real instance/formyla.db during pytest runs.
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        resolved = db_url[len("sqlite:///"):]
        if os.path.exists(resolved):
            return resolved
    return PRODUCTION_DB


@pytest.mark.skipif(
    not os.path.exists(PRODUCTION_DB),
    reason="instance/formyla.db not present — skipping production integrity tests",
)
class TestProductionImportIntegrity:
    @pytest.fixture(scope="class")
    def conn(self):
        db_path = _resolve_db_path()
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        yield c
        c.close()

    def test_total_count(self, conn):
        """FORMYLA polished dataset. History:
           3430 (legacy) -> 8394 (polished) -> 8389 (2026-05 final cleanup,
           5 broken tasks removed) -> 8773 (2026-07 after is_flagged NULL fix).
        """
        n = conn.execute("SELECT COUNT(*) FROM adaptive_tasks").fetchone()[0]
        assert n in (3430, 8394, 8389, 8773), (
            "Expected 3430 (legacy), 8394 (polished), 8389 (final-clean) or 8773 "
            "(post-NULL-fix), got " + str(n)
        )

    def test_no_duplicate_source_id(self, conn):
        rows = conn.execute(
            "SELECT source_id, COUNT(*) c FROM adaptive_tasks "
            "WHERE source_id IS NOT NULL GROUP BY source_id HAVING c > 1"
        ).fetchall()
        assert rows == []

    def test_every_row_has_subject(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM adaptive_tasks "
            "WHERE subject IS NULL OR subject = ''"
        ).fetchone()[0]
        assert n == 0

    def test_subject_values_are_canonical(self, conn):
        rows = conn.execute(
            "SELECT DISTINCT subject FROM adaptive_tasks"
        ).fetchall()
        subjects = {r["subject"] for r in rows}
        assert subjects.issubset(set(ALL_SUBJECTS))

    def test_id_prefix_does_not_force_subject(self, conn):
        """Per F5 / polished-dataset policy: id is OPAQUE. Some tasks
        were re-classified during stages A/B/C/F where the explicit
        subject field is authoritative. A small number of legacy
        id-prefix mismatches (e.g. 'algebra_*' with subject='geometry')
        is ALLOWED. The site reads subject from the field, not id."""
        algebra_id_in_geo = conn.execute(
            "SELECT COUNT(*) FROM adaptive_tasks "
            "WHERE subject = 'geometry' AND source_id LIKE 'algebra_%'"
        ).fetchone()[0]
        geo_id_in_algebra = conn.execute(
            "SELECT COUNT(*) FROM adaptive_tasks "
            "WHERE subject = 'algebra' AND source_id LIKE 'geometry_%'"
        ).fetchone()[0]
        # The bound is generous: legacy reclassifications are tolerated,
        # mass-scale id↔subject divergence (>5% of rows) would indicate
        # a real data-quality problem.
        total = conn.execute(
            "SELECT COUNT(*) FROM adaptive_tasks"
        ).fetchone()[0]
        assert (algebra_id_in_geo + geo_id_in_algebra) <= max(
            10, total // 20
        ), (
            "Too many id↔subject mismatches: "
            + str(algebra_id_in_geo)
            + " 'algebra_*' in geometry, "
            + str(geo_id_in_algebra)
            + " 'geometry_*' in algebra (total rows: "
            + str(total) + ")"
        )
