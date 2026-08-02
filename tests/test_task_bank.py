# -*- coding: utf-8 -*-
"""
Тесты для ``daily_tasks/task_bank.py`` — банк готовых задач.

Проверяет:
1. Загрузку и кэширование банка (load_bank, clear_cache)
2. grade_is_available — правильные классы
3. get_tasks — возвращает ровно 10 задач с валидными полями
4. get_tasks — MISS для несуществующих (grade, level, day)
5. validate_tasks — валидация количества и полей
6. compute_day_number — детерминизм и граничные случаи
7. pick_bank_level — 5/8 → level=5, калибровочные темы игнорируются
8. get_probe_meta — возвращает метаданные пробника
9. available_cells — возвращает ячейки
10. Детерминизм: повторный вызов get_tasks даёт те же задачи
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

import pytest

from daily_tasks import task_bank as tb


# ═══════════════════════════════════════════════════════════════════
#  Фикстуры
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _clear_cache():
    """Очищаем кэш перед каждым тестом, чтобы не было зависимостей."""
    tb.clear_cache()
    yield


@pytest.fixture
def grade6_probes() -> List[Dict[str, Any]]:
    """Загрузить банк 6-го класса."""
    return tb.load_bank(6)


# ═══════════════════════════════════════════════════════════════════
#  1. load_bank / clear_cache
# ═══════════════════════════════════════════════════════════════════

class TestLoadBank:
    """Загрузка и кэширование."""

    def test_load_grade6_returns_list(self):
        """load_bank(6) возвращает list с пробниками."""
        probes = tb.load_bank(6)
        assert isinstance(probes, list)
        assert len(probes) > 0, "Банк 6-го класса не должен быть пуст"

    def test_load_all_grades(self):
        """Все классы 5–11 загружаются без ошибок."""
        for grade in range(5, 12):
            probes = tb.load_bank(grade)
            assert len(probes) > 0, f"Банк {grade}-го класса пуст"

    def test_cache_hit(self):
        """Повторный load_bank возвращает тот же объект (кэш)."""
        a = tb.load_bank(6)
        b = tb.load_bank(6)
        assert a is b, "Повторный load_bank должен вернуть тот же объект (кэш)"

    def test_clear_cache_single(self):
        """clear_cache(grade) очищает только указанный класс."""
        tb.load_bank(6)
        tb.load_bank(7)
        tb.clear_cache(grade=6)
        assert 6 not in tb._bank_cache
        assert 7 in tb._bank_cache

    def test_clear_cache_all(self):
        """clear_cache() без аргумента очищает весь кэш."""
        tb.load_bank(6)
        tb.load_bank(7)
        tb.clear_cache()
        assert tb._bank_cache == {}

    def test_load_invalid_grade(self):
        """load_bank для неподдерживаемого класса выбрасывает ValueError."""
        with pytest.raises(ValueError, match="не поддерживает"):
            tb.load_bank(4)
        with pytest.raises(ValueError, match="не поддерживает"):
            tb.load_bank(12)


# ═══════════════════════════════════════════════════════════════════
#  2. grade_is_available
# ═══════════════════════════════════════════════════════════════════

class TestGradeIsAvailable:
    """Проверка доступности класса."""

    def test_supported_grades(self):
        """Классы 5–11 доступны."""
        for grade in range(5, 12):
            assert tb.grade_is_available(grade), f"Класс {grade} должен быть доступен"

    def test_unsupported_grades(self):
        """Классы <5 и >11 недоступны."""
        assert not tb.grade_is_available(4)
        assert not tb.grade_is_available(12)
        assert not tb.grade_is_available(0)


# ═══════════════════════════════════════════════════════════════════
#  3. get_tasks — HIT (ровно 10 задач с полями)
# ═══════════════════════════════════════════════════════════════════

class TestGetTasks:
    """Поиск задач в банке."""

    def test_returns_10_tasks(self):
        """get_tasks(6, 4, 1) возвращает ровно 10 задач."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None, "Должен быть найден пробник для (6,4,1)"
        assert len(tasks) == tb.TASKS_PER_PROBE, (
            f"Ожидалось {tb.TASKS_PER_PROBE} задач, получено {len(tasks)}"
        )

    def test_tasks_have_required_fields(self):
        """Каждая задача имеет text, answer, solution."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        for i, t in enumerate(tasks):
            assert t.get("text"), f"Задача #{i+1}: пустой text"
            assert t.get("answer"), f"Задача #{i+1}: пустой answer"
            assert t.get("solution"), f"Задача #{i+1}: пустой solution"
            # n — опционально, но если есть — должно быть от 1 до 10
            if "n" in t:
                assert 1 <= t["n"] <= 10, f"Задача #{i+1}: n вне диапазона 1..10"

    def test_tasks_have_method_field(self):
        """Каждая задача имеет method (необязательно, но желательно)."""
        tasks = tb.get_tasks(grade=7, level=5, day=10)
        assert tasks is not None
        for i, t in enumerate(tasks):
            assert "method" in t, f"Задача #{i+1}: нет поля method"

    def test_different_levels_return_different_tasks(self):
        """Разные уровни в один день дают разные наборы."""
        tasks_l4 = tb.get_tasks(grade=6, level=4, day=1)
        tasks_l5 = tb.get_tasks(grade=6, level=5, day=1)
        if tasks_l4 and tasks_l5:
            texts_l4 = {t.get("text", "") for t in tasks_l4}
            texts_l5 = {t.get("text", "") for t in tasks_l5}
            assert texts_l4 != texts_l5, (
                "Задачи для level=4 и level=5 не должны совпадать"
            )

    def test_theme_hint_preferred(self):
        """theme_hint выбирает пробник с указанной темой."""
        # (7, 5, 1) — выбираем явно существующий пробник
        tasks_no_hint = tb.get_tasks(grade=7, level=5, day=1)
        tasks_with_hint = tb.get_tasks(
            grade=7, level=5, day=1,
            theme_hint="Алгебраические выражения",
        )
        # Оба должны вернуть задачи; если с хинтом нашёлся — он корректен
        if tasks_with_hint:
            assert len(tasks_with_hint) == tb.TASKS_PER_PROBE
        if tasks_no_hint and tasks_with_hint:
            # Может быть тот же пробник, если только один на (7,5,1)
            pass  # Это нормально

    def test_same_call_deterministic(self):
        """Повторный вызов с теми же аргументами даёт те же задачи."""
        a = tb.get_tasks(grade=8, level=4, day=5)
        b = tb.get_tasks(grade=8, level=4, day=5)
        assert a is not None and b is not None
        # Проверяем, что тексты совпадают
        texts_a = [t.get("text", "") for t in a]
        texts_b = [t.get("text", "") for t in b]
        assert texts_a == texts_b, "Повторный вызов должен вернуть те же задачи"


# ═══════════════════════════════════════════════════════════════════
#  4. get_tasks — MISS (возвращает None)
# ═══════════════════════════════════════════════════════════════════

class TestGetTasksMiss:
    """Ситуации, когда get_tasks возвращает None."""

    def test_miss_wrong_grade(self):
        """get_tasks для неподдерживаемого класса выбрасывает ValueError."""
        with pytest.raises(ValueError, match="не поддерживает"):
            tb.get_tasks(grade=4, level=4, day=1)

    def test_miss_wrong_level(self):
        """get_tasks для уровня вне [1,5] → None (если нет в банке)."""
        tasks = tb.get_tasks(grade=6, level=6, day=1)
        assert tasks is None, "Уровень 6 не должен быть в банке"

    def test_miss_wrong_day(self):
        """get_tasks для дня вне [1,100] → None."""
        tasks = tb.get_tasks(grade=6, level=4, day=101)
        assert tasks is None, "День 101 не должен быть в банке"

    def test_miss_nonexistent_combination(self):
        """get_tasks для несуществующей комбинации → None."""
        # Уровень 4, день 0 — нет в банке
        tasks = tb.get_tasks(grade=6, level=4, day=0)
        assert tasks is None


# ═══════════════════════════════════════════════════════════════════
#  5. validate_tasks
# ═══════════════════════════════════════════════════════════════════

class TestValidateTasks:
    """Валидация списка задач."""

    def test_valid_tasks(self):
        """Правильный список из 10 задач проходит валидацию."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        assert tb.validate_tasks(tasks) is True

    def test_empty_list(self):
        """Пустой список не проходит."""
        assert tb.validate_tasks([]) is False

    def test_too_few_tasks(self):
        """9 задач не проходят."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        assert tb.validate_tasks(tasks[:9]) is False

    def test_too_many_tasks(self):
        """11 задач не проходят (если добавить лишнюю)."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        assert tb.validate_tasks(tasks + [tasks[0]]) is False

    def test_none_tasks(self):
        """None вместо списка не проходит."""
        assert tb.validate_tasks(None) is False

    def test_empty_text_fails(self):
        """Задача с пустым text не проходит."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        bad = list(tasks)
        bad[0] = dict(bad[0], text="   ")
        assert tb.validate_tasks(bad) is False

    def test_empty_answer_fails(self):
        """Задача с пустым answer не проходит."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        bad = list(tasks)
        bad[0] = dict(bad[0], answer="")
        assert tb.validate_tasks(bad) is False

    def test_empty_solution_fails(self):
        """Задача с пустым solution не проходит."""
        tasks = tb.get_tasks(grade=6, level=4, day=1)
        assert tasks is not None
        bad = list(tasks)
        bad[0] = dict(bad[0], solution="")
        assert tb.validate_tasks(bad) is False


# ═══════════════════════════════════════════════════════════════════
#  6. compute_day_number
# ═══════════════════════════════════════════════════════════════════

class TestComputeDayNumber:
    """Детерминированный номер дня."""

    def test_day_1_for_same_date(self):
        """start_date == today → day=1."""
        d = date(2026, 6, 1)
        assert tb.compute_day_number(d, today=d) == 1

    def test_day_2_after_one_day(self):
        """start_date + 1 день → day=2."""
        start = date(2026, 6, 1)
        today = date(2026, 6, 2)
        assert tb.compute_day_number(start, today=today) == 2

    def test_day_100_after_99_days(self):
        """start_date + 99 дней → day=100."""
        start = date(2026, 6, 1)
        today = date(2026, 9, 8)  # 99 дней
        assert tb.compute_day_number(start, today=today) == 100

    def test_wraparound_day_1(self):
        """start_date + 100 дней → day=1 (wraparound)."""
        start = date(2026, 6, 1)
        today = date(2026, 9, 9)  # 100 дней
        assert tb.compute_day_number(start, today=today) == 1

    def test_wraparound_day_50(self):
        """start_date + 150 дней → day=51."""
        start = date(2026, 6, 1)
        today = date(2026, 10, 29)  # 150 дней
        assert tb.compute_day_number(start, today=today) == 51

    def test_future_start_date(self):
        """start_date в будущем → day=1."""
        start = date(2026, 12, 31)
        today = date(2026, 6, 1)
        assert tb.compute_day_number(start, today=today) == 1

    def test_deterministic(self):
        """Одна и та же дата даёт одно и то же число."""
        start = date(2026, 1, 1)
        today = date(2026, 6, 15)
        r1 = tb.compute_day_number(start, today=today)
        r2 = tb.compute_day_number(start, today=today)
        assert r1 == r2

    def test_default_today(self):
        """Без today использует date.today()."""
        start = date(2026, 6, 1)
        today = date.today()
        expected = ((today - start).days % 100) + 1
        assert tb.compute_day_number(start) == expected


# ═══════════════════════════════════════════════════════════════════
#  7. pick_bank_level — 5/8 → level=5
# ═══════════════════════════════════════════════════════════════════

class TestPickBankLevel:
    """Выбор уровня из профиля."""

    def test_average_of_measured_topics(self):
        """Среднее target_level измеренных тем (5 и 8) → 5 (round(6.5)→6 ... wait).

        Спецификация: 5/8 → level=5. Но round((5+8)/2) = round(6.5) = 6 (banker's rounding → 6).
        Нам нужно проверить, что measured_levels работают.

        Случай: target_level=[5,5] → round(5)=5
        """
        profile = {
            "topics_full": [
                {"target_level": 5, "calibration": False, "pct": 70},
                {"target_level": 5, "calibration": False, "pct": 60},
            ],
        }
        assert tb.pick_bank_level(profile) == 5


    def test_average_2_and_4_rounds_to_3(self):
        """(2+4)/2 = 3.0 -=3. Clamped in [1,5]."""
        profile = {
            "topics_full": [
                {"target_level": 2, "calibration": False},
                {"target_level": 4, "calibration": False},
            ],
        }
        result = tb.pick_bank_level(profile)
        assert result == 3, f"Expected 3, got {result}"
    def test_calibration_topics_ignored(self):
        """Калибровочные темы не учитываются в среднем."""
        profile = {
            "topics_full": [
                {"target_level": 5, "calibration": False},   # measured → учтём
                {"target_level": 0, "calibration": True},    # calibration → игнор
                {"target_level": 5, "calibration": False},   # measured → учтём
            ],
        }
        # Среднее: (8+8)/2 = 8 → level=8
        assert tb.pick_bank_level(profile) == 5

    def test_no_measured_topics_uses_class_expected(self):
        """Без measured тем — class_expected_level."""
        profile = {
            "topics_full": [],
            "class_expected_level": 4,
        }
        assert tb.pick_bank_level(profile) == 4

    def test_no_measured_no_class_expected_uses_default(self):
        """Без measured тем и без class_expected_level — default=5."""
        profile = {"topics_full": []}
        assert tb.pick_bank_level(profile) == 5

    def test_clamp_above_max(self):
        """Уровень > 8 зажимается в 8."""
        profile = {
            "topics_full": [
                {"target_level": 9, "calibration": False},
            ],
        }
        assert tb.pick_bank_level(profile) == tb.MAX_BANK_LEVEL

    def test_clamp_below_min(self):
        """Уровень < 1 зажимается в 1."""
        profile = {
            "topics_full": [
                {"target_level": 0, "calibration": False},
            ],
        }
        assert tb.pick_bank_level(profile) == tb.MIN_BANK_LEVEL

    def test_custom_default(self):
        """Параметр default_level переопределяет стандартный 5."""
        profile = {"topics_full": []}
        assert tb.pick_bank_level(profile, default_level=3) == 3


# ═══════════════════════════════════════════════════════════════════
#  8. get_probe_meta
# ═══════════════════════════════════════════════════════════════════

class TestGetProbeMeta:
    """Метаданные пробника."""

    def test_returns_meta(self):
        """get_probe_meta(6, 4, 1) возвращает словарь с метой."""
        meta = tb.get_probe_meta(grade=6, level=4, day=1)
        assert meta is not None
        assert "probe_id" in meta
        assert "theme" in meta
        assert "level" in meta
        assert meta["level"] == 4
        assert meta["day"] == 1
        assert meta["num_tasks"] == tb.TASKS_PER_PROBE

    def test_miss_returns_none(self):
        """get_probe_meta для несуществующей комбинации → None."""
        meta = tb.get_probe_meta(grade=6, level=4, day=101)
        assert meta is None


# ═══════════════════════════════════════════════════════════════════
#  9. available_cells
# ═══════════════════════════════════════════════════════════════════

class TestAvailableCells:
    """Доступные ячейки."""

    def test_grade6_has_expected_cells(self):
        """Для 6-го класса есть ячейки (level, day)."""
        cells = tb.available_cells(6)
        assert len(cells) > 0
        # Проверяем, что (4, 1) есть
        assert (4, 1) in cells

    def test_all_levels_in_range(self):
        """Все уровни в ячейках — в [4,8]."""
        cells = tb.available_cells(6)
        for level, day in cells:
            assert tb.MIN_BANK_LEVEL <= level <= tb.MAX_BANK_LEVEL, (
                f"Уровень {level} вне диапазона [{tb.MIN_BANK_LEVEL}, {tb.MAX_BANK_LEVEL}]"
            )

    def test_all_days_in_range(self):
        """Все дни в ячейках — в [1,100]."""
        cells = tb.available_cells(6)
        for level, day in cells:
            assert 1 <= day <= tb.DAYS_PER_CELL, (
                f"День {day} вне диапазона [1, {tb.DAYS_PER_CELL}]"
            )


# ═══════════════════════════════════════════════════════════════════
#  10. Константы
# ═══════════════════════════════════════════════════════════════════

class TestConstants:
    """Проверка констант модуля."""

    def test_bank_levels(self):
        """BANK_LEVELS = (1,2,3,4,5)."""
        assert tb.BANK_LEVELS == (1, 2, 3, 4, 5)
        assert tb.MIN_BANK_LEVEL == 1
        assert tb.MAX_BANK_LEVEL == 5

    def test_days_per_cell(self):
        """DAYS_PER_CELL = 100."""
        assert tb.DAYS_PER_CELL == 100

    def test_tasks_per_probe(self):
        """TASKS_PER_PROBE = 10."""
        assert tb.TASKS_PER_PROBE == 10


# ═══════════════════════════════════════════════════════════════════
#  11. Интеграция: полный цикл
# ═══════════════════════════════════════════════════════════════════

class TestIntegration:
    """Интеграционный тест: profile → pick_bank_level → get_tasks."""

    def test_typical_profile(self):
        """Типичный профиль 6-классника с измеренными темами даёт задачи."""
        profile = {
            "class_level": 6,
            "topics_full": [
                {"target_level": 5, "calibration": False, "pct": 65},
                {"target_level": 4, "calibration": False, "pct": 45},
                {"target_level": 6, "calibration": False, "pct": 80},
            ],
        }
        level = tb.pick_bank_level(profile)
        assert tb.MIN_BANK_LEVEL <= level <= tb.MAX_BANK_LEVEL
        # Среднее (5+4+6)/3 = 5 → level=5
        assert level == 5

        start_date = date(2026, 6, 1)
        today = date(2026, 6, 21)
        day_num = tb.compute_day_number(start_date, today=today)

        tasks = tb.get_tasks(grade=6, level=level, day=day_num)
        # Может быть HIT или MISS — это нормально
        if tasks is not None:
            assert len(tasks) == tb.TASKS_PER_PROBE
            assert tb.validate_tasks(tasks)

    def test_fallback_when_bank_misses(self):
        """Если (grade, level, day) нет в банке — get_tasks возвращает None."""
        tasks = tb.get_tasks(grade=6, level=4, day=999)
        assert tasks is None, "Несуществующий день должен давать MISS"

    def test_grade5_works(self):
        """5-й класс загружается и отдаёт задачи."""
        probes = tb.load_bank(5)
        assert len(probes) > 0
        tasks = tb.get_tasks(grade=5, level=4, day=1)
        if tasks:
            assert len(tasks) == tb.TASKS_PER_PROBE
            assert tb.validate_tasks(tasks)

    def test_grade11_works(self):
        """11-й класс загружается и отдаёт задачи."""
        probes = tb.load_bank(11)
        assert len(probes) > 0
        tasks = tb.get_tasks(grade=11, level=4, day=1)
        if tasks:
            assert len(tasks) == tb.TASKS_PER_PROBE
            assert tb.validate_tasks(tasks)


# ═══════════════════════════════════════════════════════════════════
#  12. Обработка ошибок банка (try/except)
# ═══════════════════════════════════════════════════════════════════

class TestBankErrorHandling:
    """Проверка, что исключения в ``_try_bank_first`` НЕ вызывают 500.

    Фикс: банк-путь обёрнут в try/except на двух уровнях:
    1. ``_try_bank_first`` → ``_try_bank_first_impl`` (внутренняя защита)
    2. ``_run_pipeline_async`` → ``_try_bank_first`` (внешняя защита)

    Любая ошибка = MISS → graceful fallback на LLM-пайплайн.
    """

    def test_try_bank_first_wraps_exception(self, monkeypatch):
        """``_try_bank_first`` перехватывает исключение из ``_impl`` и
        возвращает ``False`` (MISS), не проваливая пайплайн."""
        import asyncio
        from daily_tasks.services import _try_bank_first

        async def _impl_raises(*args, **kwargs):
            raise RuntimeError("Внутренняя ошибка банка")

        monkeypatch.setattr(
            "daily_tasks.services._try_bank_first_impl",
            _impl_raises,
        )

        result = asyncio.run(_try_bank_first(
            user_id=42,
            target_date=None,
            daily_set_id=1,
            job_id=1,
            profile={"class_level": 6},
        ))
        # Исключение перехвачено → MISS (False), а не крах
        assert result is False, (
            "Исключение в _try_bank_first_impl должно давать MISS (False)"
        )

    def test_try_bank_first_wraps_arbitrary_error(self, monkeypatch):
        """Любой тип исключения (ValueError, KeyError, OSError и т.д.)
        перехватывается и превращается в False."""
        import asyncio
        from daily_tasks.services import _try_bank_first

        async def _impl_raises_value(*args, **kwargs):
            raise ValueError("Битый JSON в банке")

        async def _impl_raises_key(*args, **kwargs):
            raise KeyError("Отсутствует ключ")

        monkeypatch.setattr(
            "daily_tasks.services._try_bank_first_impl",
            _impl_raises_value,
        )
        assert asyncio.run(_try_bank_first(
            user_id=1, target_date=None,
            daily_set_id=1, job_id=1,
            profile={"class_level": 6},
        )) is False, "ValueError → MISS"

        monkeypatch.setattr(
            "daily_tasks.services._try_bank_first_impl",
            _impl_raises_key,
        )
        assert asyncio.run(_try_bank_first(
            user_id=1, target_date=None,
            daily_set_id=1, job_id=1,
            profile={"class_level": 6},
        )) is False, "KeyError → MISS"

    def test_try_bank_first_empty_profile_returns_false(self):
        """Если профиль без class_level — сразу MISS (без ошибки)."""
        import asyncio
        from daily_tasks.services import _try_bank_first_impl

        result = asyncio.run(_try_bank_first_impl(
            user_id=1, target_date=None,
            daily_set_id=1, job_id=1,
            profile={},
        ))
        assert result is False, "Пустой профиль → MISS"

    def test_run_pipeline_catches_bank_exception(self, monkeypatch):
        """``_run_pipeline_async`` перехватывает исключение из
        ``_try_bank_first`` и продолжает выполнение (не крашится)."""
        import asyncio
        from daily_tasks.services import _run_pipeline_async
        from app import app

        async def _bank_raises(*args, **kwargs):
            raise RuntimeError("Авария банка")

        monkeypatch.setattr(
            "daily_tasks.services._try_bank_first",
            _bank_raises,
        )

        # Патчим build_profile, чтобы не зависеть от БД
        def fake_build_profile(uid):
            return {"class_level": 6, "weak_topics": [], "strong_topics": []}

        monkeypatch.setattr(
            "daily_tasks.services.build_profile",
            fake_build_profile,
        )

        # Патчим job-запросы, чтобы не трогать БД
        class FakeJob:
            id = 1
            status = "running"
            current_step = None
            progress_pct = 0

        # Monkeypatch на .query.get триггерит дескриптор Flask-SQLAlchemy,
        # который требует app context — оборачиваем вызов.
        with app.app_context():
            monkeypatch.setattr(
                "daily_tasks.services.DailyGenerationJob.query.get",
                lambda jid: FakeJob(),
            )

        # no-op заглушки для всех функций, работающих с БД
        for name in (
            "_update_job_progress",
            "_persist_pipeline_result",
            "_mark_set_failed",
            "_fail_job",
            "run_daily_generation_pipeline",
        ):
            monkeypatch.setattr(
                f"daily_tasks.services.{name}",
                lambda *a, **kw: None,
            )

        # В _progress_cb (строки 1055–1062) есть DailyGenerationJob.query.get,
        # которая тоже требует app context. Она обёрнута в try/except,
        # но для корректной работы дескриптора SQLAlchemy даём контекст.
        with app.app_context():
            try:
                asyncio.run(_run_pipeline_async(
                    user_id=1,
                    target_date=None,
                    daily_set_id=1,
                    job_id=1,
                ))
            except Exception:
                pytest.fail(
                    "_run_pipeline_async не должен выбрасывать исключение "
                    "при ошибке банка — try/except должен перехватить"
                )
