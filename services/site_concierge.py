# -*- coding: utf-8 -*-
"""
Site Concierge — AI-помощник по сайту FORMYLA.

Архитектура (router-first):
  1. Точное / нечёткое совпадение с intent_keyword из data/site_kb.json
     (threshold ~92%, через rapidfuzz если установлен, иначе difflib).
  2. Иначе — DeepSeek-router: один LLM-вызов классифицирует сообщение и
     возвращает СТРОГИЙ JSON одного из трёх типов:
       * {"action": "kb",       "id": "<intent_id>"}              — подходит готовый ответ
       * {"action": "redirect", "target": "tutor" | "off_topic"}  — мат-задача / не про сайт
       * {"action": "free",     "answer": "<...>",                — нет KB-кандидата, своя реплика
                                 "suggested_actions": [...]}
  3. Если LLM недоступен -> консервативный fallback (показываем главные ссылки).

Публичный API:
    answer_site_question(message: str, context: dict) -> dict
        Returns: {
            "answer": str,
            "suggested_actions": [{"label": str, "url": str}, ...],
            "source": "kb" | "llm_kb" | "llm_free" | "redirect" | "off_topic" | "fallback" | "empty",
            "intent_id": str | None,
        }
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Optional

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


def _find_kb_by_id(intent_id: str) -> Optional[dict]:
    for entry in _load_kb():
        if entry.get('id') == intent_id:
            return entry
    return None


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
        # ratio() — обычный Левенштейн, требует сходства ВСЕЙ строки.
        # token_set_ratio даёт 100 даже когда keyword — короткое подмножество фразы,
        # что для нас плохо: уводит всё в ближайший KB-intent с такой подстрокой.
        return float(_rf_fuzz.ratio(a, b))
    return SequenceMatcher(None, a, b).ratio() * 100.0


def _best_kb_match(message: str, threshold: float = 95.0) -> Optional[dict]:
    """Строгий short-circuit match: срабатывает ТОЛЬКО когда вся фраза
    пользователя ≈ одному intent-заголовку или одной полной keyword-фразе.

    Все промежуточные / неоднозначные случаи уходят DeepSeek-роутеру, который
    разбирается лучше, чем substring-match: например, «разбор задач ВсОШ
    прошлых лет» и «как готовиться к ВсОШ» отличает только LLM, а в KB у обоих
    есть keyword «всош».
    """
    if not message:
        return None
    msg = message.strip().lower()
    kb = _load_kb()

    best, best_score = None, 0.0
    for entry in kb:
        # 1) Очень близкое совпадение с самим заголовком intent.
        score = _similarity(msg, (entry.get('intent') or '').lower())
        # 2) Точное (или почти точное) совпадение с одной из keyword-фраз.
        for kw in entry.get('keywords') or []:
            kw_l = kw.lower()
            score = max(score, _similarity(msg, kw_l))
            # «keyword-фраза целиком равна сообщению» — берём агрессивно;
            # «keyword входит как подстрока» — НЕ берём, отдаём LLM.
            if kw_l == msg:
                score = max(score, 100.0)
        if score > best_score:
            best, best_score = entry, score

    if best and best_score >= threshold:
        logger.debug('KB exact match: %s (score=%.1f)', best.get('id'), best_score)
        return best
    return None


# ── DeepSeek router ──────────────────────────────────────────────────────────

_ROUTER_SYSTEM_PROMPT_TEMPLATE = """Ты — диспетчер AI-помощника на сайте FORMYLA, российской онлайн-платформе подготовки к математическим олимпиадам (ВсОШ, Турнир городов, Эйлера, Ломоносова, Высшая проба, Матпраздник).

Твоя задача: получив сообщение пользователя, выбрать ОДНО из трёх действий и вернуть СТРОГО валидный JSON БЕЗ markdown-обёртки.

═══════════════════════════════════════════════════════
ДОСТУПНЫЕ ГОТОВЫЕ ОТВЕТЫ (intent-ы из базы знаний)
═══════════════════════════════════════════════════════
{intents_block}

═══════════════════════════════════════════════════════
ТРИ ВОЗМОЖНЫХ ОТВЕТА (выбери ровно один)
═══════════════════════════════════════════════════════

1) Если вопрос пользователя — про навигацию по сайту FORMYLA и явно ложится в один из intent-ов выше:
   {{"action": "kb", "id": "<id_intent>"}}

2) Если вопрос — НЕ про сайт FORMYLA:
   • Математическая задача / «реши это», «помоги с уравнением», «как доказать», объяснить теорему:
     {{"action": "redirect", "target": "tutor"}}
   • Любой посторонний вопрос (погода, новости, политика, языки, болтовня):
     {{"action": "redirect", "target": "off_topic"}}

3) Если вопрос — про сайт FORMYLA, но НЕ покрывается ни одним intent-ом
   (например, спрашивают редкую фичу, политику конфиденциальности, как пожаловаться):
   {{"action": "free",
     "answer": "<3-5 строк живого текста на русском, БЕЗ markdown, БЕЗ буллетов>",
     "suggested_actions": [
       {{"label": "<краткая надпись (можно с emoji)>", "url": "<относительный URL>"}}
     ]}}

ОГРАНИЧЕНИЯ для action=free:
   • Не выдумывай цены, фичи, обещания. Опирайся только на факты:
     – Все функции FORMYLA сейчас полностью бесплатны — подписок и тарифов нет.
     – 7 ИИ-агентов: алгебра, геометрия, теория чисел, комбинаторика, движение, логика, стратегия.
     – База: задачи ВсОШ-9 прошлых лет, разобранные по 102 методам.
     – Поддержка — Telegram-бот по ссылке внизу /about.
   • Допустимые URL: /, /about, /about#unique, /about#support,
     /daily, /probniks, /problems, /olympiads, /olympiads/courses, /olympiads/methods,
     /olympiad-prep, /profile, /section/algebra, /section/geometry,
     /leaderboard, /chat, /friends.

ВСЕГДА возвращай ровно один JSON-объект, без обёрток ```json, без комментариев.
"""


def _build_router_system_prompt() -> str:
    kb = _load_kb()
    lines = []
    for entry in kb:
        line = f'  • id="{entry.get("id")}" — {entry.get("intent")}'
        kws = entry.get('keywords') or []
        if kws:
            line += f'  (ключевые слова: {", ".join(kws[:6])})'
        lines.append(line)
    intents_block = '\n'.join(lines) if lines else '  (KB пуста)'
    return _ROUTER_SYSTEM_PROMPT_TEMPLATE.format(intents_block=intents_block)


@lru_cache(maxsize=1)
def _cached_router_prompt() -> str:
    return _build_router_system_prompt()


def _strip_json_codeblock(s: str) -> str:
    s = s.strip()
    if s.startswith('```'):
        s = re.sub(r'^```(?:json)?\s*', '', s)
        s = re.sub(r'\s*```$', '', s)
    return s.strip()


def _deepseek_router(message: str, context: dict) -> Optional[dict]:
    """Вызов DeepSeek в режиме классификатора. Возвращает разобранный JSON
    одного из трёх типов (action: kb / redirect / free) либо None при ошибке."""
    try:
        from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError  # type: ignore
    except Exception as e:
        logger.warning('DeepSeekClient unavailable: %s', e)
        return None

    if not os.environ.get('DEEPSEEK_API_KEY'):
        logger.info('DEEPSEEK_API_KEY not set — concierge LLM router disabled.')
        return None

    try:
        client = DeepSeekClient()
    except Exception as e:
        logger.warning('Cannot init DeepSeekClient: %s', e)
        return None

    current_url = (context or {}).get('current_url') or ''
    user_msg = message.strip()
    if current_url:
        user_msg = f'[Текущая страница пользователя: {current_url}]\n\nСообщение: {user_msg}'

    try:
        raw = client.generate(
            prompt=user_msg,
            system_prompt=_cached_router_prompt(),
            temperature=0.2,
            max_tokens=500,
        )
    except DeepSeekAPIError as e:
        logger.warning('DeepSeek router API error: %s', e)
        return None
    except Exception as e:
        logger.warning('DeepSeek router call failed: %s', e)
        return None

    if not raw or not raw.strip():
        return None

    cleaned = _strip_json_codeblock(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning('Router returned non-JSON: %s | head=%r', e, cleaned[:200])
        return None

    action = (parsed.get('action') or '').strip().lower()
    if action not in ('kb', 'redirect', 'free'):
        logger.warning('Router unknown action: %r', action)
        return None
    return parsed


# ── Public API ───────────────────────────────────────────────────────────────

_REDIRECT_TUTOR_ANSWER = (
    "Похоже, это вопрос по математике. Открой  ИИ-тьютора в правом нижнем углу — "
    "он специально под решение задач, у него 7 агентов по темам и режим «только подсказки». "
    "Я помогаю только по сайту FORMYLA."
)
_OFFTOPIC_ANSWER = (
    "Я помощник по сайту FORMYLA: тарифы, разделы, как начать, как готовиться к олимпиадам. "
    "Если хотел другое — попробуй переформулировать вопрос про сам сервис."
)
_FALLBACK_ACTIONS = [
    {"label": " Задачи дня", "url": "/daily"},
    {"label": " О сервисе",  "url": "/about"},
    {"label": " Тарифы",     "url": "/about#pricing"},
]


def _sanitize_actions(raw_actions, max_items: int = 4) -> list:
    """Оставляем только {label,url} с относительным URL."""
    out = []
    for a in (raw_actions or [])[:max_items]:
        if not isinstance(a, dict):
            continue
        label = (a.get('label') or '').strip()
        url = (a.get('url') or '').strip()
        if label and url and url.startswith('/'):
            out.append({"label": label, "url": url})
    return out


def _from_kb_entry(entry: dict, source: str) -> dict:
    return {
        "answer": (entry.get('answer') or '').strip(),
        "suggested_actions": entry.get('suggested_actions') or [],
        "source": source,
        "intent_id": entry.get('id'),
    }


def answer_site_question(message: str, context: Optional[dict] = None) -> dict:
    """Главный entry-point: KB -> DeepSeek-router -> fallback."""
    context = context or {}
    message = (message or '').strip()
    if not message:
        return {
            "answer": "Напиши, что хочешь сделать — подскажу, куда нажать.",
            "suggested_actions": [],
            "source": "empty",
            "intent_id": None,
        }

    # 1) Быстрый строгий KB-матч (только при ОЧЕНЬ близком совпадении формулировки).
    kb_hit = _best_kb_match(message, threshold=95.0)
    if kb_hit:
        return _from_kb_entry(kb_hit, source='kb')

    # 2) DeepSeek в роли роутера.
    routed = _deepseek_router(message, context)
    if routed:
        action = routed.get('action')
        if action == 'kb':
            intent_id = (routed.get('id') or '').strip()
            entry = _find_kb_by_id(intent_id)
            if entry:
                return _from_kb_entry(entry, source='llm_kb')
            logger.warning('Router pointed to unknown intent id=%r — fallback', intent_id)
        elif action == 'redirect':
            target = (routed.get('target') or '').strip()
            if target == 'tutor':
                return {
                    "answer": _REDIRECT_TUTOR_ANSWER,
                    "suggested_actions": [],
                    "source": "redirect",
                    "intent_id": None,
                }
            # off_topic или любой иной target
            return {
                "answer": _OFFTOPIC_ANSWER,
                "suggested_actions": [],
                "source": "off_topic",
                "intent_id": None,
            }
        elif action == 'free':
            answer_text = (routed.get('answer') or '').strip()
            actions = _sanitize_actions(routed.get('suggested_actions'))
            if answer_text:
                return {
                    "answer": answer_text,
                    "suggested_actions": actions,
                    "source": "llm_free",
                    "intent_id": None,
                }

    # 3) Last resort — статический набор популярных ссылок.
    return {
        "answer": _OFFTOPIC_ANSWER,
        "suggested_actions": list(_FALLBACK_ACTIONS),
        "source": "fallback",
        "intent_id": None,
    }


# ── Полная справка по сайту для ИИ-куратора ────────────────────────────────


def build_site_context_for_llm() -> str:
    """Текстовый блок «всей базы сайта» для инъекции в system_prompt куратора.

    Содержит: все разделы/функции FORMYLA с реальными URL и фактами
    (тарифы, лимиты, инструменты). Куратор обязан опираться ТОЛЬКО на этот
    блок и не выдумывать кнопки/страницы/цены, которых здесь нет.
    """
    kb = _load_kb()
    lines = [
        "ПОЛНАЯ СПРАВКА О САЙТЕ FORMYLA (единственный источник правды о сайте):",
        "",
        "Функции и разделы:",
    ]
    for entry in kb:
        icon = entry.get('icon', '')
        intent = entry.get('intent', '')
        answer = (entry.get('answer') or '').strip()
        actions = entry.get('suggested_actions') or []
        urls = ', '.join(a.get('url', '') for a in actions if a.get('url'))
        line = f"  • {icon} {intent}"
        if answer:
            # сжимаем длинный ответ до сути
            short = ' '.join(answer.split())
            if len(short) > 220:
                short = short[:219].rstrip() + '…'
            line += f" — {short}"
        if urls:
            line += f" [ссылки: {urls}]"
        lines.append(line)

    lines += [
        "",
        "Ключевые факты (не выдумывай другие):",
        "  • Все функции FORMYLA сейчас полностью бесплатны — подписок, тарифов и оплат нет.",
        "  • 7 ИИ-агентов: алгебра, геометрия, теория чисел, комбинаторика, движение, логика, стратегия.",
        "  • База: задачи ВсОШ-9 прошлых лет (муниципальный, региональный, заключительный этапы), разобраны по 102 методам.",
        "  • Поддержка — Telegram-бот, ссылка внизу /about.",
        "",
        "Реальные страницы (ссылайся только на существующие):",
        "  /, /about, /about#unique, /about#support, /daily, /daily_tasks,",
        "  /prep/coach, /prep/probe, /probniks, /problems, /olympiads, /olympiads/methods,",
        "  /olympiad-prep, /profile, /section/algebra, /section/geometry,",
        "  /leaderboard, /chat, /friends, /insights, /figures, /intake, /adaptive_test_simple.",
        "",
        "Правило: если ученик спрашивает про фичу/страницу/цену, которой нет выше —",
        "честно скажи, что такого в FORMYLA нет, и не выдумывай.",
    ]
    return "\n".join(lines)


# ── Top intents (для quick-replies на фронте) ────────────────────────────────

def get_top_intents(limit: int = 10) -> list:
    kb = _load_kb()
    items = []
    for entry in kb[:limit]:
        items.append({
            "id": entry.get('id'),
            "intent": entry.get('intent'),
            "icon": entry.get('icon', ''),
        })
    return items
