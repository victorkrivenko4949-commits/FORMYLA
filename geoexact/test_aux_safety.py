"""Подстраховка aux-режима (aux_safety): провал со схемой -> базовый чертёж.

Обёртка установлена при импорте geoexact.core (см. core/__init__.py);
здесь проверяется и логика обёртки напрямую (_wrap_generate), и полный
маршрут pipeline.generate -> _generate.
"""
from unittest.mock import patch

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import pipeline
from geoexact.core.aux_safety import _wrap_generate, MIN_RETRY_BUDGET
from geoexact.core.pipeline import Result

TEXT = ("В трапеции ABCD с основаниями AD и BC диагонали пересекаются в точке O. "
        "Известно, что BO:OD = 3:11. Найдите отношение площадей треугольников "
        "ABO и CDO.")


def _ok(with_aux):
    return Result(True, "9-render", "", "", svg="<svg/>", svg_base="<svg/>",
                  verification="exact", with_aux=with_aux)


def _sketch(with_aux):
    return Result(True, "9-render-sketch", "", "", svg="<svg/>", svg_base="<svg/>",
                  verification="sketch", with_aux=with_aux)


def _failed(with_aux):
    return Result(False, "4-formalize", "ARITY", "цель ratio ждёт 4 точек",
                  with_aux=with_aux)


def test_wrapper_installed():
    assert getattr(pipeline.generate, "_aux_safety", False)


def test_aux_failure_falls_back_to_base():
    calls = []

    def orig(problem, with_aux=False, **kwargs):
        calls.append(with_aux)
        return _failed(True) if with_aux else _ok(False)

    wrapped = _wrap_generate(orig, pipeline)
    res = wrapped(TEXT, True)
    assert calls == [True, False]                 # aux, затем базовый
    assert res.ok and res.verification == "exact"
    assert res.with_aux is False
    assert any("AUX_FALLBACK" in w for w in res.warnings)
    assert any("ARITY" in w for w in res.warnings)      # причина — в объяснении


def test_sketch_aux_falls_back_to_base():
    def orig(problem, with_aux=False, **kwargs):
        return _sketch(True) if with_aux else _ok(False)

    res = _wrap_generate(orig, pipeline)(TEXT, True)
    assert res.verification == "exact"
    assert any("AUX_FALLBACK" in w for w in res.warnings)


def test_good_aux_result_untouched():
    calls = []

    def orig(problem, with_aux=False, **kwargs):
        calls.append(with_aux)
        return _ok(True)

    res = _wrap_generate(orig, pipeline)(TEXT, True)
    assert calls == [True]                        # повтора не было
    assert not any("AUX_FALLBACK" in w for w in (res.warnings or []))


def test_base_no_better_keeps_aux_attempt():
    calls = []

    def orig(problem, with_aux=False, **kwargs):
        calls.append(with_aux)
        return _sketch(True) if with_aux else _sketch(False)

    res = _wrap_generate(orig, pipeline)(TEXT, True)
    assert calls == [True, False]
    assert res.verification == "sketch" and res.with_aux is True


def test_plain_mode_never_retries():
    calls = []

    def orig(problem, with_aux=False, **kwargs):
        calls.append(with_aux)
        return _failed(False)

    res = _wrap_generate(orig, pipeline)(TEXT, False)
    assert calls == [False]
    assert res is not None and not res.ok


def test_low_alarm_skips_retry():
    """Будильник воркера близко (остаток < MIN_RETRY_BUDGET) — повтора нет:
    убитый сигналом повтор потерял бы и схему."""
    import signal
    calls = []

    def orig(problem, with_aux=False, **kwargs):
        calls.append(with_aux)
        return _failed(True) if with_aux else _ok(False)

    signal.setitimer(signal.ITIMER_REAL, 5.0)     # меньше MIN_RETRY_BUDGET
    try:
        res = _wrap_generate(orig, pipeline)(TEXT, True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)   # снять будильник
    assert calls == [True]
    assert not res.ok


def test_alarm_budget_shrinks_time_limit():
    """Повтор вписывается в остаток будильника: TIME_LIMIT на повторе
    уменьшается и восстанавливается после."""
    import signal
    backup = pipeline.TIME_LIMIT
    limits = []

    def orig(problem, with_aux=False, **kwargs):
        limits.append(pipeline.TIME_LIMIT)
        return _failed(True) if with_aux else _ok(False)

    signal.setitimer(signal.ITIMER_REAL, 120.0)   # больше MIN_RETRY_BUDGET
    try:
        res = _wrap_generate(orig, pipeline)(TEXT, True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        assert pipeline.TIME_LIMIT == backup
    assert res.ok
    assert limits[0] == backup                    # первая попытка — обычный лимит
    assert limits[1] < backup                     # повтор — вписан в остаток


def test_pipeline_e2e_aux_failure_shows_base_drawing():
    """Полный маршрут: generate(aux) провалился в _generate -> обёртка
    повторяет без aux -> пользователь видит базовый чертёж с AUX_FALLBACK."""
    calls = []

    def fake_generate_inner(problem, with_aux=False, **kwargs):
        calls.append(with_aux)
        if with_aux:
            return _failed(True)
        return _ok(False)

    with patch.object(pipeline, "_generate", fake_generate_inner):
        result = pipeline.generate(TEXT, with_aux=True, use_cache=False)
    assert calls == [True, False]
    assert result.ok and result.stage == "9-render"
    assert any("основной чертёж" in w for w in (result.warnings or []))
