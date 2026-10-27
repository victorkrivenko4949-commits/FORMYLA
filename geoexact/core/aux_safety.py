"""Подстраховка aux-режима: не оставлять пользователя со схемой.

Если чертёж с дополнительными построениями не удался (схема по ключевым
словам или провал конвейера), а до будильника воркера (signal.alarm в
worker.py) времени ещё хватает — построить базовый чертёж без доп.
построений и показать его с явным объяснением. Aux-режим сильнее меняет
план формализатора, поэтому «без aux» нередко проходит там, где «с aux»
падает (прод-кейс 27.10.2026: трапеция с aux — схема, без aux — точно).

Успешные результаты не трогаются; при нехватке времени или если базовый
чертёж не лучше — возвращается исходная попытка aux (схема лучше ничего).
Суффикс версии НЕ поднимается: поведение меняется только для некэшируемых
исходов (схема/провал), кэш валиден как есть.
"""
from __future__ import annotations

import functools
import os
import signal
import time

GEOEXACT_AUXSAFETY = os.environ.get("GEOEXACT_AUXSAFETY", "1")
ENABLED = GEOEXACT_AUXSAFETY != "0"

# Минимальный остаток будильника воркера, при котором повтор ещё имеет
# смысл: обычный чертёж ~50 с, сложный ~100, плюс запас на рендер.
# Меньше — не рискуем: убитый будильником повтор потерял бы и схему.
MIN_RETRY_BUDGET = 75.0


def _alarm_remaining() -> float:
    """Сколько секунд осталось до SIGALRM воркера (0 — будильника нет:
    локальный запуск/тесты, ограничения только внутренние TIME_LIMIT)."""
    try:
        return float(signal.getitimer(signal.ITIMER_REAL)[0])
    except (AttributeError, ValueError, OSError):  # не POSIX — повтора не будет
        return 0.0


def _wrap_generate(orig, pipeline_module):
    @functools.wraps(orig)
    def generate(problem, with_aux=False, **kwargs):
        res = orig(problem, with_aux, **kwargs)
        if (not with_aux or not isinstance(problem, str)
                or not str(problem).strip()):
            return res
        if res.ok and res.verification != "sketch":
            return res                       # нормальный чертёж — не трогаем
        remaining = _alarm_remaining()
        if 0 < remaining < MIN_RETRY_BUDGET:
            return res                       # будильник близко: не рискуем
        kwargs.pop("aux_history", None)
        limit_backup = getattr(pipeline_module, "TIME_LIMIT", None)
        try:
            if remaining > 0:                # вписываем повтор в остаток будильника
                pipeline_module.TIME_LIMIT = max(20.0, remaining - 10.0)
            base = orig(problem, False, **kwargs)
        finally:
            if limit_backup is not None:
                pipeline_module.TIME_LIMIT = limit_backup
        if not (base.ok and base.verification != "sketch"):
            return res                        # базовый не лучше — оставляем aux
        code = (res.reason or res.stage or "").strip()
        detail = (res.detail or "").strip()
        why = (f" ({code}: {detail})" if code and detail
               else f" ({code or detail})" if (code or detail) else "")
        warn = ("AUX_FALLBACK: чертёж с дополнительными построениями построить"
                " не удалось" + why
                + ". Показан базовый чертёж без дополнительных построений.")
        base.warnings = list(base.warnings or []) + [warn]
        return base

    generate._aux_safety = True
    generate._original = orig
    return generate


def install(pipeline_module) -> bool:
    """Обернуть pipeline.generate. Повторный вызов — no-op. Выключается
    GEOEXACT_AUXSAFETY=0."""
    if not ENABLED:
        return False
    ok = False
    fn = getattr(pipeline_module, "generate", None)
    if fn is not None and not getattr(fn, "_aux_safety", False):
        pipeline_module.generate = _wrap_generate(fn, pipeline_module)
        ok = True
    return ok
