"""Полировка предупреждений (warnings_polish): пользователю — нормальный
язык без внутренних кодов; внутренние диагностики не показываются вовсе.

Обёртка установлена при импорте geoexact.core (самый внешний слой
pipeline.generate), здесь проверяется и логика напрямую, и полный маршрут.
"""
from unittest.mock import patch

import geoexact.core                       # обёртки устанавливаются при импорте
from geoexact.core import pipeline
from geoexact.core.warnings_polish import polish_warnings, _polish_one
from geoexact.core.pipeline import Result

TEXT = ("В трапеции ABCD с основаниями AD и BC диагонали пересекаются в точке O. "
        "Известно, что BO:OD = 3:11. Найдите отношение площадей треугольников "
        "ABO и CDO.")


def test_wrapper_installed():
    assert getattr(pipeline.generate, "_warn_polish", False)


def test_internal_diagnostics_dropped():
    assert _polish_one("UNDERDETERMINED: уравнений 2 < степеней свободы 5") is None
    assert _polish_one("CONVEXITY_INJECTED: добавлено 2 opposite_side") is None
    assert _polish_one("STATEMENT_MARK: медиана BM — половины отмечены") is None
    assert _polish_one("SKIPPED_SEGMENT: PQ") is None


def test_contract_warnings_rewritten_in_plain_language():
    w = _polish_one("TARGET_DROPPED: цель измерения некорректна; чертёж без измерения")
    assert w and "код" not in w.lower() and "TARGET" not in w
    assert "не удалось" in w and "полном решении" in w
    s = _polish_one("SKETCH: построен схематичный чертёж")
    assert s and "схематичный чертёж" in s and "SKETCH" not in s
    f = _polish_one("AUX_FALLBACK: не удалось (ARITY: цель ratio ждёт 4 точек)")
    assert f and "основной чертёж" in f and "AUX" not in f and "ARITY" not in f


def test_nested_codes_stripped():
    w = _polish_one("APPROXIMATE: не подтверждено автоматически: CEVIAN: медиана BM — M не середина")
    assert w and w.startswith("Автопроверка подтвердила не всё условие")
    assert "CEVIAN" not in w and "медиана BM" in w


def test_unknown_code_keeps_text_without_prefix():
    assert _polish_one("SOME_NEW_CHECK: точка X вне отрезка") == "точка X вне отрезка"
    assert _polish_one("WEIRD: ") is None                    # код без текста — убрать
    assert _polish_one("просто текст без кода") == "просто текст без кода"


def test_duplicates_removed():
    out = polish_warnings(["SKETCH: а", "SKETCH: а", "цель"])
    assert out == ["Показан схематичный чертёж по ключевым словам условия: пропорции "
                   "условные, сверьте чертёж с текстом задачи.", "цель"]


def test_pipeline_e2e_warnings_are_user_facing():
    """Полный маршрут: generate возвращает предупреждения без кодов и
    внутренних диагностик — пользователь видит только понятный русский."""

    def fake_generate_inner(problem, with_aux=False, **kwargs):
        return Result(True, "9-render", "", "", svg="<svg/>", verification="exact",
                      with_aux=with_aux,
                      warnings=["UNDERDETERMINED: уравнений 2 < степеней свободы 5",
                                "TARGET_DROPPED: цель измерения некорректна",
                                "STATEMENT_MARK: медиана BM — половины отмечены"])

    with patch.object(pipeline, "_generate", fake_generate_inner):
        result = pipeline.generate(TEXT, with_aux=True, use_cache=False)
    assert result.ok
    assert len(result.warnings) == 1
    w = result.warnings[0]
    assert "не удалось" in w and "полном решении" in w
    import re
    assert not re.search(r"[A-Z]{3,}", w.replace("ABC", "")), w
