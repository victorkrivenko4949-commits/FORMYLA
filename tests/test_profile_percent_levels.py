# -*- coding: utf-8 -*-
"""
Тесты PR «percent_to_level + calibration» (ТЗ от 2026-06-08).

Цели:
* `percent_to_level()` — граничные значения 0/20/21/40/41/60/61/80/81/100,
  None и значения вне [0,100].
* `compute_profile_completeness()`.
* `compute_target_level_from_pct()` / `compute_stretch_level_from_pct()`.
* `compute_slot_allocation()` — кейсы 0/7, 1/7, 4/7, 7/7.
* `select_calibration_topics()` — ротация по weekday-seed.
* `build_profile()` через моки SQLAlchemy-запросов для кейсов:
  - 0/7 тестов -> 10 калибровочных слотов, fail-safe;
  - 1/7 тестов 30% по алгебре -> ~3 measured + ~7 калибровочных, уровни OK;
  - 7/7 тестов -> старая логика (regression — не сломано).
* `running_pct.compute_running_pct()` — взвешенный декрей и difficulty-вес.
* `_resolve_class_level()` — НЕ возвращает 9 по умолчанию.

Тесты не зависят от реальной БД: build_profile-тесты мокаются.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from daily_tasks import profile as profile_mod
from daily_tasks.profile import (
    CALIBRATION_START_LEVEL,
    LEVEL_PULL_DOWN,
    MAX_TASK_LEVEL,
    MIN_TASK_LEVEL,
    PERCENT_LEVEL_THRESHOLDS,
    ProfileBuildError,
    compute_profile_completeness,
    compute_slot_allocation,
    compute_stretch_level_from_pct,
    compute_target_level_from_pct,
    percent_to_level,
    select_calibration_topics,
)
from daily_tasks.running_pct import (
    HALF_LIFE_DAYS,
    MIN_ANSWERS_FOR_MEASURED,
    compute_running_pct,
)


# ══════════════════════════════════════════════════════════════════════
# percent_to_level — граничные значения
# ══════════════════════════════════════════════════════════════════════


class TestPercentToLevel:
    """Маппинг 0–100% -> 1..5."""

    @pytest.mark.parametrize(
        "pct,expected",
        [
            # нижняя граница каждого диапазона
            (0, 1),
            (20, 1),
            (21, 2),
            (40, 2),
            (41, 3),
            (60, 3),
            (61, 4),
            (80, 4),
            (81, 5),
            (100, 5),
            # точно на стыке
            (20.0, 1),
            (40.0001, 3),  # > 40 -> lvl 3
        ],
    )
    def test_boundaries(self, pct, expected):
        assert percent_to_level(pct) == expected

    def test_none_returns_none(self):
        assert percent_to_level(None) is None

    def test_below_zero_clamps_to_lvl1(self):
        assert percent_to_level(-50) == 1

    def test_above_hundred_clamps_to_max(self):
        assert percent_to_level(150) == 5

    def test_non_numeric_returns_none(self):
        assert percent_to_level("not-a-number") is None  # type: ignore[arg-type]

    def test_thresholds_constant_is_5_levels(self):
        # защита от случайного изменения шкалы
        levels = [lvl for _, lvl in PERCENT_LEVEL_THRESHOLDS]
        assert sorted(set(levels)) == [1, 2, 3, 4, 5]


# ══════════════════════════════════════════════════════════════════════
# target_level / stretch_level
# ══════════════════════════════════════════════════════════════════════


class TestTargetStretchLevel:
    def test_target_below_measured_by_pull_down(self):
        # pct=30% -> pct_level=2 -> target = 2 - 1 = 1
        assert compute_target_level_from_pct(30) == 1

    def test_stretch_above_measured(self):
        # pct=30% -> pct_level=2 -> stretch = 2 + 1 = 3
        assert compute_stretch_level_from_pct(30) == 3

    def test_target_clamped_to_min_level(self):
        assert compute_target_level_from_pct(0) == MIN_TASK_LEVEL

    def test_stretch_clamped_to_max_level(self):
        assert compute_stretch_level_from_pct(100) <= MAX_TASK_LEVEL

    def test_none_returns_none(self):
        assert compute_target_level_from_pct(None) is None
        assert compute_stretch_level_from_pct(None) is None


# ══════════════════════════════════════════════════════════════════════
# profile_completeness
# ══════════════════════════════════════════════════════════════════════


class TestCompleteness:
    @pytest.mark.parametrize(
        "measured,total,expected",
        [
            (0, 7, 0.0),
            (1, 7, round(1 / 7, 4)),
            (4, 7, round(4 / 7, 4)),
            (7, 7, 1.0),
            (10, 7, 1.0),  # clamp
            (-1, 7, 0.0),
            (3, 0, 0.0),  # защита от деления на 0
        ],
    )
    def test_completeness(self, measured, total, expected):
        assert compute_profile_completeness(measured, total) == expected


# ══════════════════════════════════════════════════════════════════════
# slot_allocation: пропорция measured vs calibration
# ══════════════════════════════════════════════════════════════════════


class TestSlotAllocation:
    def test_zero_measured_all_calibration(self):
        m, c = compute_slot_allocation(measured_count=0, total_topics=7)
        assert (m, c) == (0, 10)

    def test_full_measured_no_calibration(self):
        m, c = compute_slot_allocation(measured_count=7, total_topics=7)
        assert (m, c) == (10, 0)

    def test_one_of_seven_min_3_measured(self):
        m, c = compute_slot_allocation(measured_count=1, total_topics=7)
        assert m >= 3
        assert m + c == 10
        assert c >= 1

    def test_total_always_10(self):
        for mc in range(0, 8):
            m, c = compute_slot_allocation(measured_count=mc, total_topics=7)
            assert m + c == 10, f"measured_count={mc} -> {m}+{c} != 10"

    def test_monotone(self):
        """Чем больше пройдено, тем больше measured-слотов."""
        prev_m = -1
        for mc in range(0, 8):
            m, _ = compute_slot_allocation(measured_count=mc, total_topics=7)
            assert m >= prev_m
            prev_m = m


# ══════════════════════════════════════════════════════════════════════
# select_calibration_topics — ротация по дням
# ══════════════════════════════════════════════════════════════════════


class TestCalibrationRotation:
    TOPICS = ["Алгебра. A", "Геометрия. G", "Логика. L",
              "Теория чисел. N", "Комбинаторика. C"]

    def test_deterministic_for_same_seed(self):
        a = select_calibration_topics(self.TOPICS, n=2, rotation_seed=3)
        b = select_calibration_topics(self.TOPICS, n=2, rotation_seed=3)
        assert a == b

    def test_different_seeds_different_topics(self):
        a = select_calibration_topics(self.TOPICS, n=2, rotation_seed=0)
        b = select_calibration_topics(self.TOPICS, n=2, rotation_seed=1)
        # хотя бы один элемент должен сдвинуться
        assert a != b

    def test_n_zero_returns_empty(self):
        assert select_calibration_topics(self.TOPICS, n=0, rotation_seed=0) == []

    def test_empty_pool_returns_empty(self):
        assert select_calibration_topics([], n=5, rotation_seed=0) == []

    def test_n_bigger_than_pool(self):
        out = select_calibration_topics(self.TOPICS, n=10, rotation_seed=0)
        assert len(out) == len(self.TOPICS)

    def test_week_covers_all_topics(self):
        """За 7 дней (seed 0..6) должны быть упомянуты все темы — хотя бы
        как первый элемент. Это критично для ТЗ «за неделю закрыть профиль»."""
        seen = set()
        for seed in range(7):
            out = select_calibration_topics(self.TOPICS, n=2, rotation_seed=seed)
            seen.update(out)
        assert seen == set(self.TOPICS)


# ══════════════════════════════════════════════════════════════════════
# running_pct (вариант B): взвешенное среднее
# ══════════════════════════════════════════════════════════════════════


class TestRunningPct:
    def _make_answers(self, correctness, difficulty=3, days_ago=None):
        """Сделать список фейковых ответов."""
        now = datetime(2026, 6, 8)
        if days_ago is None:
            days_ago = [0] * len(correctness)
        return [
            {
                "is_correct": c,
                "difficulty_level": difficulty,
                "answered_at": now - timedelta(days=d),
            }
            for c, d in zip(correctness, days_ago)
        ], now

    def test_no_answers_returns_none(self):
        pct, n, measured = compute_running_pct([], now=datetime.utcnow())
        assert pct is None
        assert n == 0
        assert measured is False

    def test_all_correct_recent_gives_100(self):
        answers, now = self._make_answers([True] * 10)
        pct, n, measured = compute_running_pct(answers, now=now)
        assert pct == 100.0
        assert n == 10
        assert measured is True

    def test_all_wrong_gives_0(self):
        answers, now = self._make_answers([False] * 10)
        pct, n, _ = compute_running_pct(answers, now=now)
        assert pct == 0.0
        assert n == 10

    def test_below_min_threshold_not_measured(self):
        few = MIN_ANSWERS_FOR_MEASURED - 1
        answers, now = self._make_answers([True] * few)
        pct, n, measured = compute_running_pct(answers, now=now)
        assert n == few
        assert measured is False
        assert pct == 100.0  # сам процент считается, просто measured=False

    def test_difficulty_weight_increases_impact(self):
        """Правильно решённая сложная задача даёт больший % чем простая."""
        # 10 ответов, все правильные, сложность 5 (max)
        ans_hard, now = self._make_answers([True] * 10, difficulty=5)
        pct_hard, _, _ = compute_running_pct(ans_hard, now=now)

        # Смешиваем: 1 неверный на lvl 5 + 9 верных на lvl 1 — суммарный pct
        # должен быть меньше 100, так как тяжёлая «ошибка» весит сильнее.
        mixed = [
            {"is_correct": False, "difficulty_level": 5, "answered_at": now},
        ] + [
            {"is_correct": True, "difficulty_level": 1, "answered_at": now}
            for _ in range(9)
        ]
        pct_mixed, _, _ = compute_running_pct(mixed, now=now)
        assert pct_mixed < pct_hard
        assert pct_mixed < 90.0  # серьёзная просадка из-за тяжёлой ошибки

    def test_old_answers_decay(self):
        """Старый ответ должен влиять меньше свежего."""
        now = datetime(2026, 6, 8)
        # Все правильные, но половина свежие, половина — год назад (декрей)
        answers = (
            [{"is_correct": True, "difficulty_level": 3, "answered_at": now}
             for _ in range(5)]
            + [{"is_correct": False, "difficulty_level": 3,
                "answered_at": now - timedelta(days=int(HALF_LIFE_DAYS * 4))}
               for _ in range(5)]
        )
        pct, _, _ = compute_running_pct(answers, now=now)
        # Свежие ответы (правильные) весят сильно больше старых (неверных) ->
        # pct заметно выше 50.
        assert pct > 70.0


# ══════════════════════════════════════════════════════════════════════
# _resolve_class_level: без silent fallback
# ══════════════════════════════════════════════════════════════════════


class TestResolveClassLevel:
    def test_missing_grade_raises(self):
        user = SimpleNamespace(id=42, preferred_grade=None)
        with pytest.raises(ProfileBuildError) as ei:
            profile_mod._resolve_class_level(user)  # type: ignore[arg-type]
        assert "preferred_grade" in str(ei.value) or "класс" in str(ei.value).lower()

    def test_empty_string_grade_raises(self):
        user = SimpleNamespace(id=42, preferred_grade="")
        with pytest.raises(ProfileBuildError):
            profile_mod._resolve_class_level(user)  # type: ignore[arg-type]

    def test_garbage_grade_raises(self):
        user = SimpleNamespace(id=42, preferred_grade="abc")
        with pytest.raises(ProfileBuildError):
            profile_mod._resolve_class_level(user)  # type: ignore[arg-type]

    def test_out_of_range_raises(self):
        user = SimpleNamespace(id=42, preferred_grade=15)
        with pytest.raises(ProfileBuildError):
            profile_mod._resolve_class_level(user)  # type: ignore[arg-type]

    def test_valid_grade_returns_int(self):
        user = SimpleNamespace(id=42, preferred_grade="9")
        assert profile_mod._resolve_class_level(user) == 9  # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════════════
# build_profile() — интеграция с мок-БД
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_grade9_user():
    """User c grade=9."""
    return SimpleNamespace(id=1, preferred_grade=9)


@pytest.fixture
def grade9_topics():
    """Точный набор 7 тем 9 класса (как в ADAPTIVE_TOPICS_BY_GRADE[9])."""
    from services.adaptive_topics_registry import ADAPTIVE_TOPICS_BY_GRADE
    return [t["db_topic"] for t in ADAPTIVE_TOPICS_BY_GRADE[9]]


def _patch_user_query(monkeypatch, user):
    """Подменить User так, чтобы User.query.get(user_id) -> user.

    Замена через class-stub, чтобы избежать ленивого lookup
    ``FSA __fsa__.session()`` (требует Flask app context).
    """
    fake_query = MagicMock()
    fake_query.get = MagicMock(return_value=user)
    stub = type("UserStub", (), {"query": fake_query})
    monkeypatch.setattr(profile_mod, "User", stub)


def _patch_db_session_empty(monkeypatch):
    """Замокать db.session так, чтобы chain .query(..).filter(..).all() = []."""
    fake_q = MagicMock()
    # Универсальный chain: query/join/filter/order_by/limit/all/first
    fake_q.query.return_value = fake_q
    fake_q.join.return_value = fake_q
    fake_q.filter.return_value = fake_q
    fake_q.order_by.return_value = fake_q
    fake_q.limit.return_value = fake_q
    fake_q.all.return_value = []
    fake_q.first.return_value = None
    fake_db = SimpleNamespace(session=fake_q)
    monkeypatch.setattr(profile_mod, "db", fake_db)


def _patch_test_results(monkeypatch, results_list):
    """Подменить _load_topic_test_results (и совместимые обёртки)."""
    results_map: dict = {}
    for r in results_list:
        if r.tasks_total:
            results_map[r.topic] = {
                "correct": r.tasks_correct,
                "total": r.tasks_total,
                "final_level": r.final_level,
                "pct": round(100 * r.tasks_correct / r.tasks_total, 2),
                "completed_at": None,
            }
    monkeypatch.setattr(
        profile_mod, "_load_topic_test_results",
        lambda uid, cl: results_map,
    )
    # Обёртки _load_topic_test_pct / _load_topic_final_level
    # используют _load_topic_test_results — патчить их не нужно,
    # но оставляем для совместимости, если кто-то вызовет напрямую.
    pct_map = {t: d["pct"] for t, d in results_map.items()}
    level_map = {
        t: d["final_level"] for t, d in results_map.items()
        if d["final_level"] is not None
    }
    monkeypatch.setattr(
        profile_mod, "_load_topic_test_pct",
        lambda uid, cl: pct_map,
    )
    monkeypatch.setattr(
        profile_mod, "_load_topic_final_level",
        lambda uid, cl: level_map,
    )


def _patch_running_pct_none(monkeypatch):
    """В большинстве кейсов running_pct не должна срабатывать."""
    monkeypatch.setattr(
        profile_mod, "compute_topic_running_pct",
        lambda uid, db_topic: (None, 0, False),
    )


class TestBuildProfile07:
    """Кейс 0/7 пройдено: все темы — калибровочные."""

    def test_zero_tests(self, monkeypatch, mock_grade9_user, grade9_topics):
        _patch_user_query(monkeypatch, mock_grade9_user)
        _patch_db_session_empty(monkeypatch)
        _patch_test_results(monkeypatch, [])
        _patch_running_pct_none(monkeypatch)

        p = profile_mod.build_profile(user_id=1, today=date(2026, 6, 8))

        assert p["class_level"] == 9
        assert p["profile_completeness"] == 0.0
        assert p["measured_topics_count"] == 0
        # все темы — кандидаты в калибровку
        assert p["calibration_topics_count"] == len(grade9_topics)
        # при 0 тестов берутся все темы (CALIBRATION_TOPICS_PER_DAY_WHEN_EMPTY)
        assert 0 < len(p["calibration_topics"]) <= len(grade9_topics)
        # slot_allocation: 0 measured, 10 calibration
        assert p["slot_allocation"]["measured"] == 0
        assert p["slot_allocation"]["calibration"] == 10
        # каждая тема в topics_full измерена=False
        assert all(t["measured"] is False for t in p["topics_full"])
        assert all(t["calibration"] is True for t in p["topics_full"])
        # weak_topics не пустой (внутри — калибровочные)
        assert 1 <= len(p["weak_topics"]) <= len(grade9_topics)
        # калибровочные темы: target_level = calibration_target_level(5) = 5
        # (шкала 1..8, для 9 класса ожидаемый уровень 5)
        cal_expected = profile_mod.calibration_target_level(
            profile_mod._class_expected_level(9)
        )
        for t in p["weak_topics"]:
            if t.get("calibration"):
                assert t["target_level"] == cal_expected


class TestBuildProfile17:
    """Кейс 1/7: 30% по алгебре -> ~3 measured + ~7 калибровочных."""

    def test_one_test_algebra_30pct(
        self, monkeypatch, mock_grade9_user, grade9_topics
    ):
        _patch_user_query(monkeypatch, mock_grade9_user)
        _patch_db_session_empty(monkeypatch)

        # один тест по «Алгебра. Квадратные уравнения, Виет, параметры»
        # tasks_correct=8 из 25 -> pct ≈ 32%
        algebra_topic = next(
            t for t in grade9_topics if t.startswith("Алгебра")
        )
        results = [
            SimpleNamespace(
                topic=algebra_topic,
                class_level=9,
                final_level=2,
                tasks_correct=8,
                tasks_total=25,
            ),
        ]
        _patch_test_results(monkeypatch, results)
        _patch_running_pct_none(monkeypatch)

        p = profile_mod.build_profile(user_id=1, today=date(2026, 6, 8))

        assert p["class_level"] == 9
        assert p["measured_topics_count"] == 1
        assert p["profile_completeness"] == round(1 / 7, 4)

        # измеренная тема — алгебра
        algebra = next(t for t in p["topics_full"] if t["topic"] == algebra_topic)
        assert algebra["measured"] is True
        assert algebra["pct"] == 32.0  # 8/25
        assert algebra["level_from_pct"] == 2   # 21–40% -> lvl 2
        # score_to_target_level: final_level=2, ratio=0.32 -> base-1=1
        assert algebra["target_level"] == 1
        # compute_level_window для target=1: [1, 3]
        assert algebra["stretch_level"] == 3
        assert algebra["floor_level"] == 1

        # все остальные — калибровка
        non_algebra = [t for t in p["topics_full"] if t["topic"] != algebra_topic]
        assert all(t["measured"] is False for t in non_algebra)
        assert all(t["calibration"] is True for t in non_algebra)

        # slot_allocation: ≥3 measured, всего 10
        assert p["slot_allocation"]["measured"] >= 3
        assert p["slot_allocation"]["measured"] + p["slot_allocation"]["calibration"] == 10

        # weak_topics содержит и алгебру (measured), и часть калибровочных
        weak_topics_ids = [t["topic"] for t in p["weak_topics"]]
        assert algebra_topic in weak_topics_ids
        cal_in_weak = [
            t for t in p["weak_topics"] if t["calibration"] is True
        ]
        assert len(cal_in_weak) >= 1, "должна быть минимум одна калибровочная тема"

        # калибровочные темы: target_level = calibration_target_level(5) = 5
        cal_expected = profile_mod.calibration_target_level(
            profile_mod._class_expected_level(9)
        )
        for t in p["weak_topics"]:
            if t["calibration"]:
                assert t["target_level"] == cal_expected


class TestBuildProfile77:
    """Кейс 7/7: regression — старый сценарий не сломан."""

    def test_full_profile_no_calibration(
        self, monkeypatch, mock_grade9_user, grade9_topics
    ):
        _patch_user_query(monkeypatch, mock_grade9_user)
        _patch_db_session_empty(monkeypatch)
        # имитируем 7 тестов с разными %
        pcts = [10, 30, 50, 70, 90, 25, 60]
        results = []
        for topic, pct in zip(grade9_topics, pcts):
            results.append(SimpleNamespace(
                topic=topic, class_level=9, final_level=3,
                tasks_correct=int(pct / 4),  # из 25
                tasks_total=25,
            ))
        _patch_test_results(monkeypatch, results)
        _patch_running_pct_none(monkeypatch)

        p = profile_mod.build_profile(user_id=1, today=date(2026, 6, 8))

        assert p["measured_topics_count"] == 7
        assert p["profile_completeness"] == 1.0
        # никаких калибровочных кандидатов
        assert p["calibration_topics_count"] == 0
        assert p["calibration_topics"] == []
        # все 10 слотов — measured
        assert p["slot_allocation"]["measured"] == 10
        assert p["slot_allocation"]["calibration"] == 0
        # каждая тема — measured
        assert all(t["measured"] is True for t in p["topics_full"])
        assert all(t["calibration"] is False for t in p["topics_full"])
        # weak_topics: max 7 measured тем (приоритет слабым)
        assert len(p["weak_topics"]) <= 7
        # тема с pct=10 (самая слабая) — в weak с высоким priority
        weakest = min(p["topics_full"], key=lambda t: t["pct"])
        assert weakest["topic"] in [t["topic"] for t in p["weak_topics"]]
        # strong_topics: проверяем что есть хоть один strong и все measured
        assert len(p["strong_topics"]) > 0
        assert all(t.get("measured") for t in p["strong_topics"])


# ══════════════════════════════════════════════════════════════════════
# Smoke: убедиться что профиль не падает при моках
# ══════════════════════════════════════════════════════════════════════


def test_build_profile_does_not_crash_on_empty_db(monkeypatch):
    """Защита от регрессии: ни при каких комбинациях моков не должно падать."""
    user = SimpleNamespace(id=1, preferred_grade=8)
    _patch_user_query(monkeypatch, user)
    _patch_db_session_empty(monkeypatch)
    monkeypatch.setattr(profile_mod, "_load_topic_test_pct", lambda u, c: {})
    monkeypatch.setattr(profile_mod, "_load_topic_final_level", lambda u, c: {})
    monkeypatch.setattr(
        profile_mod, "compute_topic_running_pct",
        lambda uid, db_topic: (None, 0, False),
    )
    p = profile_mod.build_profile(user_id=1, today=date(2026, 6, 8))
    assert p["class_level"] == 8
    assert isinstance(p["weak_topics"], list)
    assert isinstance(p["topics_full"], list)
    assert p["measured_topics_count"] == 0
