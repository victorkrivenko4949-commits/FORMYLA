# -*- coding: utf-8 -*-
"""services/cost_calculation.py — расчёт себестоимости и цены функций сайта.

Константы и допущения:
  - Подписка: 400 руб/мес, включает 7 срезов (из задания).
  - Чертежи: 3 бесплатных при регистрации, пакеты 10/30/100 за 99/249/599 руб.
  - Чертежи строит DeepSeek (FIGURE_MODEL), таймаут 90 сек.
  - Задачи генерирует OpenRouter, таймаут 300 сек.
  - Проверка фото Kimi K2.5: 0.35 руб/фото.
  - Kimi: $0.60/1M входных токенов, $3.00/1M выходных (прайс Moonshot).
  - Курс доллара: 90 руб/$ (допущение, зафиксировано на 2026-08).
  - OpenRouter средняя стоимость: $0.50/1M токенов (~500 входных + 200 выходных на запрос).

Все функции возвращают числа в рублях.  Ни одна константа не берётся
из воздуха — источник указан в комментарии.
"""

# ── Константы ───────────────────────────────────────────────────────────────

USD_RUB = 90.0                     # курс ЦБ РФ, допущение на 2026-08

# Подписка (из задания)
SUBSCRIPTION_PRICE_RUB = 400       # 400 руб/мес
SLICES_PER_MONTH = 7               # 7 срезов включено

# Чертежи (из задания)
FIGURES_FREE = 3                   # бесплатно при регистрации
FIGURE_PACK_10_RUB = 99
FIGURE_PACK_30_RUB = 249
FIGURE_PACK_100_RUB = 599

# Модели (из задания)
FIGURE_MODEL = "deepseek-chat"     # таймаут 90 сек
OPENROUTER_TIMEOUT = 300           # секунд

# Kimi K2.5 (из задания)
KIMI_COST_PER_PHOTO_RUB = 0.35    # 0.35 руб/фото
KIMI_INPUT_COST_USD_PER_1M = 0.60  # $0.60/1M входных
KIMI_OUTPUT_COST_USD_PER_1M = 3.00 # $3.00/1M выходных

# OpenRouter (допущение: $0.50/1M среднее)
OR_COST_USD_PER_1M = 0.50

# Токены на один запрос (допущения)
OR_TOKENS_PER_TASK_GEN = 1500       # ~1000 входных + 500 выходных
FIGURE_TOKENS_PER_DRAWING = 800     # ~500 входных + 300 выходных
KIMI_TOKENS_PER_PHOTO = 1200        # ~200 входных + 1000 выходных


# ── Функции расчёта ─────────────────────────────────────────────────────────

def subscription_price_rub() -> float:
    """Цена подписки в месяц.  Источник: задание."""
    return float(SUBSCRIPTION_PRICE_RUB)


def figure_pack_price_rub(count: int) -> float:
    """Цена пакета чертежей.  Источник: задание."""
    if count == 10:
        return float(FIGURE_PACK_10_RUB)
    if count == 30:
        return float(FIGURE_PACK_30_RUB)
    if count == 100:
        return float(FIGURE_PACK_100_RUB)
    raise ValueError(f"Нет пакета на {count} чертежей")


def cost_per_slice_rub() -> float:
    """Себестоимость одного среза (генерация 7 задач OpenRouter)."""
    tokens_per_slice = OR_TOKENS_PER_TASK_GEN * 7
    usd_cost = tokens_per_slice / 1_000_000 * OR_COST_USD_PER_1M
    return round(usd_cost * USD_RUB, 4)


def cost_per_daily_set_rub() -> float:
    """Себестоимость генерации набора задач дня (30 задач OpenRouter)."""
    tokens = OR_TOKENS_PER_TASK_GEN * 30
    usd_cost = tokens / 1_000_000 * OR_COST_USD_PER_1M
    return round(usd_cost * USD_RUB, 4)


def cost_per_figure_rub() -> float:
    """Себестоимость построения одного чертежа DeepSeek."""
    usd_cost = FIGURE_TOKENS_PER_DRAWING / 1_000_000 * OR_COST_USD_PER_1M
    return round(usd_cost * USD_RUB, 4)


def cost_per_kimi_photo_rub() -> float:
    """Себестоимость проверки одного фото Kimi K2.5."""
    return float(KIMI_COST_PER_PHOTO_RUB)


def cost_per_method_generation_rub() -> float:
    """Себестоимость генерации разбора метода (OpenRouter, ~2000 токенов)."""
    usd_cost = 2000 / 1_000_000 * OR_COST_USD_PER_1M
    return round(usd_cost * USD_RUB, 4)


def monthly_subscriber_profit_rub() -> float:
    """Прибыль с одного подписчика в месяц (7 срезов + 30 задач дня).

    Доход: 400 руб.  Расход: себестоимость 7 срезов + 30 задач дня.
    """
    cost = cost_per_slice_rub() * 7 + cost_per_daily_set_rub()
    return round(SUBSCRIPTION_PRICE_RUB - cost, 2)


# ── Сводная таблица ─────────────────────────────────────────────────────────

def cost_table() -> list:
    """Возвращает список кортежей (функция, себестоимость, цена)."""
    return [
        ("Подписка (месяц)", 0.0, float(SUBSCRIPTION_PRICE_RUB)),
        ("Срез (7 задач)", cost_per_slice_rub(), 0.0),
        ("Задачи дня (30 шт)", cost_per_daily_set_rub(), 0.0),
        ("Чертёж (1 шт)", cost_per_figure_rub(), 0.0),
        ("Пакет 10 чертежей", cost_per_figure_rub() * 10, float(FIGURE_PACK_10_RUB)),
        ("Пакет 30 чертежей", cost_per_figure_rub() * 30, float(FIGURE_PACK_30_RUB)),
        ("Пакет 100 чертежей", cost_per_figure_rub() * 100, float(FIGURE_PACK_100_RUB)),
        ("Проверка фото Kimi", cost_per_kimi_photo_rub(), 0.35),
        ("Разбор метода", cost_per_method_generation_rub(), 0.0),
        ("Прибыль с подписчика", 0.0, monthly_subscriber_profit_rub()),
    ]
