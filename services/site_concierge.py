# -*- coding: utf-8 -*-
"""
Site Concierge — отдельный AI-помощник по навигации FORMYLA.

НЕ путать с ИИ-тьютором (`services/ai_tutor_v2.py`):
тьютор отвечает на математические задачи, концьерж — только про сайт
(тарифы, навигация, как начать, тех-поддержка).

Пайплайн ответа:
  1. Точное / нечёткое совпадение с intent из data/site_kb.json
     (порог ~80 %, через rapidfuzz если установлен, иначе difflib).
  2. Иначе — LLM (Claude Sonnet через OpenRouter) с системным
     промптом, который строго ограничивает скоуп («только про сайт»).
  3. Математические вопросы → редирект к ИИ-тьютору, не вызываем LLM.

Публичный API:
    answer_site_question(message: str, context: dict) -> dict
        Returns: {
            "answer": str,
            "suggested_actions": [{"label": str, "url": str}, ...],
            "source": "kb" | "llm" | "redirect",
            "intent_id": str | None,
        }
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# ── KB loader ────────────────────────────────────────────────────────────────

_KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'site_kb.json',
)


@lru_cache(maxsize=1)
def _load_kb() -> list:
    """Кэшированная загрузка knowledge base."""
    try:
        with open(_KB_PATH, 'r', encoding='utf-8') as f:
            kb = json.load(f)
        if not isinstance(kb, list):
            logger.error('site_kb.json is not a list')
            return []
        return kb
    except FileNotFoundError:
        logger.warning('site_kb.json not found at %s', _KB_PATH)
        return []
    except Exception as e:
        logger.exception('Failed to load site_kb.json: %s', e)
        return []


def reload_kb() -> None:
    """Принудительная инвалидация кэша (для тестов / админки)."""
    _load_kb.cache_clear()


# ── Math-detection (заворачиваем «математику» к тьютору) ─────────────────────

# Эвристика: формула / уравнение / типичные математические запросы.
_MATH_HINTS = [
    r'[xyzабвабст]\s*[\+\-=\^]\s*[\d\-]',     # «x+1=…», «a^2-b…»
    r'\^\s*\d',                               # x^2
    r'\bуравн[еия]',
    r'\bнеравенств',
    r'\bинтегр',
    r'\bпроизводн',
    r'\bлогарифм',
    r'\bкосинус', r'\bсинус', r'\bтангенс',
    r'\bдробь', r'\bдроб[еья]',
    r'\bкорен[ьья]\s+(из|кубич|квадратн)',
    r'\bтреугольн', r'\bокружност[ьи]',
    r'\bвероятност[ьи]',
    r'\bпроцент',
    r'\bдоказа',
    r'реши(те|)\s+(задач|уравн|неравенств)',
    r'найди(те|)\s+(значен|корн|сумм|разност)',
    r'\d+\s*[\+\-\*/=]\s*\d+',                # «12+5» / «3*4»
]
_MATH_RE = re.compile('|'.join(_MATH_HINTS), re.IGNORECASE)

# Слова, говорящие что речь про сайт (анти-фолз-позитив математики).
_SITE_HINTS_RE = re.compile(
    r'тариф|подписк|оплат|цен[аыу]|стоит|стоимост|'
    r'тренаж[её]р|сайт|регистрац|акк[ау]нт|профиль|'
    r'войти|выход|пробник|задани[яе]\s+дн[яе]|настройк|'
    r'отмен|откат|VPN|карт[аыу]|купить|вернуть|'
    r'родител|ребен|ребён|класс|grade|выбрать\s+класс',
    re.IGNORECASE,
)


def _looks_like_math(text: str) -> bool:
    if _SITE_HINTS_RE.search(text):
        return False
    return bool(_MATH_RE.search(text))


# ── Fuzzy match ──────────────────────────────────────────────────────────────

try:
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False
    from difflib import SequenceMatcher


def _similarity(a: str, b: str) -> float:
    """Возвращает 0..100."""
    a, b = a.strip().lower(), b.strip().lower()
    if not a or not b:
        return 0.0
    if _HAS_RAPIDFUZZ:
        return float(_rf_fuzz.token_set_ratio(a, b))
    # Fallback: difflib
    return SequenceMatcher(None, a, b).ratio() * 100.0


def _best_kb_match(message: str, threshold: float = 78.0) -> Optional[dict]:
    """Найти лучший intent из KB по сходству с сообщением."""
    if not message:
        return None
    msg = message.strip().lower()
    kb = _load_kb()

    best, best_score = None, 0.0
    for entry in kb:
        # сначала по самому intent-заголовку
        score = _similarity(msg, entry.get('intent', ''))
        # затем по keywords (берём максимум по каждому)
        for kw in entry.get('keywords') or []:
            score = max(score, _similarity(msg, kw))
            # Точное вхождение ключевого слова — даём бонус.
            if kw.lower() in msg:
                score = max(score, 92.0)
        if score > best_score:
            best, best_score = entry, score

    if best and best_score >= threshold:
        logger.debug('KB match: %s (score=%.1f)', best.get('id'), best_score)
        return best
    return None


# ── LLM fallback ─────────────────────────────────────────────────────────────

# Хранится в модуле — формируется один раз при импорте.
_LLM_SYSTEM_PROMPT = """Ты — AI-помощник сайта FORMYLA, российской онлайн-платформы по подготовке к школьным математическим олимпиадам (ВсОШ, Турнир городов, Эйлера, Ломоносова, Высшая проба, Матпраздник).

ТВОЯ ОБЛАСТЬ:
• Навигация по сайту: где задачи, где пробники, где доска, где тарифы.
• Подписки и тарифы: Free (5 задач/день), Pro Месяц 390 ₽, Pro Год 2790 ₽ (родительский доступ).
• Возможности: 7 ИИ-агентов по темам, режим «только подсказки», радар прогресса, AI-чертежи, банк 295 задач ВсОШ-9 по 89 методам.
• Поддержка: Telegram-бот (ссылка внизу /about), отмена подписки в /subscribe.

ПРАВИЛА:
1. Отвечай КРАТКО — 3–5 строк живого текста, без буллетов и заголовков.
2. Если вопрос ПРО МАТЕМАТИКУ (решить задачу, объяснить теорему) — НЕ решай, ответь «Это вопрос по математике, открой 🤖 ИИ-тьютора в правом нижнем углу — он специально под это» и НИЧЕГО больше.
3. Если вопрос НЕ ПРО САЙТ FORMYLA и НЕ ПРО МАТЕМАТИКУ — вежливо откажись: «Я помогаю только с сайтом FORMYLA. Попробуй переформулировать».
4. Если знаешь подходящий раздел сайта, упомяни его и предложи кнопку.
5. НЕ выдумывай цены, фичи, обещания. Используй только факты из этой инструкции.

Структура ответа (JSON):
{
  "answer": "<3-5 строк, живо, по-человечески>",
  "suggested_actions": [
    {"label": "<краткая надпись на кнопке, можно с emoji>", "url": "<относительный URL раздела сайта>"}
  ]
}

Допустимые URL: /, /about, /daily, /probniks, /problems, /olympiads, /olympiads/courses, /olympiads/methods, /olympiad-prep, /subscribe, /profile, /drawing, /section/algebra, /section/geometry, /leaderboard, /chat, /friends.

Возвращай СТРОГО валидный JSON, без markdown-обёртки."""


def _llm_answer(message: str, context: dict) -> Optional[dict]:
    """Спросить у Claude через OpenRouter. Возвращает dict или None."""
    try:
        # Lazy import — чтобы concierge оставался импортируемым даже без LLM ключа.
        from services.openrouter_client import openrouter  # type: ignore
    except Exception:
        try:
            # Fallback: модуль может экспортировать класс, а не singleton.
            from services.openrouter_client import OpenRouterClient  # type: ignore
            openrouter = OpenRouterClient()
        except Exception as e:
            logger.warning('OpenRouter client unavailable: %s', e)
            return None

    if not getattr(openrouter, 'api_key', '') or not openrouter.api_key:
        logger.info('OpenRouter API key not set — LLM concierge disabled.')
        return None

    current_url = (context or {}).get('current_url') or ''
    user_msg = message
    if current_url:
        user_msg = f"[Текущая страница: {current_url}]\n\nВопрос пользователя: {message}"

    messages = [
        {"role": "system", "content": _LLM_SYSTEM_PROMPT},
        {"role": "user",   "content": user_msg},
    ]

    try:
        result = openrouter.chat(
            model='anthropic/claude-sonnet-4.7',
            messages=messages,
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.warning('LLM call failed: %s', e)
        return None

    content = (result or {}).get('content') or ''
    if not content.strip():
        return None

    # Strip потенциальные markdown-обёртки.
    content = content.strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Грубый fallback: достаём как есть.
        return {
            "answer": content[:1200],
            "suggested_actions": [],
        }

    answer = (parsed.get('answer') or '').strip()
    actions = parsed.get('suggested_actions') or []
    safe_actions: list[dict] = []
    for a in actions[:4]:
        label = (a.get('label') or '').strip()
        url = (a.get('url') or '').strip()
        if label and url and url.startswith('/'):
            safe_actions.append({"label": label, "url": url})

    if not answer:
        return None
    return {"answer": answer, "suggested_actions": safe_actions}


# ── Public API ───────────────────────────────────────────────────────────────

_DEFAULT_REDIRECT_ANSWER = (
    "Это вопрос по математике, открой 🤖 ИИ-тьютора в правом нижнем углу — "
    "он специально под решение задач. Я помогаю только с навигацией по сайту."
)
_DEFAULT_OFFTOPIC_ANSWER = (
    "Я помощник по сайту FORMYLA: тарифы, разделы, как начать, как готовиться "
    "к олимпиадам. Если хотел другое — попробуй переформулировать."
)


def answer_site_question(message: str, context: Optional[dict] = None) -> dict:
    """Главный публичный entry-point.

    :param message: текст вопроса пользователя.
    :param context: словарь с метаданными (current_url, user_id и т.п.).
    :return: dict { answer, suggested_actions, source, intent_id }
    """
    context = context or {}
    message = (message or '').strip()
    if not message:
        return {
            "answer": "Напиши, что хочешь сделать — подскажу, куда нажать.",
            "suggested_actions": [],
            "source": "empty",
            "intent_id": None,
        }

    # 1) Математика → редирект к тьютору.
    if _looks_like_math(message):
        return {
            "answer": _DEFAULT_REDIRECT_ANSWER,
            "suggested_actions": [],
            "source": "redirect",
            "intent_id": None,
        }

    # 2) Fuzzy match KB.
    kb_hit = _best_kb_match(message)
    if kb_hit:
        return {
            "answer": kb_hit.get('answer', '').strip(),
            "suggested_actions": kb_hit.get('suggested_actions') or [],
            "source": "kb",
            "intent_id": kb_hit.get('id'),
        }

    # 3) LLM fallback.
    llm_hit = _llm_answer(message, context)
    if llm_hit:
        return {
            "answer": llm_hit.get('answer', '').strip(),
            "suggested_actions": llm_hit.get('suggested_actions') or [],
            "source": "llm",
            "intent_id": None,
        }

    # 4) Минимальный «безопасный» ответ — топ-фоллбэк к ключевым разделам.
    return {
        "answer": _DEFAULT_OFFTOPIC_ANSWER,
        "suggested_actions": [
            {"label": "🚀 Задачи дня", "url": "/daily"},
            {"label": "📖 О сервисе", "url": "/about"},
            {"label": "💎 Тарифы", "url": "/about#pricing"},
        ],
        "source": "fallback",
        "intent_id": None,
    }


# ── Top intents (для quick-replies на фронте) ────────────────────────────────

def get_top_intents(limit: int = 10) -> list[dict]:
    """Список intents для отображения как Quick Replies."""
    kb = _load_kb()
    items = []
    for entry in kb[:limit]:
        items.append({
            "id": entry.get('id'),
            "intent": entry.get('intent'),
            "icon": entry.get('icon', '💬'),
        })
    return items
