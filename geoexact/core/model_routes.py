# -*- coding: utf-8 -*-
"""Маршрутизация формализатора на deepseek-v4-pro (оба пути, A и B).

Перевод по просьбе пользователя после вырожденной конфигурации в живой
генерации (задача 2: прямоугольный fallback-чертёж при «остроугольном»
треугольнике). Источник исходного сбоя не установлен: план формализатора
не сохраняется, гипотеза — потерянная качественная фраза условия.

Путь B раньше сознательно шёл на flash (FLASH_NO_THINKING_V1: pro с thinking
«думал» 3-4 минуты, пользователь не дожидался). С переводом на pro время
доп. построений может вырасти — осознанное решение пользователя.

aux_plan (доп. построение отдельным шагом) уже идёт на deepseek-v4-pro
безусловно. Классификация и оценка сложности не меняются. Бюджетная защита
сохранена: при нехватке бюджета formalize деградирует pro→flash.

Кэш: к pipeline.ENGINE_VERSION дописывается суффикс — результаты, полученные
flash-формализатором, не выдаются за свежие.

Выключение: GEOEXACT_PRO_FORMALIZE=0 — возврат к исходной маршрутизации
(путь A-XL использовал pro и до перевода).
"""
import logging
import os
import sys

CACHE_SUFFIX = "+proFormalize1"

# (модель, лимит вывода). Лимиты путей сохранены; A-L поднят до 10000 — на L/XL
# включается thinking, токены рассуждения входят в лимит вывода.
_ROUTES = {
    ("A", "S"):  ("deepseek-v4-pro", 4000),
    ("A", "M"):  ("deepseek-v4-pro", 6000),
    ("A", "L"):  ("deepseek-v4-pro", 10000),
    ("A", "XL"): ("deepseek-v4-pro", 10000),
    ("B", "S"):  ("deepseek-v4-pro", 6000),
    ("B", "M"):  ("deepseek-v4-pro", 10000),
    ("B", "L"):  ("deepseek-v4-pro", 10000),
    ("B", "XL"): ("deepseek-v4-pro", 10000),
}


def install(llm_module, pipeline_module=None):
    """Патчит llm.ROUTES для обоих путей, дописывает суффикс версии кэша и
    оборачивает llm._chat журналом фактической модели (без текста задачи —
    подтверждение живых запросов по логам сервиса)."""
    if os.getenv("GEOEXACT_PRO_FORMALIZE", "1") == "0":
        return
    llm_module.ROUTES.update(_ROUTES)
    ver = getattr(pipeline_module, "ENGINE_VERSION", None) if pipeline_module else None
    if ver and CACHE_SUFFIX not in ver:
        pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
    _install_call_log(llm_module)


def _install_call_log(llm_module):
    real = getattr(llm_module, "_chat", None)
    if real is None or getattr(real, "_pro_call_log", False):
        return
    # свой handler + уровень: в воркер-подпроцессе root-логгер не настроен,
    # INFO без handler теряется молча — журнал вызовов обязан доходить до stderr
    logger = logging.getLogger("geoexact.routes")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    def logged_chat(*a, **k):
        out = real(*a, **k)
        try:
            model = a[1] if len(a) > 1 else k.get("model", "?")
            stage = a[5] if len(a) > 5 else k.get("stage", "?")
            logging.getLogger("geoexact.routes").info(
                "llm call model=%s stage=%s", model, stage)
        except Exception:  # noqa: BLE001 - журнал не должен ломать вызов
            pass
        return out

    logged_chat._pro_call_log = True
    llm_module._chat = logged_chat
